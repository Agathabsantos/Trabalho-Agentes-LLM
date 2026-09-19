"""Os dois motores de decisao do agente, com a mesma interface.

O laco em `agent.py` nao sabe qual motor esta rodando: ele pede uma acao e
recebe sempre o mesmo formato.

    {"tipo": "ferramenta", "nome": ..., "args": {...}}   -> chame a ferramenta
    {"tipo": "final", "resposta": {...}}                 -> encerre

MotorModelo      -> decide com o LLM, via tool calling (e o motor da entrega).
MotorHeuristico  -> decide com regras fixas, SEM modelo. Existe para demonstrar
                    o laco quando nao ha chave de API. Todo registro produzido
                    por ele sai carimbado com motor="heuristica_sem_modelo", para
                    que nenhum log possa ser confundido com saida do LLM.
"""

import json
import os

CONTRATO_SAIDA = {
    "status": "recommendation | no_match",
    "title": "string | null",
    "reason": "string, ate 2 frases, citando a evidencia do catalogo",
    "platform": "string | null",
    "confidence": "low | medium | high",
    "missing_info": "string",
    "next_step": "string",
}


class MotorHeuristico:
    """Politica deterministica. Nao le gabarito: so ve o que as ferramentas devolvem."""

    nome = "heuristica_sem_modelo"

    def __init__(self, contexto):
        self.ctx = contexto
        self.fase = "referencia" if contexto.get("titulo_referencia") else "buscar"
        self.candidatos = []
        self.escolhido = None

    def proxima_acao(self, historico_mensagens):
        ultimo = historico_mensagens[-1] if historico_mensagens else {}
        resultado = ultimo.get("resultado", {})

        if self.fase == "referencia":
            self.fase = "avaliar_referencia"
            return {
                "tipo": "ferramenta",
                "nome": "consultar_titulo",
                "args": {"nome": self.ctx["titulo_referencia"]},
            }

        if self.fase == "avaliar_referencia":
            # Politica diante de registro inexistente: nao inventar substituto.
            if resultado.get("erro") == "registro_inexistente":
                return {
                    "tipo": "final",
                    "resposta": {
                        "status": "no_match",
                        "title": None,
                        "reason": f"O titulo de referencia '{self.ctx['titulo_referencia']}' nao existe no catalogo consultado.",
                        "platform": None,
                        "confidence": "low",
                        "missing_info": "o nome correto do titulo que o usuario assistiu",
                        "next_step": "pedir ao usuario que confirme o nome do titulo de referencia",
                    },
                }
            self.fase = "buscar"

        if self.fase == "buscar":
            self.fase = "escolher"
            clima = self.ctx.get("preferred_mood") or self.ctx.get("query", "")
            return {"tipo": "ferramenta", "nome": "buscar_candidatos", "args": {"clima": clima}}

        if self.fase == "escolher":
            self.candidatos = resultado.get("candidatos", [])
            if not self.candidatos:
                return {
                    "tipo": "final",
                    "resposta": {
                        "status": "no_match",
                        "title": None,
                        "reason": "Nenhum titulo do catalogo atende ao mesmo tempo a assinatura, a classificacao do perfil e o clima pedido.",
                        "platform": None,
                        "confidence": "low",
                        "missing_info": "uma plataforma adicional ou um clima alternativo",
                        "next_step": "pedir ao usuario outro clima ou avisar que a assinatura atual nao cobre o pedido",
                    },
                }
            self.escolhido = self.candidatos[0]
            self.fase = "registrar"
            return {
                "tipo": "ferramenta",
                "nome": "registrar_recomendacao",
                "args": {
                    "user_id": self.ctx["user_id"],
                    "titulo": self.escolhido["titulo"],
                    "motivo": f"clima compativel: {', '.join(self.escolhido['clima'])}",
                },
            }

        if self.fase == "registrar":
            if resultado.get("erro"):
                # A ferramenta recusou a escrita: tenta o proximo candidato.
                self.candidatos = self.candidatos[1:]
                if not self.candidatos:
                    return {
                        "tipo": "final",
                        "resposta": {
                            "status": "no_match",
                            "title": None,
                            "reason": f"A gravacao foi recusada ({resultado['erro']}) e nao ha outro candidato valido.",
                            "platform": None,
                            "confidence": "low",
                            "missing_info": "um candidato que passe nas tres invariantes",
                            "next_step": "pedir refinamento ao usuario",
                        },
                    }
                self.escolhido = self.candidatos[0]
                return {
                    "tipo": "ferramenta",
                    "nome": "registrar_recomendacao",
                    "args": {
                        "user_id": self.ctx["user_id"],
                        "titulo": self.escolhido["titulo"],
                        "motivo": f"clima compativel: {', '.join(self.escolhido['clima'])}",
                    },
                }
            return {
                "tipo": "final",
                "resposta": {
                    "status": "recommendation",
                    "title": self.escolhido["titulo"],
                    "reason": f"As tags de clima {self.escolhido['clima']} batem com o que o usuario pediu, e o titulo esta na assinatura.",
                    "platform": resultado.get("plataforma"),
                    "confidence": "medium",
                    "missing_info": "nenhuma",
                    "next_step": "aguardar o usuario aceitar ou recusar",
                },
            }

        return {
            "tipo": "final",
            "resposta": {
                "status": "no_match",
                "title": None,
                "reason": "A politica heuristica chegou a um estado sem saida.",
                "platform": None,
                "confidence": "low",
                "missing_info": "desconhecida",
                "next_step": "encaminhar para um humano",
            },
        }


class MotorModelo:
    """Decide com o LLM, via tool calling da API OpenAI-compativel.

    Nao ha fallback silencioso: se a chamada falhar, a excecao sobe e o laco
    registra a terminacao como erro. Esconder a falha foi o que, na versao
    anterior, fez os logs parecerem saida do modelo sem nunca ter chamado um.
    """

    nome = "modelo"

    def __init__(self, client, modelo, system_prompt, esquema_ferramentas, temperatura=0.2):
        self.client = client
        self.modelo = modelo
        self.esquema = esquema_ferramentas
        self.temperatura = temperatura
        self.mensagens = [{"role": "system", "content": system_prompt}]
        self.tokens_usados = 0
        # Tool calls que o modelo emitiu em PARALELO e ainda nao foram executadas.
        # O laco trata uma ferramenta por passo; quando o modelo pede N de uma
        # vez, a primeira volta agora e as outras esperam aqui. Sem esta fila,
        # o historico ficava com N pedidos e 1 resposta, e o provedor recusava
        # a chamada seguinte com 400 invalid_request_message_order -- foi o que
        # derrubou o ministral-3b em 2 dos 5 casos do benchmark de 18/09/2026.
        self._fila_de_chamadas = []

    def adicionar_pedido_do_usuario(self, texto):
        self.mensagens.append({"role": "user", "content": texto})

    def adicionar_resultado_de_ferramenta(self, tool_call_id, nome, resultado):
        self.mensagens.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": nome,
                "content": json.dumps(resultado, ensure_ascii=False),
            }
        )

    def _empacotar(self, chamada):
        try:
            args = json.loads(chamada.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        return {
            "tipo": "ferramenta",
            "nome": chamada.function.name,
            "args": args,
            "tool_call_id": chamada.id,
        }

    def proxima_acao(self, _historico_mensagens=None):
        # Ha chamada pendente de uma resposta anterior? Entrega sem ir a API:
        # o modelo ja decidiu, falta so executar e responder cada uma.
        if self._fila_de_chamadas:
            return self._empacotar(self._fila_de_chamadas.pop(0))

        resposta = self.client.chat.completions.create(
            model=self.modelo,
            messages=self.mensagens,
            tools=self.esquema,
            tool_choice="auto",
            temperature=self.temperatura,
        )
        uso = getattr(resposta, "usage", None)
        if uso is not None:
            self.tokens_usados += getattr(uso, "total_tokens", 0) or 0

        msg = resposta.choices[0].message
        self.mensagens.append(msg.model_dump(exclude_none=True))

        if msg.tool_calls:
            # Primeira executa agora; as demais (se houver) ficam na fila e
            # saem nas proximas voltas do laco, cada uma com sua resposta.
            self._fila_de_chamadas = list(msg.tool_calls[1:])
            return self._empacotar(msg.tool_calls[0])

        conteudo = (msg.content or "").strip()
        try:
            return {"tipo": "final", "resposta": json.loads(_limpar_cerca(conteudo))}
        except json.JSONDecodeError:
            # Contrato violado: devolve o erro ao modelo como dado, sem derrubar.
            return {
                "tipo": "contrato_violado",
                "bruto": conteudo,
                "como_corrigir": f"Responda APENAS com um objeto JSON no formato {json.dumps(CONTRATO_SAIDA, ensure_ascii=False)}",
            }


def _limpar_cerca(texto):
    """Remove cerca de markdown, que alguns modelos inserem apesar da instrucao."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def construir_client():
    """Cria o client da biblioteca openai apontando para o provedor escolhido.

    Trocar de provedor (OpenAI, Mistral, modelo local) muda apenas as variaveis
    de ambiente, nunca este codigo.
    """
    from openai import OpenAI

    base_url = os.environ.get("LLM_BASE_URL")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY nao esta definida. Copie .env.example para .env e preencha, "
            "ou rode com --sem-modelo para a demonstracao heuristica."
        )
    return OpenAI(base_url=base_url or None, api_key=api_key)
