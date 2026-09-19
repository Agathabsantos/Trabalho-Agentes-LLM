"""As 4 ferramentas do agente (requisito 4.1: 2 a 4 ferramentas, ao menos 1 de escrita).

REGRA DESTE MODULO: nenhuma ferramenta levanta excecao para o laco do agente.
Toda falha volta como dado, no formato:

    {"erro": "<codigo>", "detalhe": "<o que aconteceu>", "como_corrigir": "<o que fazer>"}

O campo `como_corrigir` existe porque o enunciado pede "erro de ferramenta que
ENSINA o modelo a se corrigir, nao excecao que derruba". Sem ele o modelo
recebe uma falha e nao sabe qual e a proxima jogada.

| Ferramenta                | Leitura/Escrita | Reversivel | Conversa com    |
|---------------------------|-----------------|------------|-----------------|
| consultar_titulo          | leitura         | n/a        | SQLite: titulos |
| buscar_candidatos         | leitura         | n/a        | SQLite: titulos |
| consultar_historico       | leitura         | n/a        | SQLite: historico |
| registrar_recomendacao    | ESCRITA         | sim        | SQLite: historico |
"""

from catalogo_db import (
    CatalogoDB,
    ErroDeAcesso,
    RegistroNaoEncontrado,
    ORDEM_CLASSIFICACAO,
    normalizar,
)


def _erro(codigo, detalhe, como_corrigir):
    return {"erro": codigo, "detalhe": detalhe, "como_corrigir": como_corrigir}


class Ferramentas:
    """Liga o agente a camada de acesso, carregando o contexto da conta."""

    def __init__(self, db: CatalogoDB, contexto: dict):
        self.db = db
        self.ctx = contexto
        self.escritas = []  # ids gravados nesta execucao, para permitir reversao

    # ---------------- 1. leitura ----------------

    def consultar_titulo(self, nome: str) -> dict:
        """Detalhes de um titulo do catalogo. Erro quando o registro nao existe."""
        if not nome or not str(nome).strip():
            return _erro(
                "argumento_invalido",
                "o nome do titulo veio vazio",
                "chame de novo passando o nome do titulo que o usuario citou",
            )
        try:
            item = self.db.obter_titulo(nome)
        except RegistroNaoEncontrado:
            return _erro(
                "registro_inexistente",
                f"'{nome}' nao existe no catalogo",
                "NAO invente um titulo parecido. Se o titulo de referencia nao existe, "
                "encerre com status no_match e peca ao usuario que confirme o nome.",
            )
        except ErroDeAcesso as exc:
            return _erro("falha_de_acesso", str(exc), "tente a consulta uma unica vez mais")
        return {
            "titulo": item["titulo"],
            "clima": item["clima"],
            "generos": item["generos"],
            "classificacao": item["classificacao"],
            "plataformas": item["plataformas"],
            "sinopse": item["sinopse"],
            "avaliacoes": item["avaliacoes"],
        }

    # ---------------- 2. leitura ----------------

    def buscar_candidatos(self, clima: str, limite: int = 5) -> dict:
        """Candidatos compativeis com o clima, ja filtrados pela conta do usuario.

        O filtro de assinatura, classificacao e historico acontece AQUI, em codigo.
        O modelo nao tem como burlar: ele so ve o que sobrou.
        """
        if not clima or not str(clima).strip():
            return _erro(
                "argumento_invalido",
                "o clima veio vazio",
                "descreva em poucas palavras o que o usuario quer sentir e chame de novo",
            )
        try:
            ja_vistos = [h["titulo"] for h in self.db.historico(self.ctx["user_id"])]
            excluir = set(ja_vistos)
            if self.ctx.get("titulo_referencia"):
                excluir.add(self.ctx["titulo_referencia"])

            termos = normalizar(f"{clima} {self.ctx.get('query', '')}")
            achados = self.db.buscar_por_clima(
                termos_normalizados=termos,
                plataformas=self.ctx.get("subscriptions", []),
                classificacao_max=self.ctx.get("max_rating", "18+"),
                excluir=excluir,
            )
        except ErroDeAcesso as exc:
            return _erro("falha_de_acesso", str(exc), "tente a consulta uma unica vez mais")

        if not achados:
            return {
                "candidatos": [],
                "aviso": "nenhum titulo do catalogo atende assinatura, classificacao e clima ao mesmo tempo",
                "excluidos_por_historico": sorted(ja_vistos),
                "como_corrigir": "NAO relaxe os filtros por conta propria e NAO sugira algo fora da "
                                 "assinatura. Encerre com status no_match.",
            }

        return {
            "candidatos": [
                {
                    "titulo": c["titulo"],
                    "clima": c["clima"],
                    "classificacao": c["classificacao"],
                    "plataforma": c["plataformas_disponiveis"][0],
                    "sinopse": c["sinopse"],
                    "avaliacoes": c["avaliacoes"],
                    "pontuacao_clima": c["pontuacao"],
                }
                for c in achados[:limite]
            ],
            "excluidos_por_historico": sorted(ja_vistos),
        }

    # ---------------- 3. leitura ----------------

    def consultar_historico(self, user_id: str = None) -> dict:
        alvo = user_id or self.ctx["user_id"]
        try:
            registros = self.db.historico(alvo)
        except ErroDeAcesso as exc:
            return _erro("falha_de_acesso", str(exc), "tente a consulta uma unica vez mais")
        return {"user_id": alvo, "historico": registros, "total": len(registros)}

    # ---------------- 4. ESCRITA ----------------

    def registrar_recomendacao(self, user_id: str, titulo: str, motivo: str) -> dict:
        """Grava a recomendacao. Escrita REVERSIVEL (ha `reverter_escritas`).

        Antes de gravar, revalida as 3 invariantes do dominio contra o banco.
        Isso e o verificador no caminho de escrita: mesmo que o modelo tenha
        alucinado um titulo, a gravacao e recusada e ele recebe o motivo.
        """
        alvo = user_id or self.ctx["user_id"]
        if not titulo or not str(titulo).strip():
            return _erro(
                "argumento_invalido",
                "titulo vazio",
                "so registre quando houver um titulo concreto; caso contrario encerre com no_match",
            )

        try:
            item = self.db.obter_titulo(titulo)
        except RegistroNaoEncontrado:
            return _erro(
                "titulo_inexistente",
                f"'{titulo}' nao esta no catalogo",
                "voce so pode registrar um titulo devolvido por buscar_candidatos",
            )
        except ErroDeAcesso as exc:
            return _erro("falha_de_acesso", str(exc), "tente a gravacao uma unica vez mais")

        # invariante 1: tem de estar em plataforma assinada
        assinadas = set(self.ctx.get("subscriptions", []))
        disponiveis = sorted(assinadas & set(item["plataformas"]))
        if not disponiveis:
            return _erro(
                "fora_da_assinatura",
                f"'{titulo}' esta em {item['plataformas']} e o usuario assina {sorted(assinadas)}",
                "escolha outro candidato da lista ou encerre com no_match",
            )

        # invariante 2: tem de respeitar a classificacao do perfil
        teto = ORDEM_CLASSIFICACAO.get(self.ctx.get("max_rating", "18+"), 18)
        if ORDEM_CLASSIFICACAO.get(item["classificacao"], 18) > teto:
            return _erro(
                "classificacao_incompativel",
                f"'{titulo}' e {item['classificacao']} e o perfil aceita ate {self.ctx.get('max_rating')}",
                "escolha outro candidato ou encerre com no_match",
            )

        # invariante 3: nao pode repetir
        ja_vistos = {h["titulo"] for h in self.db.historico(alvo)}
        if item["titulo"] in ja_vistos:
            return _erro(
                "recomendacao_repetida",
                f"'{titulo}' ja foi oferecido a {alvo} antes",
                "escolha o proximo candidato da lista, que ainda nao apareceu para este usuario",
            )

        try:
            resultado = self.db.registrar(alvo, item["titulo"], "recomendado")
        except ErroDeAcesso as exc:
            return _erro("falha_de_acesso", str(exc), "tente a gravacao uma unica vez mais")

        self.escritas.append(resultado["id"])
        return {
            "gravado": True,
            "id": resultado["id"],
            "titulo": item["titulo"],
            "plataforma": disponiveis[0],
            "motivo_registrado": motivo,
            "reversivel": True,
        }

    # ---------------- reversao ----------------

    def reverter_escritas(self):
        """Desfaz o que esta execucao gravou. E o que sustenta 'escrita reversivel'."""
        for registro_id in self.escritas:
            self.db.remover_registro(registro_id)
        revertidas, self.escritas = list(self.escritas), []
        return revertidas


# Esquema das ferramentas no formato tool calling da API OpenAI.
ESQUEMA_FERRAMENTAS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_titulo",
            "description": "Busca um titulo especifico no catalogo pelo nome. Use para o titulo que o usuario citou como referencia.",
            "parameters": {
                "type": "object",
                "properties": {"nome": {"type": "string", "description": "Nome exato do titulo"}},
                "required": ["nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_candidatos",
            "description": "Lista titulos compativeis com um clima, ja filtrados por assinatura, classificacao e historico do usuario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "clima": {"type": "string", "description": "O que o usuario quer sentir, em poucas palavras"},
                    "limite": {"type": "integer", "description": "Maximo de candidatos (padrao 5)"},
                },
                "required": ["clima"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_historico",
            "description": "Lista o que ja foi recomendado ou recusado por este usuario.",
            "parameters": {
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_recomendacao",
            "description": "ESCRITA. Grava a recomendacao escolhida no historico. Recusa titulo fora da assinatura, fora da classificacao ou repetido.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "titulo": {"type": "string"},
                    "motivo": {"type": "string", "description": "Por que este titulo atende o clima pedido"},
                },
                "required": ["titulo", "motivo"],
            },
        },
    },
]
