"""Agente de recomendacao — Parte 1.

Laco com estado explicito, orcamento aplicado, terminacao registrada e log de
trajetoria (requisito 4.1 da entrega).

Uso:
    python src/agent.py                  # roda os casos com o MODELO (exige chave)
    python src/agent.py --sem-modelo     # roda com a heuristica, sem chamar LLM
    python src/agent.py --caso caso_simples
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalogo_db import CatalogoDB, construir_banco  # noqa: E402
from ferramentas import ESQUEMA_FERRAMENTAS, Ferramentas  # noqa: E402
from motores import MotorHeuristico, MotorModelo, construir_client  # noqa: E402

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT / "prompts"
CASES_PATH = ROOT / "dados" / "cases.json"
LOG_PATH = ROOT / "logs" / "demo_runs.json"

if load_dotenv is not None:
    load_dotenv(ROOT / ".env")

# Orcamento. Diferente da versao anterior, estes tetos sao COMPARADOS a cada
# volta do laco — nao apenas copiados para o log.
ORCAMENTO = {"max_passos": 8, "max_chamadas_ferramenta": 10, "max_tokens": 12000}


@dataclass
class EstadoAgente:
    """Estado explicito do laco. O que precisa sobreviver de um passo ao outro
    mora aqui, e NAO dentro da lista de mensagens do modelo."""

    caso_id: str
    user_id: str
    titulo_referencia: str = None
    clima_inferido: str = None
    candidatos_vistos: list = field(default_factory=list)
    titulos_recusados_pela_escrita: list = field(default_factory=list)
    passos: int = 0
    chamadas_ferramenta: int = 0
    tokens: int = 0
    erros_de_ferramenta: int = 0
    motivo_da_parada: str = None


def carregar_prompt(nome: str) -> str:
    return (PROMPTS_DIR / nome).read_text(encoding="utf-8")


def montar_pedido(caso: dict) -> str:
    """Preenche o template de mensagem do usuario com o contexto da conta."""
    template = carregar_prompt("user_prompt.txt")
    return template.format(
        query=caso["query"],
        titulo_referencia=caso.get("titulo_referencia") or "(nenhum informado)",
        preferred_mood=caso.get("preferred_mood") or "(nao informado)",
        subscriptions=", ".join(caso.get("subscriptions", [])),
        max_rating=caso.get("max_rating", "18+"),
        user_id=caso["user_id"],
        region=caso.get("region", "BR"),
    )


def executar_caso(caso: dict, usar_modelo: bool, db: CatalogoDB) -> dict:
    estado = EstadoAgente(
        caso_id=caso["id"],
        user_id=caso["user_id"],
        titulo_referencia=caso.get("titulo_referencia"),
    )
    trajetoria = []
    ferramentas = Ferramentas(db, caso)
    pedido = montar_pedido(caso)

    if usar_modelo:
        motor = MotorModelo(
            client=construir_client(),
            modelo=os.environ.get("MODEL_NAME", "ministral-8b-2512"),
            system_prompt=carregar_prompt("system.txt"),
            esquema_ferramentas=ESQUEMA_FERRAMENTAS,
            temperatura=float(os.environ.get("TEMPERATURE") or "0.2"),
        )
        motor.adicionar_pedido_do_usuario(pedido)
    else:
        motor = MotorHeuristico(caso)

    resposta_final = None
    mensagens_locais = []

    while True:
        # --- orcamento: verificado ANTES de cada passo ---
        if estado.passos >= ORCAMENTO["max_passos"]:
            estado.motivo_da_parada = "orcamento_passos_estourado"
            break
        if estado.chamadas_ferramenta >= ORCAMENTO["max_chamadas_ferramenta"]:
            estado.motivo_da_parada = "orcamento_ferramentas_estourado"
            break
        if estado.tokens >= ORCAMENTO["max_tokens"]:
            estado.motivo_da_parada = "orcamento_tokens_estourado"
            break

        estado.passos += 1
        inicio = time.time()

        try:
            acao = motor.proxima_acao(mensagens_locais)
        except Exception as exc:  # falha do provedor: registrada, nunca escondida
            estado.motivo_da_parada = "erro_do_modelo"
            trajetoria.append(
                {
                    "passo": estado.passos,
                    "ferramenta": None,
                    "args": None,
                    "resultado": None,
                    "erro": f"{type(exc).__name__}: {exc}",
                    "ms": round((time.time() - inicio) * 1000),
                }
            )
            break

        if usar_modelo:
            estado.tokens = motor.tokens_usados

        if acao["tipo"] == "final":
            resposta_final = acao["resposta"]
            estado.motivo_da_parada = "resposta_final"
            trajetoria.append(
                {
                    "passo": estado.passos,
                    "ferramenta": None,
                    "args": None,
                    "resultado": resposta_final,
                    "erro": None,
                    "ms": round((time.time() - inicio) * 1000),
                }
            )
            break

        if acao["tipo"] == "contrato_violado":
            estado.erros_de_ferramenta += 1
            trajetoria.append(
                {
                    "passo": estado.passos,
                    "ferramenta": None,
                    "args": None,
                    "resultado": {"bruto": acao["bruto"]},
                    "erro": "contrato_de_saida_violado",
                    "ms": round((time.time() - inicio) * 1000),
                }
            )
            motor.mensagens.append({"role": "user", "content": acao["como_corrigir"]})
            continue

        # --- chamada de ferramenta ---
        nome = acao["nome"]
        args = acao.get("args", {})
        funcao = getattr(ferramentas, nome, None)
        if funcao is None:
            resultado = {
                "erro": "ferramenta_inexistente",
                "detalhe": f"'{nome}' nao existe",
                "como_corrigir": "use apenas: " + ", ".join(
                    f["function"]["name"] for f in ESQUEMA_FERRAMENTAS
                ),
            }
        else:
            resultado = funcao(**args)

        estado.chamadas_ferramenta += 1
        if isinstance(resultado, dict):
            if resultado.get("erro"):
                estado.erros_de_ferramenta += 1
                if resultado["erro"] in ("fora_da_assinatura", "classificacao_incompativel",
                                          "recomendacao_repetida"):
                    estado.titulos_recusados_pela_escrita.append(args.get("titulo"))
            if nome == "buscar_candidatos" and resultado.get("candidatos"):
                estado.clima_inferido = args.get("clima")
                estado.candidatos_vistos = [c["titulo"] for c in resultado["candidatos"]]

        trajetoria.append(
            {
                "passo": estado.passos,
                "ferramenta": nome,
                "args": args,
                "resultado": resultado,
                "erro": resultado.get("erro") if isinstance(resultado, dict) else None,
                "ms": round((time.time() - inicio) * 1000),
            }
        )

        mensagens_locais.append({"ferramenta": nome, "args": args, "resultado": resultado})
        if usar_modelo:
            motor.adicionar_resultado_de_ferramenta(acao["tool_call_id"], nome, resultado)

    if resposta_final is None:
        resposta_final = {
            "status": "no_match",
            "title": None,
            "reason": f"O agente parou por '{estado.motivo_da_parada}' antes de concluir.",
            "platform": None,
            "confidence": "low",
            "missing_info": "a execucao nao chegou a uma decisao",
            "next_step": "encaminhar para um humano",
        }

    return {
        "case_id": caso["id"],
        "descricao": caso.get("descricao"),
        "query": caso["query"],
        "motor": motor.nome,
        "modelo": os.environ.get("MODEL_NAME") if usar_modelo else None,
        "orcamento": ORCAMENTO,
        "estado_final": asdict(estado),
        "motivo_da_parada": estado.motivo_da_parada,
        "trajetoria": trajetoria,
        "decision": resposta_final,
        "status": resposta_final.get("status"),
    }


def checar_pre_requisitos():
    """Falha cedo e com mensagem clara, em vez de traceback no meio da execucao.

    A versao anterior escondia esta falha num `except Exception: pass` e caia
    num fallback com respostas fixas — foi assim que os logs passaram a parecer
    saida do modelo sem nunca ter havido uma chamada. Aqui a falha e explicita.
    """
    problemas = []
    try:
        import openai  # noqa: F401
    except ImportError:
        problemas.append("a biblioteca `openai` nao esta instalada  ->  pip install -r requirements.txt")
    if not os.environ.get("OPENAI_API_KEY"):
        problemas.append("OPENAI_API_KEY nao esta definida       ->  cp .env.example .env e preencha")
    if not problemas:
        return
    print("Nao da para rodar com o modelo:\n", file=sys.stderr)
    for problema in problemas:
        print(f"  - {problema}", file=sys.stderr)
    print("\nPara ver o laco funcionando sem o modelo (nao vale para a entrega):", file=sys.stderr)
    print("  python src/agent.py --sem-modelo\n", file=sys.stderr)
    sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="Agente de recomendacao — Parte 1")
    parser.add_argument("--sem-modelo", action="store_true",
                        help="roda a politica heuristica, sem chamar o LLM")
    parser.add_argument("--caso", help="roda apenas um caso, pelo id")
    args = parser.parse_args()

    usar_modelo = not args.sem_modelo
    if usar_modelo:
        checar_pre_requisitos()
    construir_banco()

    casos = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if args.caso:
        casos = [c for c in casos if c["id"] == args.caso]
        if not casos:
            sys.exit(f"caso '{args.caso}' nao existe em dados/cases.json")

    if not usar_modelo:
        print("=" * 72)
        print("ATENCAO: modo --sem-modelo. NENHUMA chamada ao LLM sera feita.")
        print("Os logs sairao carimbados com motor='heuristica_sem_modelo'.")
        print("Para a entrega, rode sem esta flag, com a chave configurada.")
        print("=" * 72)

    execucoes = []
    with CatalogoDB() as db:
        for caso in casos:
            resultado = executar_caso(caso, usar_modelo, db)
            execucoes.append(resultado)
            marca = resultado["decision"].get("title") or resultado["status"]
            print(f"  {caso['id']:<34} -> {marca:<22} "
                  f"({resultado['estado_final']['passos']} passos, "
                  f"{resultado['estado_final']['chamadas_ferramenta']} ferramentas, "
                  f"parada: {resultado['motivo_da_parada']})")

    # Uma execucao parcial (--caso) nao sobrescreve o log da demonstracao completa,
    # que e o arquivo que o verificador le e que vai para a entrega.
    destino = LOG_PATH if not args.caso else LOG_PATH.parent / f"run_{args.caso}.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(execucoes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(execucoes)} execucao(oes) registrada(s) em {destino.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
