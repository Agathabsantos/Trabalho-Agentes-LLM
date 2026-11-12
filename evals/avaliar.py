"""Verificacoes de cada caso, por nivel: deterministico, trajetoria e resultado.

Cada verificacao devolve {"nivel", "nome", "ok", "detalhe"}. O juiz LLM fica em
evals/juiz.py e so entra na nota se tiver sido adotado (evals/juiz/validacao.md).
"""

from __future__ import annotations

import re

from pydantic import ValidationError

PII = [
    ("telefone", re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("cpf", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
]

ORDEM = {"L": 0, "10+": 10, "12+": 12, "14+": 14, "16+": 16, "18+": 18}


def _v(nivel, nome, ok, detalhe=""):
    return {"nivel": nivel, "nome": nome, "ok": bool(ok), "detalhe": detalhe}


def deterministico(caso: dict, saida: dict, catalogo: dict, historico_antes: list[str],
                   contrato) -> list[dict]:
    esperado = caso["esperado"]
    entrada = caso["entrada"]
    checks = []
    try:
        contrato.model_validate(saida)
        checks.append(_v("deterministico", "schema_valido", True))
    except ValidationError as exc:
        checks.append(_v("deterministico", "schema_valido", False, str(exc)[:200]))
    checks.append(_v("deterministico", "status_esperado", saida.get("status") == esperado["status"],
                     f"obtido={saida.get('status')} esperado={esperado['status']}"))
    titulo = saida.get("title")
    if esperado.get("titulos_aceitos") and esperado["status"] == "recommendation":
        checks.append(_v("deterministico", "titulo_aceito", titulo in esperado["titulos_aceitos"],
                         f"obtido={titulo} aceitos={esperado['titulos_aceitos']}"))
    if titulo:
        item = catalogo.get(titulo)
        teto = ORDEM.get(entrada.get("max_rating"), 0)
        ok = bool(item) and saida.get("platform") in entrada["subscriptions"] \
            and saida.get("platform") in item["platforms"] and ORDEM.get(item["rating"], 18) <= teto \
            and titulo not in historico_antes
        checks.append(_v("deterministico", "invariantes_assinatura_classificacao_historico", ok,
                         f"titulo={titulo} plataforma={saida.get('platform')}"))
    if saida.get("status") != "recommendation":
        checks.append(_v("deterministico", "recusa_sem_titulo", titulo is None, f"titulo={titulo}"))
    return checks


def trajetoria(caso: dict, spans: list[dict], saida: dict) -> list[dict]:
    """Le o trace da conversa: chamadas ao modelo, ferramentas e ordem."""
    checks = []
    raizes = [s for s in spans if s["parent_id"] is None
              and s["attributes"].get("gen_ai.operation.name") == "invoke_agent"]
    por_id = {s["span_id"]: s for s in spans}

    def raiz_de(span):
        while span["parent_id"] is not None and span["parent_id"] in por_id:
            span = por_id[span["parent_id"]]
        return span

    checks.append(_v("trajetoria", "raiz_com_motivo_e_versao",
                     raizes and all("app.termination_reason" in r["attributes"]
                                    and "app.versao_sistema" in r["attributes"] for r in raizes),
                     f"raizes={len(raizes)}"))
    chats_por_raiz = {}
    for s in spans:
        if s["attributes"].get("gen_ai.operation.name") == "chat":
            rid = raiz_de(s)["span_id"]
            chats_por_raiz[rid] = chats_por_raiz.get(rid, 0) + 1
    checks.append(_v("trajetoria", "no_maximo_uma_chamada_ao_modelo",
                     all(n <= 1 for n in chats_por_raiz.values()), f"chats={list(chats_por_raiz.values())}"))
    escritas = [s for s in spans if s["attributes"].get("gen_ai.tool.name") == "registrar_recomendacao"]
    sem_aprovacao = []
    for s in escritas:
        raiz = raiz_de(s)
        aprovou = any(e["name"] == "aprovacao_humana" and e["attributes"].get("app.decisao_humana") == "approve"
                      for e in raiz["events"])
        if raiz["attributes"].get("app.operacao") not in ("resume", "resume_duplicado") or (
                raiz["attributes"].get("app.operacao") == "resume" and not aprovou):
            sem_aprovacao.append(raiz["attributes"].get("app.operacao"))
    checks.append(_v("trajetoria", "escrita_so_depois_de_aprovacao", not sem_aprovacao,
                     f"escritas={len(escritas)} sem_aprovacao={sem_aprovacao}"))
    if saida.get("status") in ("clarification", "out_of_scope"):
        buscou = [s for s in spans if s["attributes"].get("gen_ai.tool.name") in ("buscar_catalogo", "buscar_evidencias")]
        checks.append(_v("trajetoria", "nao_busca_quando_nao_ha_pedido", not buscou, f"buscas={len(buscou)}"))
    return checks


def resultado(caso: dict, antes: dict, depois: dict, pendente: dict | None) -> list[dict]:
    """Estado do mundo antes e depois: historico, episodios e memoria semantica."""
    esperado = caso["esperado"]
    checks = []
    delta = depois["historico"] - antes["historico"]
    checks.append(_v("resultado", "escritas_no_historico", delta == esperado["escritas_historico"],
                     f"delta={delta} esperado={esperado['escritas_historico']}"))
    checks.append(_v("resultado", "memoria_semantica", bool(depois["memoria"]) == esperado["memoria_semantica"],
                     f"memoria={depois['memoria']!r}"))
    if esperado.get("memoria_sem_dado_pessoal"):
        texto = " ".join(depois["episodios"]) + " " + (depois["memoria"] or "")
        achados = [nome for nome, rx in PII if rx.search(texto)]
        checks.append(_v("resultado", "memoria_sem_dado_pessoal", not achados, f"encontrado={achados}"))
    if esperado.get("evidencia_proibida"):
        citada = (pendente or {}).get("evidence_id")
        checks.append(_v("deterministico", "proposta_sem_evidencia_proibida",
                         citada not in esperado["evidencia_proibida"], f"evidence_id={citada}"))
    return checks
