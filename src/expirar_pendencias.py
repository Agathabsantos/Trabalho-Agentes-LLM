"""Rotina do agendador: rejeita aprovacoes humanas pendentes ha mais de 24h.

Uso, a cada hora (exemplo de crontab, a partir da raiz do repositorio):

    0 * * * * cd /caminho/do/repo && .venv/bin/python src/expirar_pendencias.py >> logs/expiracao.log 2>&1

A rotina so rejeita; nunca aprova nem grava historico. Uma pendencia dentro do
prazo continua intacta no checkpoint.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from graph import APPROVAL_TIMEOUT_SECONDS, fechar_graph, get_graph, varrer_pendencias  # noqa: E402


def main() -> None:
    graph = get_graph()
    try:
        expiradas = varrer_pendencias(graph)
    finally:
        fechar_graph()
    print(json.dumps({
        "executado_em": datetime.now(timezone.utc).isoformat(),
        "prazo_segundos": APPROVAL_TIMEOUT_SECONDS,
        "threads_expiradas": expiradas,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
