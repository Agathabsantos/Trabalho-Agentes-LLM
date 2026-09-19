"""Benchmark minimo dos modelos candidatos (item 3.3 da entrega).

Roda os MESMOS casos, com o MESMO prompt, nos modelos candidatos, e grava a
saida bruta de cada um. O enunciado pede "cinco casos do seu dominio nos tres
candidatos, com o mesmo prompt", e que a tabela venha de execucao real — nao de
leaderboard e nao de expectativa.

Uso:
    python src/benchmark_modelos.py --modelos ministral-3b-2512 ministral-8b-2512 ministral-14b-2512

Saidas:
    logs/benchmark_modelos.json   saida bruta e trajetoria de cada modelo
    docs/modelos-tabela.md        a tabela em Markdown, pronta para colar

Trocar de provedor no meio do benchmark: exporte LLM_BASE_URL e OPENAI_API_KEY
do provedor certo antes de rodar aquele grupo de modelos.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import executar_caso  # noqa: E402
from catalogo_db import CatalogoDB, ORDEM_CLASSIFICACAO, construir_banco  # noqa: E402
from verificador import historico_inicial, verificar_invariantes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "dados" / "cases.json"
SAIDA_JSON = ROOT / "logs" / "benchmark_modelos.json"
SAIDA_TABELA = ROOT / "docs" / "modelos-tabela.md"


def main():
    parser = argparse.ArgumentParser(description="Benchmark minimo dos modelos candidatos")
    parser.add_argument("--modelos", nargs="+", required=True,
                        help="ids dos modelos candidatos, como na API do provedor")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY nao definida. O benchmark exige chamadas reais ao provedor.")

    casos = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    historico = historico_inicial()
    resultados = {}

    for modelo in args.modelos:
        os.environ["MODEL_NAME"] = modelo
        print(f"\n=== {modelo} ===")
        construir_banco()
        linhas = []
        with CatalogoDB() as db:
            catalogo = {
                linha["titulo"]: db._linha_para_dict(linha)
                for linha in db.conn.execute("SELECT * FROM titulos")
            }
            for caso in casos:
                inicio = time.time()
                try:
                    execucao = executar_caso(caso, usar_modelo=True, db=db)
                    erro = None
                except Exception as exc:
                    execucao, erro = None, f"{type(exc).__name__}: {exc}"
                decorrido = round(time.time() - inicio, 2)

                if execucao is None:
                    linhas.append({"caso": caso["id"], "erro": erro, "segundos": decorrido})
                    print(f"  {caso['id']:<34} ERRO: {erro}")
                    continue

                decisao = execucao["decision"]
                esperado = caso["expected_title"] or caso["expected_status"]
                obtido = decisao.get("title") or decisao.get("status")
                violacoes = verificar_invariantes(caso, decisao, catalogo, historico)

                linhas.append({
                    "caso": caso["id"],
                    "esperado": esperado,
                    "obtido": obtido,
                    "acertou": esperado == obtido,
                    "violacoes": violacoes,
                    "passos": execucao["estado_final"]["passos"],
                    "tokens": execucao["estado_final"]["tokens"],
                    "parada": execucao["motivo_da_parada"],
                    "segundos": decorrido,
                    "decisao_bruta": decisao,
                })
                marca = "OK" if esperado == obtido else "FALHOU"
                extra = f"  !! {len(violacoes)} violacao(oes)" if violacoes else ""
                print(f"  {caso['id']:<34} {marca:<8} {obtido:<16} "
                      f"{execucao['estado_final']['tokens']:>6} tok  {decorrido:>5}s{extra}")

        resultados[modelo] = linhas

    SAIDA_JSON.parent.mkdir(exist_ok=True)
    SAIDA_JSON.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- tabela em Markdown, pronta para colar em docs/modelos.md ----
    modelos = list(resultados.keys())
    partes = ["| Caso | Esperado | " + " | ".join(modelos) + " |",
              "|---|---|" + "---|" * len(modelos)]
    for i, caso in enumerate(casos):
        celulas = []
        for modelo in modelos:
            linha = resultados[modelo][i]
            if linha.get("erro"):
                celulas.append("erro")
                continue
            marca = "acerta" if linha["acertou"] else f"erra ({linha['obtido']})"
            if linha["violacoes"]:
                marca += f" + {len(linha['violacoes'])} violacao"
            celulas.append(marca)
        esperado = caso["expected_title"] or caso["expected_status"]
        partes.append(f"| {caso['id']} | {esperado} | " + " | ".join(celulas) + " |")

    partes.append("")
    partes.append("| Modelo | Acertos | Violacoes | Tokens totais | Tempo total |")
    partes.append("|---|---|---|---|---|")
    for modelo in modelos:
        linhas = [l for l in resultados[modelo] if not l.get("erro")]
        partes.append(
            f"| {modelo} | {sum(l['acertou'] for l in linhas)}/{len(casos)} "
            f"| {sum(len(l['violacoes']) for l in linhas)} "
            f"| {sum(l['tokens'] for l in linhas)} "
            f"| {round(sum(l['segundos'] for l in resultados[modelo]), 1)}s |"
        )

    tabela = "\n".join(partes)
    SAIDA_TABELA.write_text(
        f"<!-- Gerado por src/benchmark_modelos.py em {time.strftime('%Y-%m-%d %H:%M')} -->\n"
        f"<!-- Nao editar a mao: cole no docs/modelos.md secao 4 -->\n\n{tabela}\n",
        encoding="utf-8",
    )
    print(f"\n{tabela}\n")
    print(f"Saida bruta: {SAIDA_JSON.relative_to(ROOT)}")
    print(f"Tabela:      {SAIDA_TABELA.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
