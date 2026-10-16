"""Recuperacao lexical de evidencias curadas do catalogo.

O caso pede trechos de avaliacao curtos e rastreaveis, nao busca semantica
sobre documentos longos. A recuperacao e lexical com filtros estruturados; os
registros revogados sao excluidos antes do ranking.
"""

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = ROOT / "dados" / "rag_corpus.jsonl"


def tokens(texto: str) -> set[str]:
    sem_acento = "".join(
        char for char in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(char) != "Mn"
    )
    return set(re.findall(r"[a-z0-9]+", sem_acento))


def carregar_corpus(caminho: Path = CORPUS_PATH) -> list[dict]:
    registros = []
    with Path(caminho).open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            if linha.strip():
                registros.append(json.loads(linha))
    return registros


def buscar_evidencias(pergunta: str, titulos: set[str], limite: int = 8,
                      caminho: Path = CORPUS_PATH) -> list[dict]:
    """Retorna evidencias ativas dos titulos permitidos, em ordem deterministica."""
    termos = tokens(pergunta)
    achados = []
    for registro in carregar_corpus(caminho):
        if registro.get("status") != "active" or registro.get("title") not in titulos:
            continue
        sobreposicao = termos & tokens(registro["text"])
        if not sobreposicao:
            continue
        achados.append({
            "id": registro["id"],
            "title": registro["title"],
            "text": registro["text"],
            "source": registro["source"],
            "score": len(sobreposicao),
        })
    achados.sort(key=lambda item: (-item["score"], item["title"], item["id"]))
    return achados[:limite]
