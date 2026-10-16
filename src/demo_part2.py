"""Executa os casos reproduziveis da Parte 2 e grava logs/part2_runs.json."""

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from catalogo_db import construir_banco  # noqa: E402
from graph import create_graph, resultado_publico, resumir  # noqa: E402
from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402

OUTPUT_PATH = ROOT / "logs" / "part2_runs.json"

CASES = [
    {
        "case_id": "01_caminho_feliz",
        "message": "Curti Severance pelo mal-estar constante. Indica algo parecido.",
        "user_id": "demo-p2-01", "subscriptions": ["Netflix"], "max_rating": "16+",
        "expected": "recommendation", "approval": {"decision": "approve"},
    },
    {
        "case_id": "02_divergencia",
        "message": "Quero algo leve e sem ficar pensando demais. Me lembra Severance?",
        "user_id": "demo-p2-02", "subscriptions": ["Netflix", "Prime Video"], "max_rating": "14+",
        "expected": "recommendation", "approval": {"decision": "approve"},
    },
    {
        "case_id": "03_registro_inexistente",
        "message": "Amei O Enigma de Kessler, quero misterio e estranheza. Me recomenda algo.",
        "user_id": "demo-p2-03", "subscriptions": ["Netflix"], "max_rating": "16+",
        "expected": "recommendation", "approval": {"decision": "approve"},
    },
    {
        "case_id": "04_nao_dispara_acao",
        "message": "Quero algo intenso e estranho, tipo Severance.",
        "user_id": "demo-p2-04", "subscriptions": ["Prime Video"], "max_rating": "10+",
        "expected": "no_match",
    },
    {
        "case_id": "05_fora_do_corpus",
        "message": "Recomenda um filme de viagem submarina.",
        "user_id": "demo-p2-05", "subscriptions": ["Netflix"], "max_rating": "16+",
        "expected": "no_match",
    },
    {
        "case_id": "06_pausa_edicao_idempotencia",
        "message": "Quero algo leve e cotidiano, para rir. Recomenda um titulo.",
        "user_id": "demo-p2-06", "subscriptions": ["Netflix"], "max_rating": "16+",
        "expected": "recommendation",
        "approval": {
            "decision": "approve",
            "reason": "Edicao humana: o trecho descreve leveza e humor cotidiano.",
            "remember_preference": True,
        },
        "duplicate_write": True,
    },
    {
        "case_id": "07_entrada_incompleta",
        "message": "Me indica algo parecido.",
        "user_id": "demo-p2-07", "subscriptions": ["Netflix"], "max_rating": "16+",
        "expected": "clarification",
    },
    {
        "case_id": "08_entrada_ambigua",
        "message": "Me recomenda algo leve ou intenso? Ainda nao sei.",
        "user_id": "demo-p2-08", "subscriptions": ["Netflix"], "max_rating": "16+",
        "expected": "clarification",
    },
    {
        "case_id": "09_fora_de_escopo",
        "message": "Qual e a previsao do tempo?",
        "user_id": "demo-p2-09", "subscriptions": ["Netflix"], "max_rating": "16+",
        "expected": "out_of_scope",
    },
]


def _git_metadata() -> dict:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    dirty = bool(subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip())
    return {"source_commit": commit, "working_tree_dirty": dirty}


def _run_one(graph, case: dict, db_path: Path, provenance: dict) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    request = {
        "message": case["message"],
        "user_id": case["user_id"],
        "subscriptions": case["subscriptions"],
        "max_rating": case["max_rating"],
        "region": "BR",
        "session_id": case["case_id"],
        "case_id": case["case_id"],
    }
    thread_id = request["session_id"]
    state = graph.invoke(
        {**request, "messages": [{"role": "user", "content": case["message"]}]},
        config={"configurable": {"thread_id": thread_id}, "recursion_limit": 12},
    )
    pause = resultado_publico(state)
    pending_action = pause.get("pending_action")
    human_response = case.get("approval")
    write_attempts = []
    if pending_action and human_response:
        state = resumir(thread_id, human_response, graph)
        if state.get("persist_result"):
            write_attempts.append(state["persist_result"])
        if case.get("duplicate_write") and state.get("idempotency_key"):
            duplicate_state = resumir(thread_id, human_response, graph, db_path)
            write_attempts.append(duplicate_state["duplicate_write_result"])
    output = resultado_publico(state)
    assert output["status"] == case["expected"], (case["case_id"], output)
    return {
        **provenance,
        "case_id": case["case_id"],
        "started_at": started,
        "request": request,
        "execution": {
            "engine": state.get("decision_source", "regras_locais"),
            "model": state.get("decision_source") == "modelo",
            "model_name": state.get("model_name"),
            "temperature": state.get("temperature"),
            "model_calls": state.get("model_calls", 0),
            "model_output_tokens": state.get("model_tokens", 0),
            "max_output_tokens": 300,
            "timeout_seconds": 20,
            "recursion_limit": 12,
            "prompt_sha256": state.get("prompt_manifest", {}),
            "retrieval_calls": state.get("retrieval_calls", 0),
            "thread_id": thread_id,
        },
        "paused_action": pending_action,
        "human_response": human_response,
        "write_attempts": write_attempts,
        "decision": output,
        "trajectory": state.get("trajectory", []),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    provenance = _git_metadata()
    with tempfile.TemporaryDirectory(prefix="agente-p2-") as temp:
        root = Path(temp)
        db_path = root / "catalogo.db"
        checkpoint_path = root / "checkpoints.sqlite"
        construir_banco(db_path)
        with SqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
            checkpointer.setup()
            graph = create_graph(db_path, checkpointer)
            runs = [_run_one(graph, case, db_path, provenance) for case in CASES]
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(runs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(runs)} execucoes gravadas em {OUTPUT_PATH.relative_to(ROOT)}")
    for run in runs:
        print(f"{run['case_id']}: {run['decision']['status']} | retrievals={run['execution']['retrieval_calls']} | commit={run['source_commit'][:12]} dirty={run['working_tree_dirty']}")


if __name__ == "__main__":
    main()
