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
    # Vereditos ja obtidos ficam num arquivo parcial: se o limite da camada gratis
    # derrubar a rodada, rodar de novo continua de onde parou.
    parcial_arq = SAIDA.with_name("validacao_parcial.json")
    parcial = json.loads(parcial_arq.read_text(encoding="utf-8")) if parcial_arq.exists() else {}
    linhas = []
    for n, item in enumerate(dados["itens"], 1):
        if item["id"] in parcial:
            v = parcial[item["id"]]
        else:
            print(f"[{n}/20] julgando {item['id']}...", flush=True)
            try:
                v = julgar(item["pedido"], item["titulo"], item["trecho"])
            except Exception as exc:
                sys.exit(f"parou em {item['id']} ({type(exc).__name__}). {len(parcial)} de 20 salvos; "
                         "espere alguns minutos e rode de novo para continuar.")
            parcial[item["id"]] = v
            parcial_arq.write_text(json.dumps(parcial, ensure_ascii=False, indent=2), encoding="utf-8")
            time.sleep(31)  # camada gratis da Mistral: ~2 chamadas por minuto
        matriz[item["rotulo_humano"]][v["veredito"]] += 1
        linhas.append({"id": item["id"], "humano": item["rotulo_humano"], "juiz": v["veredito"],
                       "justificativa_juiz": v["justificativa"], "nota_humana": item["nota_humana"],
                       "concorda": item["rotulo_humano"] == v["veredito"],
                       "classificacao_desacordo": None if item["rotulo_humano"] == v["veredito"] else "A_CLASSIFICAR"})
    acordos = sum(l["concorda"] for l in linhas)
    resultado = {
        "rubrica": versao_rubrica(), "modelo_juiz": v["modelo"], "itens": len(linhas),
        "concordancia": round(100 * acordos / len(linhas), 1), "limiar": LIMIAR,
        "adotado": 100 * acordos / len(linhas) >= LIMIAR,
        "matriz_humano_x_juiz": matriz, "linhas": linhas,
        "em": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    parcial_arq.unlink(missing_ok=True)
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
