"""Mostra os traces gravados em logs/traces/ como arvore de spans.

    python src/ver_trace.py                      # ultimas 5 conversas do arquivo mais novo
    python src/ver_trace.py --conversa <thread>  # todas as chamadas de uma conversa
    python src/ver_trace.py --arquivo <jsonl> --todos
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RAIZ_CHAVES = ("app.versao_sistema", "app.operacao", "app.termination_reason",
               "app.input.message", "app.decision.status", "app.decision.title",
               "app.retrieval.ids", "gen_ai.request.model", "app.prompt.versao",
               "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens")


def carregar(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8") as arquivo:
        return [json.loads(linha) for linha in arquivo if linha.strip()]


def imprimir(spans: list[dict]) -> None:
    filhos = defaultdict(list)
    for span in spans:
        filhos[span["parent_id"]].append(span)

    def mostrar(span, nivel):
        attrs = span["attributes"]
        marca = " [ERRO]" if span["status"] == "ERROR" else ""
        print(f"{'  ' * nivel}{span['name']}  {span['duration_ms']:.1f} ms{marca}")
        if attrs.get("gen_ai.operation.name") == "invoke_agent":
            for chave in RAIZ_CHAVES:
                if chave in attrs:
                    print(f"{'  ' * nivel}  · {chave} = {attrs[chave]}")
            for evento in span["events"]:
                print(f"{'  ' * nivel}  ⚑ {evento['name']}: {evento['attributes']}")
        elif "gen_ai.tool.call.result" in attrs:
            print(f"{'  ' * nivel}  → {attrs['gen_ai.tool.call.result'][:160]}")
        elif attrs.get("gen_ai.operation.name") == "chat":
            print(f"{'  ' * nivel}  tokens in={attrs.get('gen_ai.usage.input_tokens')} "
                  f"out={attrs.get('gen_ai.usage.output_tokens')}")
        for filho in sorted(filhos[span["span_id"]], key=lambda s: s["start"]):
            mostrar(filho, nivel + 1)

    for raiz in sorted(filhos[None], key=lambda s: s["start"]):
        print(f"\ntrace {raiz['trace_id']}  conversa={raiz['attributes'].get('gen_ai.conversation.id')}")
        mostrar(raiz, 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arquivo", type=Path)
    parser.add_argument("--conversa")
    parser.add_argument("--todos", action="store_true")
    args = parser.parse_args()
    caminho = args.arquivo
    if caminho is None:
        arquivos = sorted((ROOT / "logs" / "traces").glob("*.jsonl"),
                          key=lambda p: p.stat().st_mtime)
        if not arquivos:
            raise SystemExit("nenhum trace em logs/traces/; rode o agente primeiro")
        caminho = arquivos[-1]
    spans = carregar(caminho)
    raizes = [s for s in spans if s["parent_id"] is None]
    if args.conversa:
        ids = {s["trace_id"] for s in raizes
               if s["attributes"].get("gen_ai.conversation.id") == args.conversa}
    elif args.todos:
        ids = {s["trace_id"] for s in raizes}
    else:
        conversas = []
        for s in sorted(raizes, key=lambda s: s["start"]):
            c = s["attributes"].get("gen_ai.conversation.id")
            if c not in conversas:
                conversas.append(c)
        ultimas = set(conversas[-5:])
        ids = {s["trace_id"] for s in raizes
               if s["attributes"].get("gen_ai.conversation.id") in ultimas}
    print(f"arquivo: {caminho}")
    imprimir([s for s in spans if s["trace_id"] in ids])


if __name__ == "__main__":
    main()
