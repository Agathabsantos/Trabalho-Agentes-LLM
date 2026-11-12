"""Compara duas rodadas da suite, por classe.

    python -m evals.comparar evals/resultados/<rodada-A> evals/resultados/<rodada-B>
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _juiz() -> str:
    arquivo = ROOT / "evals" / "juiz" / "validacao_resultado.json"
    if not arquivo.exists():
        rubrica = "v1.0.0"
        return f"JUIZ rubrica {rubrica}   nao validado (faltam os rotulos humanos)   limiar 85.0%"
    r = json.loads(arquivo.read_text(encoding="utf-8"))
    estado = "adotado" if r["adotado"] else "NAO adotado"
    return f"JUIZ rubrica {r['rubrica']}   concordancia {r['concordancia']}%   limiar {r['limiar']}%   ({estado})"


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    a, b = (json.loads((Path(p) / "resumo.json").read_text(encoding="utf-8")) for p in sys.argv[1:])
    if a["dataset_versao"] != b["dataset_versao"]:
        print(f"AVISO: datasets diferentes ({a['dataset_versao']} x {b['dataset_versao']})")
    if a["motor"] != b["motor"]:
        print(f"AVISO: motores diferentes ({a['motor']} x {b['motor']}); a comparacao mistura modelo e regras")
    o = b["origens"]
    print(f"DATASET v{b['dataset_versao']}   {b['casos']} casos   (producao {o.get('producao', 0)} · "
          f"desenvolvimento {o.get('desenvolvimento', 0)} · sintetico {o.get('sintetico', 0)})")
    print(_juiz())
    print(f"motor: A={a['motor']} {a.get('modelo') or ''}  B={b['motor']} {b.get('modelo') or ''}")
    print()
    print(f"{'classe':18}{'versão ' + a['versao_sistema']:>14}{'versão ' + b['versao_sistema']:>14}{'delta':>9}")
    for classe in sorted(set(a["classes"]) | set(b["classes"])):
        ta = a["classes"].get(classe, {}).get("taxa")
        tb = b["classes"].get(classe, {}).get("taxa")
        delta = f"{tb - ta:+.1f}" if ta is not None and tb is not None else "-"
        print(f"{classe:18}{str(ta) + '%':>14}{str(tb) + '%':>14}{delta:>9}")
    print(f"{'MÉDIA':18}{str(a['media']) + '%':>14}{str(b['media']) + '%':>14}{b['media'] - a['media']:>+9.1f}")


if __name__ == "__main__":
    main()
