"""Valida o juiz contra os 20 rotulos humanos de evals/juiz/validacao.json.

    python -m evals.validar_juiz

O limiar foi declarado em docs/evals.md antes de medir. Grava
evals/juiz/validacao_resultado.json com a matriz e a lista de desacordos,
que o grupo classifica um a um (defeito do juiz, da rubrica ou do rotulo).
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
ARQUIVO = ROOT / "evals" / "juiz" / "validacao.json"
SAIDA = ROOT / "evals" / "juiz" / "validacao_resultado.json"
LIMIAR = 85.0  # % de concordancia; declarado em docs/evals.md antes da medicao


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    from evals.juiz import julgar, versao_rubrica

    dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    faltando = [i["id"] for i in dados["itens"] if i["rotulo_humano"] not in ("sustenta", "nao_sustenta")]
    if faltando:
        sys.exit(f"rotulo humano faltando em: {', '.join(faltando)}")
    matriz = {"sustenta": {"sustenta": 0, "nao_sustenta": 0},
              "nao_sustenta": {"sustenta": 0, "nao_sustenta": 0}}  # matriz[humano][juiz]
    linhas = []
    for item in dados["itens"]:
        v = julgar(item["pedido"], item["titulo"], item["trecho"])
        matriz[item["rotulo_humano"]][v["veredito"]] += 1
        linhas.append({"id": item["id"], "humano": item["rotulo_humano"], "juiz": v["veredito"],
                       "justificativa_juiz": v["justificativa"], "nota_humana": item["nota_humana"],
                       "concorda": item["rotulo_humano"] == v["veredito"],
                       "classificacao_desacordo": None if item["rotulo_humano"] == v["veredito"] else "A_CLASSIFICAR"})
        time.sleep(1.5)
    acordos = sum(l["concorda"] for l in linhas)
    resultado = {
        "rubrica": versao_rubrica(), "modelo_juiz": v["modelo"], "itens": len(linhas),
        "concordancia": round(100 * acordos / len(linhas), 1), "limiar": LIMIAR,
        "adotado": 100 * acordos / len(linhas) >= LIMIAR,
        "matriz_humano_x_juiz": matriz, "linhas": linhas,
        "em": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"concordancia {resultado['concordancia']}% (limiar {LIMIAR}%) -> "
          f"{'ADOTADO' if resultado['adotado'] else 'NAO ADOTADO'}")
    print("                juiz=sustenta  juiz=nao_sustenta")
    for humano in ("sustenta", "nao_sustenta"):
        print(f"humano={humano:12} {matriz[humano]['sustenta']:>8} {matriz[humano]['nao_sustenta']:>16}")
    for l in linhas:
        if not l["concorda"]:
            print(f"desacordo {l['id']}: humano={l['humano']} juiz={l['juiz']} | {l['justificativa_juiz']}")


if __name__ == "__main__":
    main()
