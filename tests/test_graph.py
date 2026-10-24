"""Tests for the LangGraph contract, retrieval, pause, and idempotent writes."""

import operator
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
from typing import Annotated, TypedDict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402
from langgraph.errors import InvalidUpdateError  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

from catalogo_db import CatalogoDB, construir_banco  # noqa: E402
from graph import (  # noqa: E402
    APPROVAL_TIMEOUT_SECONDS,
    create_graph,
    expirar_pendencia,
    remover_titular,
    resultado_publico,
    resumir,
    varrer_pendencias,
)
from rag import buscar_evidencias  # noqa: E402


class ParallelState(TypedDict):
    values: Annotated[list[str], operator.add]


class ParallelStateWithoutReducer(TypedDict):
    value: str


def parallel_test_graph(with_reducer=True):
    state_type = ParallelState if with_reducer else ParallelStateWithoutReducer
    graph = StateGraph(state_type)
    left_value = ["left"] if with_reducer else "left"
    right_value = ["right"] if with_reducer else "right"
    graph.add_node("left", lambda _: {"values" if with_reducer else "value": left_value})
    graph.add_node("right", lambda _: {"values" if with_reducer else "value": right_value})
    graph.add_edge(START, "left")
    graph.add_edge(START, "right")
    graph.add_edge("left", END)
    graph.add_edge("right", END)
    return graph.compile()


class TestGraphPart2(unittest.TestCase):
    def setUp(self):
        # graph.py carrega o .env no import; sem isto, a chave local faz os
        # testes chamarem o modelo e as asserções determinísticas quebram.
        env_patch = mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db_path = self.root / "catalogo.db"
        self.checkpoint_path = self.root / "checkpoints.sqlite"
        construir_banco(self.db_path)
        self.saver_context = SqliteSaver.from_conn_string(str(self.checkpoint_path))
        self.saver = self.saver_context.__enter__()
        self.saver.setup()
        self.addCleanup(self.saver_context.__exit__, None, None, None)
        self.graph = create_graph(self.db_path, self.saver)

    def run_request(self, message, user="u-test", subscriptions=None, rating="16+", thread="t-1"):
        return self.graph.invoke({
            "message": message,
            "user_id": user,
            "subscriptions": subscriptions or ["Netflix"],
            "max_rating": rating,
            "region": "BR",
            "session_id": thread,
            "messages": [{"role": "user", "content": message}],
        }, config={"configurable": {"thread_id": thread}, "recursion_limit": 12})

    def test_approval_pauses_before_write_and_resume_saves(self):
        state = self.run_request(
            "Curti Severance pelo mal-estar constante. Indica algo parecido.",
            user="u-graph-1", thread="approve-1",
        )
        self.assertEqual(resultado_publico(state)["status"], "awaiting_human")
        with CatalogoDB(self.db_path) as db:
            self.assertEqual(db.historico("u-graph-1"), [])
        done = resumir("approve-1", {
            "decision": "approve",
            "reason": "Editado pelo responsavel: evidencia de inquietacao constante.",
        }, self.graph)
        result = resultado_publico(done)
        self.assertEqual(result["status"], "recommendation")
        self.assertTrue(result["sufficient"])
        self.assertEqual(done["persist_result"]["ja_existia"], False)
        self.assertIn("messages", done)

    def test_duplicate_approval_write_is_idempotent(self):
        state = self.run_request(
            "Quero algo leve e cotidiano, para rir. Recomenda um titulo.",
            user="u-graph-2", thread="approve-2",
        )
        approval = {
            "decision": "approve", "remember_preference": True,
        }
        done = resumir("approve-2", approval, self.graph)
        self.assertEqual(done["persist_result"]["ja_existia"], False)
        duplicate_resume = resumir("approve-2", approval, self.graph, self.db_path)
        self.assertTrue(duplicate_resume["duplicate_resume"])
        self.assertTrue(duplicate_resume["duplicate_write_result"]["ja_existia"])
        with CatalogoDB(self.db_path) as db:
            self.assertEqual(len(db.historico("u-graph-2")), 1)
            self.assertEqual(len(db.buscar_episodios("u-graph-2", "leve cotidiano")), 1)
            self.assertEqual(
                db.obter_preferencia("u-graph-2")["resumo"],
                "preferencia explicitamente autorizada: leve",
            )

    def test_rejection_does_not_write(self):
        self.run_request(
            "Quero algo leve e cotidiano, para rir. Recomenda um titulo.",
            user="u-reject", thread="reject-1",
        )
        done = resumir("reject-1", {"decision": "reject"}, self.graph)
        self.assertEqual(resultado_publico(done)["status"], "rejected")
        with CatalogoDB(self.db_path) as db:
            self.assertEqual(db.historico("u-reject"), [])

    def test_expired_approval_rejects_on_resume(self):
        state = self.run_request(
            "Quero algo leve e cotidiano, para rir. Recomenda um titulo.",
            user="u-expired", thread="expired-1",
        )
        config = {"configurable": {"thread_id": "expired-1"}}
        pending = dict(state["pending_action"])
        pending["created_at"] = time.time() - APPROVAL_TIMEOUT_SECONDS - 1
        self.graph.update_state(config, {"pending_action": pending})
        done = expirar_pendencia("expired-1", self.graph, agora=time.time())
        self.assertIsNotNone(done)
        self.assertEqual(resultado_publico(done)["status"], "rejected")
        with CatalogoDB(self.db_path) as db:
            self.assertEqual(db.historico("u-expired"), [])

    def test_scheduler_sweep_expires_only_overdue_threads(self):
        message = "Quero algo leve e cotidiano, para rir. Recomenda um titulo."
        self.run_request(message, user="u-old", thread="sweep-old")
        self.run_request(message, user="u-new", thread="sweep-new")
        self.run_request("Qual e a previsao do tempo?", user="u-done", thread="sweep-done")
        old = {"configurable": {"thread_id": "sweep-old"}}
        pending = dict(self.graph.get_state(old).values["pending_action"])
        pending["created_at"] = time.time() - APPROVAL_TIMEOUT_SECONDS - 1
        self.graph.update_state(old, {"pending_action": pending})

        self.assertEqual(varrer_pendencias(self.graph, agora=time.time()), ["sweep-old"])
        self.assertEqual(self.graph.get_state(old).values["decision"]["status"], "rejected")
        self.assertIn("approval", self.graph.get_state(
            {"configurable": {"thread_id": "sweep-new"}}).next)
        self.assertEqual(varrer_pendencias(self.graph, agora=time.time()), [])
        with CatalogoDB(self.db_path) as db:
            self.assertEqual(db.historico("u-old"), [])

    def test_sweep_survives_a_corrupted_thread(self):
        message = "Quero algo leve e cotidiano, para rir. Recomenda um titulo."
        self.run_request(message, user="u-old", thread="sweep-old")
        old = {"configurable": {"thread_id": "sweep-old"}}
        pending = dict(self.graph.get_state(old).values["pending_action"])
        pending["created_at"] = time.time() - APPROVAL_TIMEOUT_SECONDS - 1
        self.graph.update_state(old, {"pending_action": pending})
        # "a-broken" vem antes na ordem alfabetica: sem isolamento, a varredura parava nela
        self.saver.conn.execute(
            "INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, type, checkpoint, metadata) "
            "VALUES ('a-broken', '', 'x', 'msgpack', X'c1c1c1', X'c1')")
        self.saver.conn.commit()

        falhas = []
        expiradas = varrer_pendencias(self.graph, agora=time.time(), falhas=falhas)

        self.assertEqual(expiradas, ["sweep-old"])
        self.assertEqual([falha["thread_id"] for falha in falhas], ["a-broken"])

    def test_missing_rating_fails_closed(self):
        message = "Quero algo leve e cotidiano, para rir. Recomenda um titulo."
        with_rating = resultado_publico(self.run_request(message, user="u-rated", thread="rating-1"))
        without = resultado_publico(self.run_request(message, user="u-unrated", rating=None, thread="rating-2"))

        self.assertEqual(with_rating["pending_action"]["title"], "The Office")
        self.assertEqual(without["status"], "no_match")

    def test_holder_removal_clears_every_structure_and_restores_behavior(self):
        message = "Quero algo leve e cotidiano, para rir. Recomenda um titulo."
        self.run_request(message, user="u-other", thread="rm-other")
        resumir("rm-other", {"decision": "approve"}, self.graph)
        first = self.run_request(message, user="u-rm", thread="rm-1")
        self.assertEqual(resultado_publico(first)["pending_action"]["title"], "The Office")
        resumir("rm-1", {"decision": "approve", "remember_preference": True}, self.graph)
        # comportamento mudou: o titulo ja recomendado nao volta
        changed = resultado_publico(self.run_request(message, user="u-rm", thread="rm-2"))
        self.assertNotEqual(changed.get("pending_action", {}).get("title"), "The Office")

        result = remover_titular("u-rm", self.graph, self.db_path)

        self.assertEqual(result["removidos"]["historico"], 1)
        self.assertEqual(result["removidos"]["checkpoint_threads"], 2)
        self.assertEqual(set(result["varredura_depois"].values()), {0})
        with CatalogoDB(self.db_path) as db:
            self.assertIsNone(db.obter_preferencia("u-rm"))
            self.assertEqual(len(db.historico("u-other")), 1)
        self.assertIsNotNone(self.graph.get_state({"configurable": {"thread_id": "rm-other"}}).values)
        # comportamento voltou: sem historico, o mesmo titulo pode ser proposto de novo
        restored = resultado_publico(self.run_request(message, user="u-rm", thread="rm-3"))
        self.assertEqual(restored["pending_action"]["title"], "The Office")

    def test_checkpoint_survives_saver_reopen_and_resumes(self):
        checkpoint_path = self.root / "restart-checkpoints.sqlite"
        request = {
            "message": "Curti Severance pelo mal-estar constante. Indica algo parecido.",
            "user_id": "u-restart", "subscriptions": ["Netflix"],
            "max_rating": "16+", "region": "BR", "session_id": "restart-1",
        }
        with SqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
            saver.setup()
            graph = create_graph(self.db_path, saver)
            paused = graph.invoke(request, config={"configurable": {"thread_id": "restart-1"}})
            self.assertTrue(paused.get("__interrupt__"))
        with SqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
            saver.setup()
            graph = create_graph(self.db_path, saver)
            done = resumir("restart-1", {"decision": "approve"}, graph)
            self.assertEqual(resultado_publico(done)["status"], "recommendation")

    def test_same_thread_accepts_a_second_text_turn_without_stale_evidence(self):
        self.run_request(
            "Curti Severance pelo mal-estar constante. Indica algo parecido.",
            user="u-multi", thread="multi-1",
        )
        after_first = resumir("multi-1", {"decision": "approve"}, self.graph)
        second_message = "Quero algo leve e cotidiano, para rir. Recomenda outro titulo."
        second = self.graph.invoke({
            "message": second_message,
            "user_id": "u-multi",
            "subscriptions": ["Netflix"],
            "max_rating": "16+",
            "region": "BR",
            "session_id": "multi-1",
            "messages": [{"role": "user", "content": second_message}],
        }, config={"configurable": {"thread_id": "multi-1"}, "recursion_limit": 12})
        self.assertEqual(after_first["decision"]["title"], "Dark")
        self.assertEqual(resultado_publico(second)["status"], "awaiting_human")
        self.assertEqual(resultado_publico(second)["pending_action"]["title"], "The Office")
        self.assertEqual(second["retrieval_calls"], 1)
        self.assertEqual(len(second["messages"]), 2)

    def test_reference_missing_recovers_from_explicit_mood_without_guess(self):
        state = self.run_request(
            "Amei O Enigma de Kessler, quero misterio e estranheza. Me recomenda algo.",
            thread="missing-1",
        )
        self.assertEqual(resultado_publico(state)["status"], "awaiting_human")
        self.assertEqual(state["trajectory"][0]["lookup_error"], "registro_inexistente")
        self.assertEqual(state.get("retrieval_calls"), 1)
        done = resumir("missing-1", {"decision": "approve"}, self.graph)
        result = resultado_publico(done)
        self.assertEqual(result["status"], "recommendation")
        self.assertEqual(result["title"], "The OA")

    def test_incomplete_ambiguous_and_out_of_scope_are_not_recommendations(self):
        incomplete = self.run_request("Me indica algo parecido.", thread="incomplete-1")
        ambiguous = self.run_request(
            "Me recomenda algo leve ou intenso? Ainda nao sei.", thread="ambiguous-1"
        )
        out_scope = self.run_request("Qual e a previsao do tempo?", thread="scope-1")
        self.assertEqual(resultado_publico(incomplete)["status"], "clarification")
        self.assertEqual(resultado_publico(ambiguous)["status"], "clarification")
        self.assertEqual(resultado_publico(out_scope)["status"], "out_of_scope")
        self.assertEqual(incomplete.get("retrieval_calls", 0), 0)

    def test_out_of_corpus_topic_gets_useful_refusal(self):
        state = self.run_request(
            "Recomenda um filme de viagem submarina.", thread="outside-corpus-1"
        )
        result = resultado_publico(state)
        self.assertEqual(result["status"], "no_match")
        self.assertFalse(result["sufficient"])
        self.assertIn("corpus", result["reason"])
        self.assertEqual(state.get("retrieval_calls", 0), 0)

    def test_empty_eligible_catalog_refuses_without_pause(self):
        state = self.run_request(
            "Quero algo intenso e estranho, tipo Severance.", user="u-graph-3",
            subscriptions=["Prime Video"], rating="10+", thread="no-candidate-1",
        )
        self.assertEqual(resultado_publico(state)["status"], "no_match")
        self.assertFalse(state.get("__interrupt__"))
        self.assertEqual(state.get("retrieval_calls"), 1)

    def test_rag_never_returns_revoked_evidence(self):
        evidence = buscar_evidencias("leve cotidiano", {"Dark"})
        self.assertEqual(evidence, [])
        evidence = buscar_evidencias("mal estar inquietacao", {"Dark"})
        self.assertTrue(evidence)
        self.assertNotIn("dark-review-obsolete", {row["id"] for row in evidence})

    def test_rag_eval_has_ten_classified_questions_and_absence_case(self):
        questions = json.loads((ROOT / "dados" / "rag_eval.json").read_text(encoding="utf-8"))
        self.assertEqual(len(questions), 10)
        self.assertGreaterEqual(sum(item["exception"] for item in questions), 2)
        self.assertEqual(sum(not item["in_corpus"] for item in questions), 1)
        self.assertTrue(all(item["form"] and item["question"] for item in questions))

    def test_reducer_combines_parallel_updates_and_missing_reducer_errors(self):
        combined = parallel_test_graph().invoke({"values": []})
        self.assertEqual(set(combined["values"]), {"left", "right"})
        with self.assertRaises(InvalidUpdateError):
            parallel_test_graph(with_reducer=False).invoke({"value": "start"})


if __name__ == "__main__":
    unittest.main()
