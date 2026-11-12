"""Telemetria do agente nas convencoes semanticas GenAI do OpenTelemetry.

Cada chamada ao grafo abre um span raiz `invoke_agent recomendador`; a chamada
ao modelo abre `chat <modelo>`; cada ferramenta (consulta ao catalogo, busca no
corpus, leitura da memoria, escrita no historico) abre `execute_tool <nome>`.

Destino: um arquivo JSONL por processo, em `logs/traces/` (ou no caminho de
TRACE_FILE). Cada linha e um span. `python src/ver_trace.py` mostra a arvore.

O trace e tambem o registro da decisao (docs/model-card.md, campo Registro e
retencao): entrada, trechos recuperados, versoes, ferramentas, saida, motivo de
termino e aprovacao humana ficam nos atributos.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Status, StatusCode

from versao import VERSAO_SISTEMA

ROOT = Path(__file__).resolve().parent.parent
AGENTE = "recomendador"

# Motivos de termino (taxonomia da Aula 05, adaptada ao grafo):
#   respondeu           o grafo chegou a uma decisao de contrato (recomendacao,
#                       recusa, pergunta de esclarecimento ou fora de escopo)
#   aguardando_humano   parou no interrupt, esperando o responsavel pela conta
#   rejeitado_humano    o responsavel rejeitou ou a edicao foi invalida
#   expirado            a pendencia venceu o prazo de 24h sem resposta
#   orcamento_esgotado  passou do teto de tempo ou de passos do grafo
#   erro                excecao, falha do provedor ou saida invalida do modelo
MOTIVOS = ("respondeu", "aguardando_humano", "rejeitado_humano", "expirado",
           "orcamento_esgotado", "erro")


class ExportadorJSONL(SpanExporter):
    """Grava cada span como uma linha JSON; o arquivo e o destino consultavel."""

    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)
        self._lock = threading.Lock()

    def export(self, spans):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.caminho.open("a", encoding="utf-8") as arquivo:
            for span in spans:
                arquivo.write(json.dumps(_span_para_dict(span), ensure_ascii=False) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self):
        return None


def _span_para_dict(span) -> dict:
    contexto = span.get_span_context()
    return {
        "trace_id": format(contexto.trace_id, "032x"),
        "span_id": format(contexto.span_id, "016x"),
        "parent_id": format(span.parent.span_id, "016x") if span.parent else None,
        "name": span.name,
        "start": span.start_time,
        "end": span.end_time,
        "duration_ms": round((span.end_time - span.start_time) / 1e6, 3),
        "status": span.status.status_code.name,
        "attributes": dict(span.attributes or {}),
        "events": [{"name": e.name, "timestamp": e.timestamp,
                    "attributes": dict(e.attributes or {})} for e in span.events],
        "resource": dict(span.resource.attributes),
    }


_provider: TracerProvider | None = None
_arquivo_atual: Path | None = None


def caminho_padrao() -> Path:
    if os.environ.get("TRACE_FILE"):
        return Path(os.environ["TRACE_FILE"])
    dia = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return ROOT / "logs" / "traces" / f"traces-{dia}.jsonl"


def configurar(caminho: Path | None = None) -> Path:
    """Liga a exportacao para `caminho`. Pode ser chamada de novo para trocar o arquivo."""
    global _provider, _arquivo_atual
    destino = Path(caminho) if caminho else caminho_padrao()
    if _provider is not None and destino == _arquivo_atual:
        return destino
    if _provider is not None:
        _provider.shutdown()
    _provider = TracerProvider(resource=Resource.create({
        "service.name": "agente-recomendacao",
        "service.version": VERSAO_SISTEMA,
    }))
    _provider.add_span_processor(SimpleSpanProcessor(ExportadorJSONL(destino)))
    _arquivo_atual = destino
    return destino


def tracer():
    if _provider is None:
        configurar()
    return _provider.get_tracer("agente-recomendacao", VERSAO_SISTEMA)


def _limpo(atributos: dict) -> dict:
    """OpenTelemetry so aceita escalares e listas; dict vira JSON e None sai."""
    saida = {}
    for chave, valor in atributos.items():
        if valor is None:
            continue
        if isinstance(valor, (dict, list, tuple)) and not (
                isinstance(valor, (list, tuple)) and all(isinstance(v, str) for v in valor)):
            valor = json.dumps(valor, ensure_ascii=False, default=str)
        saida[chave] = valor
    return saida


@contextmanager
def span_ferramenta(nome: str, argumentos: dict):
    """Span `execute_tool <nome>`. A excecao marca erro no span e sobe."""
    with tracer().start_as_current_span(f"execute_tool {nome}", attributes=_limpo({
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": nome,
        "gen_ai.tool.type": "function",
        "gen_ai.tool.call.arguments": argumentos,
    })) as span:
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            span.set_attribute("error.type", type(exc).__name__)
            raise


def resultado_ferramenta(span, resultado) -> None:
    span.set_attribute("gen_ai.tool.call.result",
                       json.dumps(resultado, ensure_ascii=False, default=str)[:2000])


@contextmanager
def span_chat(modelo: str, provedor: str, atributos: dict):
    with tracer().start_as_current_span(f"chat {modelo}", attributes=_limpo({
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": provedor,
        "gen_ai.request.model": modelo,
        **atributos,
    })) as span:
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            span.set_attribute("error.type", type(exc).__name__)
            raise


def provedor_de(base_url: str | None) -> str:
    base = (base_url or "").lower()
    if "mistral" in base:
        return "mistral_ai"
    if not base or "openai.com" in base:
        return "openai"
    return "desconhecido"


@contextmanager
def span_raiz(operacao: str, thread_id: str, atributos: dict):
    """Span `invoke_agent recomendador`, um por chamada ao grafo.

    `operacao` e "invoke" (pedido novo), "resume" (resposta do aprovador) ou
    "expire" (rotina de expiracao). As chamadas da mesma conversa compartilham
    gen_ai.conversation.id = thread_id.
    """
    with tracer().start_as_current_span(f"invoke_agent {AGENTE}", attributes=_limpo({
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": AGENTE,
        "gen_ai.conversation.id": thread_id,
        "app.versao_sistema": VERSAO_SISTEMA,
        "app.operacao": operacao,
        **atributos,
    })) as span:
        yield span


def fechar_raiz(span, state: dict | None, *, excecao: Exception | None = None) -> str:
    """Grava saida, motivo de termino e o registro da decisao no span raiz."""
    motivo = motivo_termino(state or {}, excecao)
    span.set_attribute("app.termination_reason", motivo)
    if excecao is not None:
        span.set_status(Status(StatusCode.ERROR, type(excecao).__name__))
        span.set_attribute("error.type", type(excecao).__name__)
        return motivo
    state = state or {}
    decisao = state.get("decision") or {}
    pendente = state["__interrupt__"][0].value if state.get("__interrupt__") else None
    span.set_attributes(_limpo({
        "app.user_id": state.get("user_id"),
        "app.mood": state.get("mood") or None,
        "app.decision_source": state.get("decision_source"),
        "gen_ai.request.model": state.get("model_name"),
        "app.prompt.sha256": (state.get("prompt_manifest") or {}).get("interpret_request.txt"),
        "app.prompt.versao": state.get("prompt_version"),
        "app.model_calls": state.get("model_calls", 0),
        "gen_ai.usage.input_tokens": state.get("model_input_tokens", 0),
        "gen_ai.usage.output_tokens": state.get("model_tokens", 0),
        "app.retrieval.ids": [item["id"] for item in state.get("current_evidence", [])],
        "app.candidatos": state.get("candidate_titles"),
        "app.decision.status": decisao.get("status") if not pendente else "awaiting_human",
        "app.decision.title": decisao.get("title") or (pendente or {}).get("title"),
        "app.decision.reason": decisao.get("reason") or (pendente or {}).get("reason"),
        "app.decision.sources": [s["id"] for s in decisao.get("sources", [])],
        "app.pending_action": pendente,
        "app.idempotency_key": state.get("idempotency_key"),
        "app.persist_result": state.get("persist_result"),
        "app.controles": state.get("controles"),
    }))
    resposta = state.get("human_response")
    if resposta is not None and not pendente:
        span.add_event("aprovacao_humana", _limpo({
            "app.aprovador": resposta.get("approver") or "nao_identificado",
            "app.decisao_humana": resposta.get("decision"),
            "app.titulo_aprovado": (state.get("pending_action") or {}).get("title"),
            "app.editado": bool(resposta.get("title") or resposta.get("reason")),
            "app.motivo_humano": resposta.get("reason"),
            "app.em": datetime.now(timezone.utc).isoformat(),
        }))
    return motivo


def motivo_termino(state: dict, excecao: Exception | None = None) -> str:
    if excecao is not None:
        nome = type(excecao).__name__
        return "orcamento_esgotado" if nome == "GraphRecursionError" else "erro"
    if state.get("__interrupt__"):
        return "aguardando_humano"
    if any(e.get("result") == "timeout" for e in state.get("trajectory", [])):
        return "orcamento_esgotado"
    status = (state.get("decision") or {}).get("status")
    if status == "error":
        return "erro"
    if status == "rejected":
        resposta = state.get("human_response") or {}
        return "expirado" if "expirado" in str(resposta.get("reason", "")) else "rejeitado_humano"
    if status:
        return "respondeu"
    return "erro"
