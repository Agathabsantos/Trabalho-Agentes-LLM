"""Remocao a pedido do titular (enunciado §5.4): apaga e depois varre.

    python src/remover_titular.py <user_id>

Apaga historico, episodios, indice FTS, preferencia semantica, chaves
idempotentes e as threads do checkpoint desse user_id. Depois varre as mesmas
estruturas e os arquivos de logs/ procurando o identificador. Os logs sao
versionados no git: o script so aponta onde o id aparece, porque reescrever
historico do repositorio e decisao de quem mantem o projeto.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from graph import fechar_graph, get_graph, remover_titular  # noqa: E402


def ocorrencias_em_logs(user_id: str) -> dict:
    return {str(path.relative_to(ROOT)): texto.count(user_id)
            for path in sorted((ROOT / "logs").glob("*"))
            if path.is_file() and user_id in (texto := path.read_text(encoding="utf-8", errors="ignore"))}


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("uso: python src/remover_titular.py <user_id>")
    user_id = sys.argv[1]
    graph = get_graph()
    try:
        resultado = remover_titular(user_id, graph)
    finally:
        fechar_graph()
    resultado["varredura_depois"]["logs"] = ocorrencias_em_logs(user_id)
    print(json.dumps({"executado_em": datetime.now(timezone.utc).isoformat(), **resultado},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
