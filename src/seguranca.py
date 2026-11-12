"""Controles aplicados no codigo, fora do prompt (docs/seguranca.md, secao 3.2).

Cada funcao aqui e o ponto de aplicacao de um limite; os testes ficam em
tests/test_controles.py e tentam a acao indevida.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# C1 (ASI04): allowlist do endpoint do modelo.
# A lista fica no codigo, nao no .env: quem consegue trocar LLM_BASE_URL no
# .env nao consegue, pelo mesmo arquivo, ampliar a lista. Fail-closed: sem
# host permitido, nenhuma mensagem sai da maquina.
# ---------------------------------------------------------------------------
HOSTS_PERMITIDOS = frozenset({"api.mistral.ai", "api.openai.com"})


def endpoint_permitido(base_url: str | None) -> tuple[bool, str]:
    """Vazio = padrao da biblioteca openai (api.openai.com). Exige https."""
    if not base_url:
        return True, "padrao da biblioteca (api.openai.com)"
    partes = urlparse(base_url)
    if partes.scheme != "https":
        return False, f"esquema {partes.scheme or 'ausente'} nao e https"
    if partes.hostname not in HOSTS_PERMITIDOS:
        return False, f"host {partes.hostname} fora da allowlist"
    if partes.username or partes.password:
        return False, "credencial embutida na URL"
    return True, partes.hostname


# ---------------------------------------------------------------------------
# C3 (ASI06/ASI09): quarentena de evidencia.
# Um trecho do corpus so pode ser citado ao aprovador se parecer avaliacao,
# nao instrucao. Trecho que fala com quem le, ou longo demais para ser uma
# frase de avaliacao, fica fora da busca e e registrado no trace.
# ---------------------------------------------------------------------------
TAMANHO_MAXIMO_TRECHO = 160
PADROES_INSTRUCAO = re.compile(
    r"\b(aprov\w*|confie|confiar|ignor\w*|sistema|instru\w*|clique|senha|"
    r"sem conferir|verificad\w* pela equipe|assistente|prompt)\b",
    re.IGNORECASE,
)


def motivo_quarentena(texto: str) -> str | None:
    if len(texto) > TAMANHO_MAXIMO_TRECHO:
        return f"trecho com {len(texto)} caracteres (maximo {TAMANHO_MAXIMO_TRECHO})"
    achado = PADROES_INSTRUCAO.search(texto)
    if achado:
        return f"linguagem de instrucao: '{achado.group(0)}'"
    return None


# ---------------------------------------------------------------------------
# C4 (secao 3.4): a memoria longa nao guarda dado pessoal.
# O motivo editado pelo aprovador e texto livre e vai para o historico e os
# episodios. Antes de gravar, telefone, e-mail, CPF e coisa com cara de chave
# viram [removido]. A preferencia semantica ja e montada pelo codigo a partir
# do clima (uma tag fechada), nunca do texto livre.
# ---------------------------------------------------------------------------
PADROES_DADO_PESSOAL = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("cpf", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("telefone", re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}")),
    ("chave", re.compile(r"\b(?:sk|pk|api)[-_][A-Za-z0-9_-]{12,}\b")),
]


def limpar_para_memoria(texto: str) -> tuple[str, list[str]]:
    """Devolve o texto sem dado pessoal e a lista do que foi removido."""
    removidos = []
    for nome, padrao in PADROES_DADO_PESSOAL:
        if padrao.search(texto):
            removidos.append(nome)
            texto = padrao.sub("[removido]", texto)
    return texto, removidos
