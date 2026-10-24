"""Grafo LangGraph do agente de recomendacao e demonstracao CLI.

A interpretacao de texto pode usar o LLM com JSON validado; sem credencial,
usa-se um parser local explicitamente rotulado. Filtros, recuperacao e escrita
idempotente permanecem deterministas e no codigo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from catalogo_db import (  # noqa: E402
    CatalogoDB,
    DB_PATH,
    ORDEM_CLASSIFICACAO,
    RegistroNaoEncontrado,
    construir_banco,
    normalizar,
    teto_classificacao,
)
from rag import buscar_evidencias  # noqa: E402

CHECKPOINT_PATH = ROOT / "dados" / "checkpoints.sqlite"
MAX_NODES = 12
MAX_RUNTIME_SECONDS = 20
APPROVAL_TIMEOUT_SECONDS = 24 * 60 * 60

Mood = Literal[
    "mal_estar", "misterio", "ambiente_corporativo", "tempo", "melancolia",
    "luto", "ambiente_pesado", "surreal", "ambiente_tenso", "leve",
    "sarcastico", "cotidiano", "determinacao", "inteligencia", "ascensao",
    "ambiente_quieto", "suspense", "enigma", "carismatico", "intenso",
    "proximo", "caotico",
]


class Evidence(BaseModel):
    id: str
    title: str
    text: str
    source: str
    score: int = Field(ge=1)


class RecommendationResult(BaseModel):
    """Contrato validado retornado ao consumidor."""

    status: Literal["recommendation", "no_match", "clarification", "out_of_scope", "rejected", "error"]
    title: str | None
    reason: str
    platform: str | None
    confidence: Literal["low", "medium", "high"]
    missing_info: str
    next_step: str
    sufficient: bool
    sources: list[Evidence]


class Interpretation(BaseModel):
    intent: Literal["recommendation", "out_of_scope"]
    mood: Mood | None
    ambiguous: bool
    clarification: str


# json_object, nao json_schema: medido em 2026-10-17 com ministral-8b-2512, o
# schema estrito trocava o clima dito ("mal-estar" -> ambiente_corporativo) em
# 4 de 4 chamadas, contra 3 de 4 certas com json_object. O formato fica a cargo
# do prompt v2 e da validacao Pydantic, que sobe como status "error".
INTERPRETATION_RESPONSE_FORMAT = {"type": "json_object"}


class Request(TypedDict, total=False):
    message: str
    user_id: str
    subscriptions: list[str]
    max_rating: str
    region: str
    reference_title: str | None
    session_id: str
    case_id: str


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    message: str
    user_id: str
    subscriptions: list[str]
    max_rating: str
    region: str
    reference_title: str | None
    reference_error: str | None
    session_id: str
    case_id: str
    route: str
    mood: str
    candidate_titles: list[str]
    candidates: list[dict]
    evidence: Annotated[list[dict], list.__add__]
    current_evidence: list[dict]
    trajectory: Annotated[list[dict], list.__add__]
    retrieval_calls: int
    pending_action: dict
    human_response: dict
    idempotency_key: str
    decision: dict
    started_at: float
    model_calls: int
    model_tokens: int
    model_name: str | None
    temperature: str
    decision_source: str
    persist_result: dict
    prompt_manifest: dict
    memory_hits: list[dict]
    semantic_memory: dict | None

# As listas sao acumulativas porque podem ser atualizadas por nos distintos.
# list.__add__ e um reducer puro: nao depende de estado global nem de ordem.

MOOD_ALIASES: dict[str, tuple[str, ...]] = {
    "mal_estar": ("mal estar", "mal-estar", "desconforto", "inquietacao", "estranhamento"),
    "misterio": ("misterio", "misterioso", "misteriosa"),
    "ambiente_corporativo": ("corporativo", "escritorio"),
    "tempo": ("viagem no tempo", "temporal"),
    "melancolia": ("melancolia", "melancolico", "triste"),
    "luto": ("luto",),
    "ambiente_pesado": ("pesado", "denso"),
    "surreal": ("surreal", "estranho", "estranha", "esquisito"),
    "ambiente_tenso": ("tenso", "tensa", "tensao"),
    "leve": ("leve", "leveza", "engracado", "engracada", "comedia"),
    "sarcastico": ("sarcastico", "sarcasmo"),
    "cotidiano": ("cotidiano", "dia a dia"),
    "determinacao": ("determinacao", "determinada"),
    "inteligencia": ("inteligencia", "inteligente"),
    "ascensao": ("ascensao", "superacao"),
    "ambiente_quieto": ("quieto", "silencioso"),
    "suspense": ("suspense",),
    "enigma": ("enigma", "quebra cabeca"),
    "carismatico": ("carismatico", "carismatica"),
    "intenso": ("intenso", "intensa", "intensidade"),
    "proximo": ("proximo", "intimista"),
    "caotico": ("caotico", "caotica", "frenetico"),
}
CONTRADICTORY_MOODS = ({"leve", "intenso"}, {"leve", "mal_estar"}, {"leve", "ambiente_pesado"})


def _plain(text: str) -> str:
    text = "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def inferir_climas(texto: str) -> list[str]:
    pedido = _plain(texto)
    encontrados = []
    for mood, aliases in MOOD_ALIASES.items():
        if any(re.search(r"\b" + re.escape(_plain(alias)) + r"\b", pedido) for alias in aliases):
            encontrados.append(mood)
    return encontrados


def _intent(texto: str) -> bool:
    plain = _plain(texto)
    return any(word in plain for word in (
        "indica", "recomenda", "recomendacao", "assistir", "ver algo",
        "proximo titulo", "filme", "serie", "algo parecido", "sugere", "quero algo",
    ))


def _specific_topic(texto: str) -> bool:
    plain = _plain(texto)
    return bool(re.search(r"\b(?:sobre|filme de|serie de|documentario sobre)\s+[a-z]+(?:\s+[a-z]+){0,2}\b", plain))


def _reference(texto: str, db: CatalogoDB) -> str | None:
    plain = _plain(texto)
    titulos = [row["titulo"] for row in db.conn.execute("SELECT titulo FROM titulos")]
    matches = [title for title in titulos if _plain(title) in plain]
    return max(matches, key=len) if matches else None


def _unknown_reference(texto: str, reference: str | None) -> str | None:
    if reference:
        return None
    match = re.search(
        r"\b(?:curti|gostei de|amei|assisti)\s+(?:muito\s+)?([^,.!?]+)",
        texto,
        re.IGNORECASE,
    )
    if not match:
        return None
    candidate = re.split(
        r"\b(?:e|mas|porque|pelo|pela|por)\b", match.group(1), maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    return candidate if len(candidate.split()) >= 2 else None


def _result(status: str, reason: str, *, title: str | None = None,
            platform: str | None = None, confidence: str = "low",
            missing_info: str = "nenhuma", next_step: str = "nenhuma",
            sufficient: bool = False, sources: list[dict] | None = None) -> dict:
    return RecommendationResult(
        status=status, title=title, reason=reason, platform=platform,
        confidence=confidence, missing_info=missing_info, next_step=next_step,
        sufficient=sufficient, sources=sources or [],
    ).model_dump()


def _event(node: str, **details) -> dict:
    return {"node": node, "at": time.time(), **details}


def create_graph(db_path: Path = DB_PATH, checkpointer=None):
    """Monta o grafo de produção uma vez; db_path facilita testes isolados."""
    db_path = Path(db_path)

    def triage(state: AgentState) -> dict:
        message = (state.get("message") or "").strip()
        started_at = time.monotonic()
        prompt_path = Path(__file__).resolve().parent / "prompts" / "interpret_request.txt"
        prompt = prompt_path.read_text(encoding="utf-8")
        prompt_manifest = {"interpret_request.txt": hashlib.sha256(prompt.encode("utf-8")).hexdigest()}
        configured_model = (os.environ.get("MODEL_NAME", "ministral-8b-2512")
                    if os.environ.get("OPENAI_API_KEY") else None)
        configured_temperature = os.environ.get("TEMPERATURE") or "0.2"
        reference_error = None
        with CatalogoDB(db_path) as db:
            reference = state.get("reference_title") or _reference(message, db)
            unknown_reference = _unknown_reference(message, reference)
            if unknown_reference:
                try:
                    db.obter_titulo(unknown_reference)
                except RegistroNaoEncontrado:
                    reference_error = f"registro_inexistente:{unknown_reference}"
        model_calls = 0
        model_tokens = 0
        decision_source = "regras_locais"
        if message and os.environ.get("OPENAI_API_KEY"):
            try:
                from openai import OpenAI

                client = OpenAI(
                    base_url=os.environ.get("LLM_BASE_URL") or None,
                    api_key=os.environ["OPENAI_API_KEY"],
                    timeout=MAX_RUNTIME_SECONDS,
                    max_retries=0,
                )
                answer = client.chat.completions.create(
                    model=configured_model,
                    messages=[{"role": "system", "content": prompt},
                              {"role": "user", "content": message}],
                    response_format=INTERPRETATION_RESPONSE_FORMAT,
                    max_tokens=300,
                    temperature=float(configured_temperature),
                )
                parsed = Interpretation.model_validate_json(answer.choices[0].message.content or "{}")
                moods = [parsed.mood] if parsed.mood else []
                model_calls = 1
                model_tokens = getattr(getattr(answer, "usage", None), "completion_tokens", 0) or 0
                decision_source = "modelo"
                model_out_of_scope = parsed.intent == "out_of_scope"
                model_ambiguous = parsed.ambiguous
            except Exception as exc:
                # Falha operacional, nao recusa de dominio: status proprio para o
                # log nao confundir erro do provedor com "nao ha base para recomendar".
                result = _result("error", f"A interpretacao do pedido falhou ({type(exc).__name__}); nenhum titulo foi escolhido.",
                                 next_step="tentar novamente ou reformular")
                return {"reference_title": reference, "route": "finish", "decision": result,
                        "started_at": state.get("started_at") or time.monotonic(),
                        "model_calls": 1, "model_tokens": model_tokens,
                        "model_name": configured_model, "temperature": configured_temperature,
                        "decision_source": "modelo_com_erro",
                        "prompt_manifest": prompt_manifest,
                        "trajectory": [_event("triage", route="finish", error=type(exc).__name__)]}
        else:
            moods = inferir_climas(message)
            model_out_of_scope = False
            model_ambiguous = False
        if not message:
            result = _result("clarification", "Envie em texto o que voce quer assistir.",
                             missing_info="o pedido em linguagem natural", next_step="perguntar ao usuario")
            route = "finish"
            mood = ""
        elif model_out_of_scope or (not model_calls and not _intent(message)):
            result = _result("out_of_scope", "Este agente recomenda filmes e series a partir do que voce quer sentir.",
                             next_step="pedir um pedido de recomendacao")
            route = "finish"
            mood = ""
        else:
            conflict = any(pair.issubset(set(moods)) for pair in CONTRADICTORY_MOODS)
            if model_ambiguous or conflict or (" ou " in f" {_plain(message)} " and len(moods) > 1):
                result = _result("clarification", "O pedido combina preferencias que podem levar a escolhas diferentes.",
                                 missing_info="qual clima deve ter prioridade", next_step="perguntar qual preferencia vence")
                route = "finish"
                mood = ""
            elif not moods:
                if reference_error:
                    result = _result(
                        "clarification",
                        f"A referencia nao existe no catalogo ({reference_error}); diga o clima sem depender desse titulo.",
                        missing_info="o clima desejado ou a confirmacao do titulo",
                        next_step="pedir uma descricao que possa ser buscada",
                    )
                elif _specific_topic(message):
                    result = _result(
                        "no_match",
                        "O corpus curado nao contem evidencia suficiente sobre esse assunto; nao vou inventar uma recomendacao.",
                        missing_info="uma evidencia de catalogo sobre o assunto solicitado",
                        next_step="refinar para um clima coberto ou atualizar o corpus",
                    )
                else:
                    result = _result("clarification", "Ainda nao sei qual clima voce quer; diga o que gostou ou o que quer sentir.",
                                     missing_info="o motivo do gosto ou clima desejado", next_step="perguntar ao usuario")
                route = "finish"
                mood = ""
            else:
                result = {}
                route = "retrieve"
                mood = moods[0]
        return {
            "reference_title": reference,
            "reference_error": reference_error,
            "mood": mood,
            "route": route,
            "decision": result,
            "started_at": started_at,
            "model_calls": model_calls,
            "model_tokens": model_tokens,
            "model_name": configured_model,
            "temperature": configured_temperature,
            "retrieval_calls": 0,
            "decision_source": decision_source,
            "prompt_manifest": prompt_manifest,
            "trajectory": [_event("triage", route=route, mood=mood or None,
                                   reference=reference,
                                   lookup_error=reference_error.split(":", 1)[0] if reference_error else None,
                                   unknown_reference=reference_error.split(":", 1)[1] if reference_error else None)],
        }

    def retrieve(state: AgentState) -> dict:
        if time.monotonic() - state.get("started_at", time.monotonic()) > MAX_RUNTIME_SECONDS:
            result = _result("no_match", "O limite de tempo da execucao foi atingido antes da busca.",
                             next_step="tentar novamente")
            return {"route": "finish", "decision": result,
                    "trajectory": [_event("retrieve", result="timeout", retrieval_calls=0)]}
        with CatalogoDB(db_path) as db:
            history = db.historico(state["user_id"])
            memory_hits = db.buscar_episodios(state["user_id"], state["mood"], limite=3)
            semantic_memory = db.obter_preferencia(state["user_id"])
            excluded = {row["titulo"] for row in history}
            if state.get("reference_title"):
                excluded.add(state["reference_title"])
            matches = db.buscar_por_clima(
                termos_normalizados=normalizar(state["mood"]),
                plataformas=state.get("subscriptions", []),
                classificacao_max=state.get("max_rating"),
                excluir=excluded,
            )
        eligible = {candidate["titulo"] for candidate in matches}
        evidence = buscar_evidencias(
            f"{state['mood']} {state['message']}", eligible, limite=12
        ) if eligible else []
        evidence_by_title: dict[str, list[dict]] = {}
        for item in evidence:
            evidence_by_title.setdefault(item["title"], []).append(item)
        candidates = [candidate for candidate in matches if candidate["titulo"] in evidence_by_title]
        candidates.sort(key=lambda candidate: (
            -max(item["score"] for item in evidence_by_title[candidate["titulo"]]),
            -candidate["pontuacao"], candidate["titulo"],
        ))
        return {
            "candidates": candidates,
            "candidate_titles": [candidate["titulo"] for candidate in candidates],
            "evidence": evidence,
            "current_evidence": evidence,
            "retrieval_calls": 1,
            "memory_hits": memory_hits,
            "semantic_memory": semantic_memory,
            "route": "propose",
            "trajectory": [_event("retrieve", eligible=len(eligible), returned=len(candidates), retrieval_calls=1)],
        }

    def propose(state: AgentState) -> dict:
        if not state.get("candidates"):
            result = _result(
                "no_match",
                "Nao encontrei evidencia ativa no corpus para um titulo compativel com assinatura, classificacao e historico.",
                missing_info="um clima com evidencia no corpus ou outra assinatura",
                next_step="pedir refinamento; nao relaxar filtros",
            )
            return {"decision": result, "route": "finish",
                    "trajectory": [_event("propose", result="no_match")]}

        chosen = state["candidates"][0]
        evidence = [item for item in state.get("current_evidence", []) if item["title"] == chosen["titulo"]]
        best = evidence[0]
        platform = sorted(set(chosen["plataformas_disponiveis"]))[0]
        action = {
            "action": "registrar_recomendacao_no_historico",
            "title": chosen["titulo"],
            "platform": platform,
            "reason": f"A avaliacao cita: ‘{best['text']}’",
            "consequence": "O titulo passara a constar como recomendado no historico deste usuario.",
            "optional_memory": "A preferencia so sera guardada como memoria semantica se o responsavel marcar remember_preference=true.",
            "account_owner": state["user_id"],
            "created_at": time.time(),
            "deadline_seconds": APPROVAL_TIMEOUT_SECONDS,
            "evidence_id": best["id"],
        }
        return {"pending_action": action, "route": "approval",
                "trajectory": [_event("propose", title=chosen["titulo"], source=best["id"])]}

    def approval(state: AgentState) -> dict:
        # O interrupt e prima facie a primeira operacao do no; a retomada o reexecuta.
        response = interrupt(state["pending_action"])
        if isinstance(response, str):
            response = {"decision": response}
        response = response if isinstance(response, dict) else {"decision": "reject"}
        choice = response.get("decision")
        if time.time() > state["pending_action"]["created_at"] + APPROVAL_TIMEOUT_SECONDS:
            choice = "reject"
            response = {"decision": "reject", "reason": "prazo de aprovacao expirado"}
        if choice != "approve":
            result = _result("rejected", "A pessoa responsavel rejeitou a gravacao; nenhum historico foi alterado.",
                             missing_info="nenhuma", next_step="encerrar sem gravar")
            return {"human_response": response, "decision": result, "route": "finish",
                    "trajectory": [_event("approval", outcome="rejected")]}

        title = response.get("title") or state["pending_action"]["title"]
        reason = response.get("reason") or state["pending_action"]["reason"]
        platform = response.get("platform") or state["pending_action"]["platform"]
        if title not in state.get("candidate_titles", []):
            result = _result("rejected", "A edicao humana selecionou um titulo que nao passou pelos filtros ou nao tem evidencia.",
                             next_step="reabrir uma recomendacao valida")
            return {"human_response": response, "decision": result, "route": "finish",
                    "trajectory": [_event("approval", outcome="invalid_edit", title=title)]}
        with CatalogoDB(db_path) as db:
            item = db.obter_titulo(title)
        subscriptions = set(state.get("subscriptions", []))
        rating_limit = teto_classificacao(state.get("max_rating"))
        if platform not in subscriptions or platform not in item["plataformas"]:
            valid = False
        else:
            valid = ORDEM_CLASSIFICACAO.get(item["classificacao"], 18) <= rating_limit
        if not valid:
            result = _result("rejected", "A edicao humana viola assinatura ou classificacao; nenhum registro foi gravado.",
                             next_step="corrigir os argumentos ou rejeitar")
            return {"human_response": response, "decision": result, "route": "finish",
                    "trajectory": [_event("approval", outcome="invalid_constraints")]}
        key_content = json.dumps({
            "user_id": state["user_id"], "title": title, "platform": platform,
            "mood": state["mood"], "reason": reason,
            "remember_preference": response.get("remember_preference") is True,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        key = hashlib.sha256(key_content.encode("utf-8")).hexdigest()
        updated_action = {**state["pending_action"], "title": title,
                          "platform": platform, "reason": reason,
                          "remember_preference": response.get("remember_preference") is True}
        return {"human_response": response, "pending_action": updated_action,
                "idempotency_key": key, "route": "persist",
                "trajectory": [_event("approval", outcome="approved", edited=bool(response.get("title") or response.get("reason")))]}

    def persist(state: AgentState) -> dict:
        action = state["pending_action"]
        with CatalogoDB(db_path) as db:
            saved = db.registrar_idempotente(
                state["user_id"], action["title"], "recomendado",
                f"{state['mood']} | {action['reason']}", state["idempotency_key"],
                preferencia=(f"preferencia explicitamente autorizada: {state['mood']}"
                             if action.get("remember_preference") else None),
            )
        evidence = next((item for item in state.get("current_evidence", [])
                         if item["id"] == action["evidence_id"]), None)
        result = _result(
            "recommendation", action["reason"], title=action["title"],
            platform=action["platform"], confidence="high" if evidence and evidence["score"] > 1 else "medium",
            next_step="aguardar a reacao do usuario", sufficient=bool(evidence),
            sources=[evidence] if evidence else [],
        )
        return {"decision": result, "route": "finish", "persist_result": saved,
                "trajectory": [_event("persist", **saved)]}

    builder = StateGraph(AgentState)
    builder.add_node("triage", triage)
    builder.add_node("retrieve", retrieve)
    builder.add_node("propose", propose)
    builder.add_node("approval", approval)
    builder.add_node("persist", persist)
    builder.add_edge(START, "triage")
    builder.add_conditional_edges("triage", lambda state: state["route"],
                                  {"retrieve": "retrieve", "finish": END})
    builder.add_conditional_edges("retrieve", lambda state: state["route"],
                                  {"propose": "propose", "finish": END})
    builder.add_conditional_edges("propose", lambda state: state["route"],
                                  {"approval": "approval", "finish": END})
    builder.add_conditional_edges("approval", lambda state: state["route"],
                                  {"persist": "persist", "finish": END})
    builder.add_edge("persist", END)
    return builder.compile(checkpointer=checkpointer)


@lru_cache(maxsize=1)
def get_graph():
    """Retorna o grafo compilado uma vez com checkpointer persistente SQLite."""
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    manager = SqliteSaver.from_conn_string(str(CHECKPOINT_PATH))
    checkpointer = manager.__enter__()
    checkpointer.setup()
    graph = create_graph(DB_PATH, checkpointer)
    graph._checkpointer_manager = manager
    return graph


def fechar_graph() -> None:
    graph = get_graph()
    manager = getattr(graph, "_checkpointer_manager", None)
    if manager:
        manager.__exit__(None, None, None)
        get_graph.cache_clear()


def invoke_request(request: Request, *, checkpointer=None, db_path: Path = DB_PATH,
                   recursion_limit: int = MAX_NODES):
    graph = create_graph(db_path, checkpointer) if checkpointer is not None else get_graph()
    thread_id = request.get("session_id") or request.get("user_id", "anonimo")
    graph_input = dict(request)
    graph_input["messages"] = [{"role": "user", "content": request.get("message", "")}]
    return graph.invoke(graph_input, config={
        "configurable": {"thread_id": thread_id},
        "recursion_limit": recursion_limit,
    })


def resumir(thread_id: str, resposta: dict, graph=None, db_path: Path = DB_PATH) -> dict:
    graph = graph or get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    normalizada = {"decision": resposta} if isinstance(resposta, str) else resposta
    snapshot = graph.get_state(config)
    if (snapshot and not snapshot.next
            and snapshot.values.get("human_response") == normalizada
            and snapshot.values.get("idempotency_key")):
        action = snapshot.values["pending_action"]
        with CatalogoDB(db_path) as db:
            duplicate = db.registrar_idempotente(
                snapshot.values["user_id"], action["title"], "recomendado",
                f"{snapshot.values['mood']} | {action['reason']}",
                snapshot.values["idempotency_key"],
                preferencia=(
                    f"preferencia explicitamente autorizada: {snapshot.values['mood']}"
                    if action.get("remember_preference") else None
                ),
            )
        return {**snapshot.values, "duplicate_resume": True,
                "duplicate_write_result": duplicate}
    return graph.invoke(Command(resume=normalizada), config={
        **config,
        "recursion_limit": MAX_NODES,
    })


def expirar_pendencia(thread_id: str, graph=None, agora: float | None = None):
    """Rotina de scheduler: rejeita HITL pendente ao vencer 24h, sem escrita."""
    graph = graph or get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if not snapshot or "approval" not in snapshot.next or not snapshot.values.get("pending_action"):
        return None
    action = snapshot.values.get("pending_action", {})
    deadline = action.get("created_at", 0) + action.get("deadline_seconds", APPROVAL_TIMEOUT_SECONDS)
    if (agora if agora is not None else time.time()) < deadline:
        return None
    return graph.invoke(Command(resume={
        "decision": "reject", "reason": "prazo de aprovacao expirado",
    }), config={**config, "recursion_limit": MAX_NODES})


def varrer_pendencias(graph=None, agora: float | None = None,
                      falhas: list[dict] | None = None) -> list[str]:
    """Percorre todas as threads do checkpointer e expira as vencidas.

    E o que o agendador externo (cron, systemd timer) chama; devolve os
    thread_ids rejeitados por prazo para o log de operacao. Uma thread que
    falha (checkpoint corrompido, versao incompativel) vai para `falhas` e a
    varredura segue: sem isso, uma unica thread quebrada impedia a expiracao
    de todas as outras (ASI08, exercicios/aula14).
    """
    graph = graph or get_graph()
    # IDs pela tabela, sem desserializar: listar pelo checkpointer ja quebraria
    # na thread corrompida, antes do laco.
    thread_ids = [row[0] for row in graph.checkpointer.conn.execute(
        "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id")]
    expiradas, erros = [], []
    for thread_id in thread_ids:
        try:
            if expirar_pendencia(thread_id, graph, agora) is not None:
                expiradas.append(thread_id)
        except Exception as exc:
            erros.append({"thread_id": thread_id, "erro": type(exc).__name__})
    if falhas is None and erros:
        # quem nao pediu a lista recebe a falha, depois de as outras threads expirarem
        raise RuntimeError(f"varredura concluida com threads ilegiveis: {erros}")
    if falhas is not None:
        falhas.extend(erros)
    return expiradas


def resultado_publico(state: dict) -> dict:
    """Devolve contrato final ou estrutura de pausa do LangGraph."""
    if state.get("__interrupt__"):
        return {"status": "awaiting_human", "pending_action": state["__interrupt__"][0].value}
    if state.get("decision"):
        return RecommendationResult.model_validate(state["decision"]).model_dump()
    return _result("no_match", "A execucao terminou sem decisao.", next_step="verificar logs")


def _threads_com_titular(graph, user_id: str) -> list[str]:
    return sorted({item.config["configurable"]["thread_id"]
                   for item in graph.checkpointer.list(None)
                   if item.checkpoint.get("channel_values", {}).get("user_id") == user_id})


def ocorrencias_no_checkpoint(graph, user_id: str) -> int:
    """Varre os bytes do checkpoint SQLite, sem depender do campo user_id do estado."""
    agulha = user_id.encode("utf-8")
    total = 0
    for tabela, colunas in (("checkpoints", ("checkpoint", "metadata")), ("writes", ("value",))):
        for coluna in colunas:
            total += graph.checkpointer.conn.execute(
                f"SELECT COUNT(*) FROM {tabela} WHERE instr(CAST({coluna} AS BLOB), ?) > 0",
                (agulha,),
            ).fetchone()[0]
    return total


def remover_titular(user_id: str, graph=None, db_path: Path = DB_PATH) -> dict:
    """Remocao a pedido do titular: memoria SQLite e threads do checkpoint.

    Devolve o que foi apagado e a varredura feita depois, que procura o
    identificador de novo em vez de confiar na contagem do DELETE.
    """
    graph = graph or get_graph()
    threads = _threads_com_titular(graph, user_id)
    # SQLite primeiro, porque e transacional: se falhar, nada saiu e o pedido
    # pode ser repetido. Apagar o checkpoint antes deixava remocao pela metade.
    with CatalogoDB(db_path) as db:
        removidos = db.remover_titular(user_id)
    for thread_id in threads:
        graph.checkpointer.delete_thread(thread_id)
    with CatalogoDB(db_path) as db:
        restante = db.ocorrencias_titular(user_id)
    restante["checkpoint_bytes"] = ocorrencias_no_checkpoint(graph, user_id)
    return {"user_id": user_id, "removidos": {**removidos, "checkpoint_threads": len(threads)},
            "varredura_depois": restante}


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente de recomendacao em LangGraph")
    parser.add_argument("--caso", help="id de caso em dados/cases.json")
    parser.add_argument("--message", help="pedido em texto livre")
    parser.add_argument("--user-id", default="demo-u-001")
    parser.add_argument("--subscriptions", default="Netflix", help="plataformas separadas por virgula")
    parser.add_argument("--max-rating", default="16+")
    parser.add_argument("--session-id", default=f"cli-{uuid.uuid4().hex}")
    args = parser.parse_args()

    if not DB_PATH.exists():
        construir_banco()
    if args.caso:
        cases = json.loads((ROOT / "dados" / "cases.json").read_text(encoding="utf-8"))
        case = next((item for item in cases if item["id"] == args.caso), None)
        if not case:
            parser.error(f"caso inexistente: {args.caso}")
        request: Request = {
            "message": case["query"], "user_id": case["user_id"],
            "subscriptions": case["subscriptions"], "max_rating": case["max_rating"],
            "region": case.get("region", "BR"), "session_id": args.session_id,
            "case_id": case["id"],
        }
    else:
        request = {
            "message": args.message or input("O que voce quer assistir? "),
            "user_id": args.user_id,
            "subscriptions": [p.strip() for p in args.subscriptions.split(",") if p.strip()],
            "max_rating": args.max_rating,
            "region": "BR", "session_id": args.session_id,
        }
    graph = get_graph()
    state = invoke_request(request)
    public = resultado_publico(state)
    if public["status"] == "awaiting_human":
        print(json.dumps(public["pending_action"], ensure_ascii=False, indent=2))
        answer = input("Digite aprovar, rejeitar ou edite com JSON: ").strip()
        if answer.lower() in {"aprovar", "approve"}:
            answer = {"decision": "approve"}
        elif answer.lower() in {"rejeitar", "reject"}:
            answer = {"decision": "reject"}
        else:
            answer = json.loads(answer)
        state = resumir(request["session_id"], answer, graph)
        public = resultado_publico(state)
    print(json.dumps(public, ensure_ascii=False, indent=2))
    print(json.dumps({"retrieval_calls": state.get("retrieval_calls", 0),
                      "trajectory": state.get("trajectory", [])}, ensure_ascii=False, indent=2))
    fechar_graph()


if __name__ == "__main__":
    main()
