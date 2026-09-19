"""Verificador da saida do agente (item 2.6 e 2.7 da entrega).

Confere DUAS coisas diferentes, porque o custo do erro e assimetrico:

  A) ACERTO — a decisao bate com o gabarito rotulado a mao em dados/cases.json.
     Erro aqui custa uma recomendacao ruim: o usuario ignora e pede outra.

  B) INVARIANTES — o agente nunca pode recomendar fora da assinatura, acima da
     classificacao do perfil, ou repetir titulo ja oferecido. Erro aqui custa
     confianca: o usuario clica e descobre que nao pode assistir, ou ve a mesma
     sugestao pela terceira vez.

Criterio de sucesso declarado: >= 4 de 5 acertos E 0 violacoes de invariante.
Uma violacao de invariante reprova a execucao inteira, mesmo com 5/5 acertos.

Uso:
    python src/verificador.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalogo_db import CatalogoDB, ORDEM_CLASSIFICACAO, construir_banco  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "dados" / "cases.json"
LOG_PATH = ROOT / "logs" / "demo_runs.json"
HISTORICO_SEED = ROOT / "dados" / "historico_seed.jsonl"

MINIMO_ACERTOS = 4


def historico_inicial():
    """O historico ANTES da execucao. E contra ele que 'nao repetir' e medido."""
    por_usuario = {}
    if HISTORICO_SEED.exists():
        for linha in HISTORICO_SEED.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                reg = json.loads(linha)
                por_usuario.setdefault(reg["user_id"], set()).add(reg["titulo"])
    return por_usuario


def verificar_invariantes(caso, decisao, catalogo, historico):
    """Devolve a lista de invariantes violadas por esta decisao."""
    violacoes = []
    titulo = decisao.get("title")
    if not titulo:
        return violacoes  # no_match nao viola nada

    item = catalogo.get(titulo)
    if item is None:
        return [f"titulo '{titulo}' nao existe no catalogo (alucinacao)"]

    assinadas = set(caso.get("subscriptions", []))
    if not assinadas & set(item["plataformas"]):
        violacoes.append(
            f"'{titulo}' esta em {item['plataformas']}, usuario assina {sorted(assinadas)}"
        )

    teto = ORDEM_CLASSIFICACAO.get(caso.get("max_rating", "18+"), 18)
    if ORDEM_CLASSIFICACAO.get(item["classificacao"], 18) > teto:
        violacoes.append(
            f"'{titulo}' e {item['classificacao']}, perfil aceita ate {caso.get('max_rating')}"
        )

    if titulo in historico.get(caso["user_id"], set()):
        violacoes.append(f"'{titulo}' ja tinha sido oferecido a {caso['user_id']}")

    if decisao.get("platform") and decisao["platform"] not in assinadas:
        violacoes.append(f"plataforma informada '{decisao['platform']}' nao esta na assinatura")

    return violacoes


def autoteste():
    """Prova que o verificador nao e vazio: injeta 4 decisoes sabidamente
    erradas e exige que TODAS sejam pegas. Um verificador que aprova tudo e
    pior que nenhum, porque da falsa seguranca."""
    construir_banco()
    with CatalogoDB() as db:
        catalogo = {
            linha["titulo"]: db._linha_para_dict(linha)
            for linha in db.conn.execute("SELECT * FROM titulos")
        }
    historico = historico_inicial()

    sondas = [
        ("fora da assinatura",
         {"user_id": "u-001", "subscriptions": ["Netflix"], "max_rating": "16+"},
         {"title": "The Bear", "platform": "Hulu"}),
        ("acima da classificacao",
         {"user_id": "u-004", "subscriptions": ["Prime Video"], "max_rating": "10+"},
         {"title": "Severance", "platform": "Prime Video"}),
        ("recomendacao repetida",
         {"user_id": "u-005", "subscriptions": ["Netflix"], "max_rating": "16+"},
         {"title": "Dark", "platform": "Netflix"}),
        ("titulo alucinado",
         {"user_id": "u-001", "subscriptions": ["Netflix"], "max_rating": "16+"},
         {"title": "O Enigma de Kessler", "platform": "Netflix"}),
    ]

    print("\nAUTOTESTE DO VERIFICADOR (decisoes propositalmente erradas)")
    print("-" * 72)
    falhou = False
    for nome, caso, decisao in sondas:
        violacoes = verificar_invariantes(caso, decisao, catalogo, historico)
        pegou = bool(violacoes)
        falhou |= not pegou
        print(f"  {nome:<26} -> {'PEGOU' if pegou else 'PASSOU BATIDO (bug!)'}"
              f"  {violacoes[0] if violacoes else ''}")

    sonda_ok = verificar_invariantes(
        {"user_id": "u-001", "subscriptions": ["Netflix"], "max_rating": "16+"},
        {"title": "Dark", "platform": "Netflix"}, catalogo, historico)
    if sonda_ok:
        falhou = True
        print(f"  {'decisao valida':<26} -> REPROVOU SEM MOTIVO (bug!) {sonda_ok}")
    else:
        print(f"  {'decisao valida':<26} -> aprovou, correto")

    print("-" * 72)
    print("AUTOTESTE: " + ("FALHOU" if falhou else "OK — o verificador pega os 4 erros"))
    return 1 if falhou else 0


def main():
    if "--autoteste" in sys.argv:
        sys.exit(autoteste())

    if not LOG_PATH.exists():
        sys.exit("logs/demo_runs.json nao existe. Rode `python src/agent.py` antes.")

    casos = {c["id"]: c for c in json.loads(CASES_PATH.read_text(encoding="utf-8"))}
    execucoes = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    historico = historico_inicial()

    construir_banco()
    with CatalogoDB() as db:
        catalogo = {
            linha["titulo"]: db._linha_para_dict(linha)
            for linha in db.conn.execute("SELECT * FROM titulos")
        }

    motores = {e.get("motor") for e in execucoes}
    print()
    if motores == {"heuristica_sem_modelo"}:
        print("!! Estes logs foram produzidos SEM o modelo (modo --sem-modelo).")
        print("!! Para a entrega, rode `python src/agent.py` com a chave configurada.")
        print()

    acertos = 0
    todas_violacoes = []

    print(f"{'CASO':<34}{'ESPERADO':<16}{'OBTIDO':<16}{'ACERTO':<9}INVARIANTES")
    print("-" * 92)

    for execucao in execucoes:
        caso = casos.get(execucao["case_id"])
        if caso is None:
            print(f"{execucao['case_id']:<34}(caso removido de cases.json)")
            continue

        decisao = execucao["decision"]
        esperado = caso["expected_title"] or caso["expected_status"]
        obtido = decisao.get("title") or decisao.get("status")
        acertou = esperado == obtido
        acertos += acertou

        violacoes = verificar_invariantes(caso, decisao, catalogo, historico)
        todas_violacoes.extend((execucao["case_id"], v) for v in violacoes)

        print(
            f"{execucao['case_id']:<34}{str(esperado):<16}{str(obtido):<16}"
            f"{'OK' if acertou else 'FALHOU':<9}"
            f"{'ok' if not violacoes else '; '.join(violacoes)}"
        )

    total = len(execucoes)
    print("-" * 92)
    print(f"ACERTOS:     {acertos}/{total}   (minimo exigido: {MINIMO_ACERTOS}/{total})")
    print(f"INVARIANTES: {len(todas_violacoes)} violacoes   (maximo tolerado: 0)")

    aprovado = acertos >= MINIMO_ACERTOS and not todas_violacoes
    print(f"\nRESULTADO: {'APROVADO' if aprovado else 'REPROVADO'}\n")

    if todas_violacoes:
        print("Violacoes encontradas:")
        for caso_id, violacao in todas_violacoes:
            print(f"  - [{caso_id}] {violacao}")
        print()

    sys.exit(0 if aprovado else 1)


if __name__ == "__main__":
    main()
