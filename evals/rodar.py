"""Roda o golden dataset contra o sistema entregue e grava a rodada.

    python -m evals.rodar --versao 1.1.0              # com o modelo do .env
    python -m evals.rodar --versao 1.1.0 --sem-modelo # regras locais, sem chave
    python -m evals.rodar --versao 1.1.0 --juiz       # tambem chama o juiz LLM

A suite usa o mesmo ponto de entrada do CLI (graph.invocar e graph.resumir),
num banco e num checkpoint temporarios reconstruidos do seed. Grava em
evals/resultados/<versao>-<motor>-<data>/: resultados.json (um registro por
caso), resumo.json (nota por classe e por nivel) e traces.jsonl (os spans).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DATASET = ROOT / "evals" / "dataset.json"
RESULTADOS = ROOT / "evals" / "resultados"


def _git() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"commit": run("rev-parse", "HEAD"), "arvore_suja": bool(run("status", "--porcelain"))}


def _estado(db, user_id: str) -> dict:
    historico = db.conn.execute("SELECT COUNT(*) FROM historico WHERE user_id = ?", (user_id,)).fetchone()[0]
    episodios = [r[0] for r in db.conn.execute("SELECT contexto FROM episodios WHERE user_id = ?", (user_id,))]
    memoria = db.obter_preferencia(user_id)
    titulos = [r[0] for r in db.conn.execute("SELECT titulo FROM historico WHERE user_id = ?", (user_id,))]
    return {"historico": historico, "episodios": episodios,
            "memoria": memoria["resumo"] if memoria else None, "titulos": titulos}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--versao", required=True, help="versao do sistema que esta sendo medida")
    parser.add_argument("--sem-modelo", action="store_true", help="forca as regras locais (sem chave)")
    parser.add_argument("--juiz", action="store_true", help="avalia as recomendacoes com o juiz LLM")
    parser.add_argument("--pausa", type=float, default=0.0, help="segundos entre casos (camada gratis: 1.5)")
    parser.add_argument("--casos", nargs="*", help="roda so estes ids")
    args = parser.parse_args()

    if args.sem_modelo:
        os.environ["OPENAI_API_KEY"] = ""
    else:
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
        except ImportError:
            pass
    motor = "modelo" if os.environ.get("OPENAI_API_KEY") else "regras"

    from versao import VERSAO_SISTEMA
    if args.versao != VERSAO_SISTEMA:
        sys.exit(f"--versao {args.versao} mas o codigo e {VERSAO_SISTEMA} (src/versao.py); "
                 "a rodada seria rotulada errado")

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    casos = [c for c in dataset["casos"] if not args.casos or c["id"] in args.casos]
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pasta = RESULTADOS / f"{args.versao}-{motor}-{carimbo}"
    pasta.mkdir(parents=True)
    os.environ["TRACE_FILE"] = str(pasta / "traces.jsonl")

    import telemetria
    telemetria.configurar(pasta / "traces.jsonl")
    from catalogo_db import CatalogoDB, construir_banco
    from graph import (RecommendationResult, create_graph, expirar_pendencia, invocar,
                       resultado_publico, resumir, APPROVAL_TIMEOUT_SECONDS)
    from langgraph.checkpoint.sqlite import SqliteSaver
    from rag import CORPUS_PATH
    from evals import avaliar

    bruto = json.loads((ROOT / "dados" / "streaming_catalog.json").read_text(encoding="utf-8"))
    catalogo = {t["title"]: t for t in next(iter(bruto.values()))}

    registros = []
    with tempfile.TemporaryDirectory(prefix="evals-") as temp:
        temp = Path(temp)
        db_path = temp / "catalogo.db"
        construir_banco(db_path)
        with SqliteSaver.from_conn_string(str(temp / "checkpoints.sqlite")) as checkpointer:
            checkpointer.setup()
            graph = create_graph(db_path, checkpointer)
            for caso in casos:
                entrada = caso["entrada"]
                thread_id = f"{caso['id']}-{carimbo}"
                request = {**{k: v for k, v in entrada.items() if v is not None},
                           "region": "BR", "session_id": thread_id, "case_id": caso["id"]}
                if caso.get("corpus_extra"):
                    corpus = temp / f"corpus-{caso['id']}.jsonl"
                    corpus.write_text(CORPUS_PATH.read_text(encoding="utf-8") + "".join(
                        json.dumps(r, ensure_ascii=False) + "\n" for r in caso["corpus_extra"]), encoding="utf-8")
                    os.environ["RAG_CORPUS"] = str(corpus)
                with CatalogoDB(db_path) as db:
                    antes = _estado(db, entrada["user_id"])
                inicio = time.perf_counter()
                erro = None
                pendente = None
                try:
                    state = invocar(graph, request)
                    publico = resultado_publico(state)
                    pendente = publico.get("pending_action")
                    if pendente and caso.get("aprovacao"):
                        state = resumir(thread_id, caso["aprovacao"], graph, db_path)
                        if caso.get("duplicar"):
                            resumir(thread_id, caso["aprovacao"], graph, db_path)
                    elif pendente and caso.get("expirar"):
                        state = expirar_pendencia(thread_id, graph,
                                                  agora=time.time() + APPROVAL_TIMEOUT_SECONDS + 3600)
                    saida = resultado_publico(state)
                except Exception as exc:  # o caso falha, a suite segue
                    erro = f"{type(exc).__name__}: {exc}"
                    saida = {"status": "excecao", "title": None}
                finally:
                    os.environ.pop("RAG_CORPUS", None)
                duracao = time.perf_counter() - inicio
                with CatalogoDB(db_path) as db:
                    depois = _estado(db, entrada["user_id"])
                registros.append({"caso": caso, "thread_id": thread_id, "saida": saida,
                                  "pendente": pendente, "antes": antes, "depois": depois,
                                  "erro": erro, "duracao_s": round(duracao, 3),
                                  "motor": state.get("decision_source") if erro is None else None})
                print(f"{caso['id']:32} {saida.get('status'):15} {str(saida.get('title')):30} {duracao:.2f}s")
                if args.pausa:
                    time.sleep(args.pausa)

    spans = [json.loads(l) for l in (pasta / "traces.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    raizes_por_conversa = {}
    for s in spans:
        if s["parent_id"] is None:
            raizes_por_conversa.setdefault(s["attributes"].get("gen_ai.conversation.id"), set()).add(s["trace_id"])

    juiz = None
    if args.juiz:
        from evals.juiz import julgar
        juiz = julgar

    for reg in registros:
        caso = reg["caso"]
        traces = raizes_por_conversa.get(reg["thread_id"], set())
        da_conversa = [s for s in spans if s["trace_id"] in traces]
        checks = avaliar.deterministico(caso, reg["saida"], catalogo, reg["antes"]["titulos"], RecommendationResult) \
            if reg["erro"] is None else [avaliar._v("deterministico", "sem_excecao", False, reg["erro"])]
        checks += avaliar.trajetoria(caso, da_conversa, reg["saida"])
        checks += avaliar.resultado(caso, reg["antes"], reg["depois"], reg["pendente"])
        reg["checks"] = checks
        reg["passou"] = all(c["ok"] for c in checks)
        if juiz and reg["saida"].get("status") == "recommendation" and reg["saida"].get("sources"):
            reg["juiz"] = juiz(caso["entrada"]["message"], reg["saida"]["title"],
                               reg["saida"]["sources"][0]["text"])
            if args.pausa:
                time.sleep(args.pausa)
        del reg["antes"]["titulos"], reg["depois"]["titulos"]

    classes = {}
    niveis = {}
    for reg in registros:
        c = classes.setdefault(reg["caso"]["classe"], {"casos": 0, "passou": 0})
        c["casos"] += 1
        c["passou"] += reg["passou"]
        for ch in reg["checks"]:
            n = niveis.setdefault(ch["nivel"], {"verificacoes": 0, "ok": 0})
            n["verificacoes"] += 1
            n["ok"] += ch["ok"]
    origens = {}
    for c in casos:
        origens[c["origem"]] = origens.get(c["origem"], 0) + 1
    resumo = {
        "versao_sistema": args.versao, "motor": motor,
        "modelo": os.environ.get("MODEL_NAME") if motor == "modelo" else None,
        "dataset_versao": dataset["versao"], "casos": len(registros), "origens": origens,
        "classes": {k: {**v, "taxa": round(100 * v["passou"] / v["casos"], 1)} for k, v in sorted(classes.items())},
        "niveis": niveis,
        "media": round(100 * sum(r["passou"] for r in registros) / len(registros), 1),
        "juiz": ({"sustenta": sum(1 for r in registros if r.get("juiz", {}).get("veredito") == "sustenta"),
                  "julgados": sum(1 for r in registros if "juiz" in r)} if args.juiz else None),
        "git": _git(), "inicio": carimbo, "traces": "traces.jsonl",
    }
    (pasta / "resultados.json").write_text(json.dumps(registros, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (pasta / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nrodada gravada em {pasta.relative_to(ROOT)}")
    for k, v in resumo["classes"].items():
        print(f"  {k:16} {v['passou']}/{v['casos']}  {v['taxa']}%")
    print(f"  MEDIA            {resumo['media']}%")
    falhas = [(r["caso"]["id"], [c["nome"] for c in r["checks"] if not c["ok"]]) for r in registros if not r["passou"]]
    for caso_id, nomes in falhas:
        print(f"  falhou {caso_id}: {', '.join(nomes)}")


if __name__ == "__main__":
    main()
