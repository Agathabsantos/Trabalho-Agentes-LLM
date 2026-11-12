"""Metricas de operacao a partir dos traces das rodadas, com corte por versao.

    python -m evals.metricas evals/resultados/<rodada-1> evals/resultados/<rodada-2> ...

Unidade: a conversa (gen_ai.conversation.id). Uma conversa com aprovacao tem
duas chamadas ao grafo (invoke e resume); o motivo de termino da conversa e o
da ultima chamada. A latencia e a do agente (soma dos spans raiz), sem o tempo
que o humano levou para responder.

Precos: tabela abaixo, em US$ por milhao de tokens. Fonte: pagina do modelo no
OpenRouter, hospedado pela Mistral, consultada em 2026-11-11. Na camada gratis
(plano Experiment) o custo cobrado e zero; a conta mostra o preco de lista.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

PRECOS_USD_POR_MILHAO = {
    "ministral-8b-2512": (0.15, 0.15),
}
BONS = {"respondeu", "rejeitado_humano", "expirado"}
RUINS = {"erro", "orcamento_esgotado"}
SLO_OBJETIVO = 95.0  # % das conversas concluidas sem erro nem orcamento esgotado, janela de 7 dias


def percentil(valores: list[float], p: float) -> float | None:
    if not valores:
        return None
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p / 100
    baixo, alto = math.floor(k), math.ceil(k)
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (k - baixo)


def carregar(pastas: list[Path]) -> list[dict]:
    spans = []
    for pasta in pastas:
        for linha in (pasta / "traces.jsonl").read_text(encoding="utf-8").splitlines():
            if linha.strip():
                span = json.loads(linha)
                span["_rodada"] = pasta.name
                spans.append(span)
    return spans


def calcular(spans: list[dict]) -> dict:
    por_versao = defaultdict(list)
    for s in spans:
        por_versao[s["resource"].get("service.version", "?")].append(s)
    saida = {}
    for versao, lista in sorted(por_versao.items()):
        raizes = [s for s in lista if s["parent_id"] is None
                  and s["attributes"].get("gen_ai.operation.name") == "invoke_agent"]
        conversas = defaultdict(list)
        for r in raizes:
            conversas[(r["_rodada"], r["attributes"].get("gen_ai.conversation.id"))].append(r)
        latencias, custos, finais, motores = [], [], Counter(), Counter()
        tokens_in = tokens_out = 0
        for chave, rs in conversas.items():
            rs.sort(key=lambda r: r["start"])
            latencias.append(sum(r["duration_ms"] for r in rs))
            finais[rs[-1]["attributes"].get("app.termination_reason", "sem_motivo")] += 1
            motores[next((r["attributes"].get("app.decision_source") for r in rs
                          if r["attributes"].get("app.decision_source")), "?")] += 1
            trace_ids = {r["trace_id"] for r in rs}
            custo = 0.0
            for s in lista:
                if s["trace_id"] in trace_ids and s["attributes"].get("gen_ai.operation.name") == "chat":
                    modelo = s["attributes"].get("gen_ai.request.model")
                    ti = s["attributes"].get("gen_ai.usage.input_tokens", 0) or 0
                    to = s["attributes"].get("gen_ai.usage.output_tokens", 0) or 0
                    tokens_in += ti
                    tokens_out += to
                    pin, pout = PRECOS_USD_POR_MILHAO.get(modelo, (0.0, 0.0))
                    custo += (ti * pin + to * pout) / 1e6
            custos.append(custo)
        ferramentas = defaultdict(lambda: {"chamadas": 0, "erros": 0})
        for s in lista:
            nome = s["attributes"].get("gen_ai.tool.name")
            if nome:
                ferramentas[nome]["chamadas"] += 1
                ferramentas[nome]["erros"] += s["status"] == "ERROR"
        chats = [s for s in lista if s["attributes"].get("gen_ai.operation.name") == "chat"]
        validos = sum(n for m, n in finais.items() if m != "aguardando_humano")
        bons = sum(n for m, n in finais.items() if m in BONS)
        sli = round(100 * bons / validos, 1) if validos else None
        orcamento = 100 - SLO_OBJETIVO
        consumido = round(100 * (100 - sli) / orcamento, 1) if sli is not None else None
        saida[versao] = {
            "rodadas": sorted({s["_rodada"] for s in lista}),
            "conversas": len(conversas), "chamadas_ao_grafo": len(raizes),
            "motores": dict(motores),
            "latencia_ms": {"p50": round(percentil(latencias, 50), 1), "p95": round(percentil(latencias, 95), 1)},
            "chamadas_ao_modelo": len(chats),
            "chat_latencia_ms": {"p50": percentil([c["duration_ms"] for c in chats], 50),
                                 "p95": percentil([c["duration_ms"] for c in chats], 95)},
            "tokens": {"entrada": tokens_in, "saida": tokens_out},
            "custo_usd_por_conversa": {"media": round(sum(custos) / len(custos), 8) if custos else 0,
                                       "p95": round(percentil(custos, 95) or 0, 8),
                                       "por_1000_conversas": round(1000 * sum(custos) / len(custos), 4) if custos else 0},
            "motivos_de_termino": dict(finais),
            "ferramentas": {k: {**v, "taxa_erro": round(100 * v["erros"] / v["chamadas"], 1)}
                            for k, v in sorted(ferramentas.items())},
            "slo": {"sli": sli, "bons": bons, "validos": validos, "objetivo": SLO_OBJETIVO,
                    "orcamento_de_erro_consumido_pct": consumido,
                    "violado": sli is not None and sli < SLO_OBJETIVO},
        }
    return saida


def main() -> None:
    pastas = [Path(p) for p in sys.argv[1:]]
    if not pastas:
        sys.exit(__doc__)
    resultado = calcular(carregar(pastas))
    for versao, m in resultado.items():
        print(f"\n== versao {versao}  ({m['conversas']} conversas, {m['chamadas_ao_grafo']} chamadas ao grafo, motores {m['motores']})")
        print(f"latencia do agente por conversa: p50 {m['latencia_ms']['p50']} ms · p95 {m['latencia_ms']['p95']} ms")
        if m["chamadas_ao_modelo"]:
            print(f"chamada ao modelo: p50 {m['chat_latencia_ms']['p50']:.0f} ms · p95 {m['chat_latencia_ms']['p95']:.0f} ms "
                  f"({m['chamadas_ao_modelo']} chamadas, {m['tokens']['entrada']} tokens in, {m['tokens']['saida']} out)")
        c = m["custo_usd_por_conversa"]
        print(f"custo por conversa: media US$ {c['media']:.6f} · p95 US$ {c['p95']:.6f} · US$ {c['por_1000_conversas']} por 1000")
        print("motivos de termino:", ", ".join(f"{k} {v}" for k, v in sorted(m["motivos_de_termino"].items())))
        print("ferramentas:", ", ".join(f"{k} {v['erros']}/{v['chamadas']} erro" for k, v in m["ferramentas"].items()))
        s = m["slo"]
        print(f"SLO: SLI {s['sli']}% ({s['bons']}/{s['validos']}) · objetivo {s['objetivo']}% · "
              f"orcamento consumido {s['orcamento_de_erro_consumido_pct']}% · {'VIOLADO' if s['violado'] else 'cumprido'}")
    destino = Path("evals/resultados/metricas.json")
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\ngravado em {destino}")


if __name__ == "__main__":
    main()
