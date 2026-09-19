"""Camada de acesso a dados do agente (requisito 4.2 da entrega).

Esta camada existe para que o agente NAO leia um arquivo JSON solto no meio do
codigo. Todo acesso a catalogo e historico passa por aqui, contra um banco
SQLite em `dados/catalogo.db`. O banco e construido a partir dos dados
simulados versionados (`dados/streaming_catalog.json` e
`dados/historico_seed.jsonl`), que continuam legiveis por humanos.

O que esta fronteira traz de real para o agente, e que um dicionario Python nao
traria: registro inexistente, consulta que volta vazia, e erro de banco. Na
Parte 2 esta camada e o que vira servidor MCP.
"""

import json
import sqlite3
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "dados" / "catalogo.db"
CATALOGO_SEED = ROOT / "dados" / "streaming_catalog.json"
HISTORICO_SEED = ROOT / "dados" / "historico_seed.jsonl"

ORDEM_CLASSIFICACAO = {"L": 0, "10+": 10, "12+": 12, "14+": 14, "16+": 16, "18+": 18}


class RegistroNaoEncontrado(Exception):
    """O identificador pedido nao existe no banco."""


class ErroDeAcesso(Exception):
    """Falha na camada de acesso (banco ausente, corrompido, indisponivel)."""


def normalizar(texto: str) -> str:
    """Remove acentos e uniformiza separadores, para comparar clima com tags."""
    if not texto:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return sem_acento.lower().replace("-", "_").replace(" ", "_")


class CatalogoDB:
    """Acesso ao catalogo e ao historico. Nenhuma regra de negocio aqui."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise ErroDeAcesso(f"nao foi possivel abrir o banco: {exc}") from exc

    def fechar(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fechar()

    # ---------------- leitura ----------------

    def obter_titulo(self, nome: str) -> dict:
        """Retorna um titulo pelo nome. Levanta RegistroNaoEncontrado se nao existir."""
        cur = self.conn.execute(
            "SELECT * FROM titulos WHERE lower(titulo) = lower(?)", (nome.strip(),)
        )
        linha = cur.fetchone()
        if linha is None:
            raise RegistroNaoEncontrado(nome.strip())
        return self._linha_para_dict(linha)

    def buscar_por_clima(self, termos_normalizados, plataformas, classificacao_max, excluir=()):
        """Candidatos que casam com o clima, ja filtrados por assinatura e classificacao.

        A pontuacao e o numero de tags de clima do titulo presentes no texto do
        pedido. Ordenacao deterministica: pontuacao desc, depois titulo asc.
        """
        teto = ORDEM_CLASSIFICACAO.get(classificacao_max, 18)
        excluir_lower = {e.lower() for e in excluir}
        assinadas = set(plataformas or [])
        resultados = []

        for linha in self.conn.execute("SELECT * FROM titulos ORDER BY titulo ASC"):
            item = self._linha_para_dict(linha)
            if item["titulo"].lower() in excluir_lower:
                continue
            if not assinadas & set(item["plataformas"]):
                continue
            if ORDEM_CLASSIFICACAO.get(item["classificacao"], 18) > teto:
                continue
            pontos = sum(1 for tag in item["clima"] if tag in termos_normalizados)
            if pontos == 0:
                continue
            item["pontuacao"] = pontos
            item["plataformas_disponiveis"] = sorted(assinadas & set(item["plataformas"]))
            resultados.append(item)

        resultados.sort(key=lambda x: (-x["pontuacao"], x["titulo"]))
        return resultados

    def historico(self, user_id: str):
        cur = self.conn.execute(
            "SELECT titulo, desfecho FROM historico WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        )
        return [{"titulo": r["titulo"], "desfecho": r["desfecho"]} for r in cur.fetchall()]

    def climas_conhecidos(self):
        cur = self.conn.execute("SELECT DISTINCT clima FROM titulos")
        tags = set()
        for linha in cur.fetchall():
            tags.update(json.loads(linha["clima"]))
        return sorted(tags)

    # ---------------- escrita ----------------

    def registrar(self, user_id: str, titulo: str, desfecho: str) -> dict:
        """Escrita reversivel: grava a decisao no historico."""
        try:
            cur = self.conn.execute(
                "INSERT INTO historico (user_id, titulo, desfecho) VALUES (?, ?, ?)",
                (user_id, titulo, desfecho),
            )
            self.conn.commit()
        except sqlite3.Error as exc:
            raise ErroDeAcesso(f"falha ao gravar no historico: {exc}") from exc
        return {"gravado": True, "id": cur.lastrowid, "user_id": user_id, "titulo": titulo}

    def remover_registro(self, registro_id: int):
        """Reversao da escrita acima. E o que torna `registrar` reversivel de fato."""
        self.conn.execute("DELETE FROM historico WHERE id = ?", (registro_id,))
        self.conn.commit()

    # ---------------- interno ----------------

    @staticmethod
    def _linha_para_dict(linha) -> dict:
        return {
            "titulo": linha["titulo"],
            "tipo": linha["tipo"],
            "generos": json.loads(linha["generos"]),
            "clima": json.loads(linha["clima"]),
            "plataformas": json.loads(linha["plataformas"]),
            "classificacao": linha["classificacao"],
            "sinopse": linha["sinopse"],
            "avaliacoes": json.loads(linha["avaliacoes"]),
        }


def construir_banco(db_path: Path = DB_PATH, forcar: bool = False) -> Path:
    """Cria o SQLite a partir dos dados simulados versionados.

    Chamado no inicio de toda execucao, para o projeto rodar do zero sem
    nenhum passo manual de migracao.
    """
    db_path = Path(db_path)
    if db_path.exists() and not forcar:
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS titulos (
            titulo         TEXT PRIMARY KEY,
            tipo           TEXT,
            generos        TEXT,
            clima          TEXT,
            plataformas    TEXT,
            classificacao  TEXT,
            sinopse        TEXT,
            avaliacoes     TEXT
        );
        CREATE TABLE IF NOT EXISTS historico (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  TEXT NOT NULL,
            titulo   TEXT NOT NULL,
            desfecho TEXT NOT NULL
        );
        """
    )

    with CATALOGO_SEED.open(encoding="utf-8") as f:
        titulos = json.load(f)["titles"]

    for item in titulos:
        conn.execute(
            "INSERT OR REPLACE INTO titulos VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item["title"],
                item.get("type", ""),
                json.dumps(item.get("genres", []), ensure_ascii=False),
                json.dumps([normalizar(m) for m in item.get("mood", [])], ensure_ascii=False),
                json.dumps(item.get("platforms", []), ensure_ascii=False),
                item.get("rating", ""),
                item.get("synopsis", ""),
                json.dumps(item.get("reviews", []), ensure_ascii=False),
            ),
        )

    if HISTORICO_SEED.exists():
        with HISTORICO_SEED.open(encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                reg = json.loads(linha)
                conn.execute(
                    "INSERT INTO historico (user_id, titulo, desfecho) VALUES (?, ?, ?)",
                    (reg["user_id"], reg["titulo"], reg["desfecho"]),
                )

    conn.commit()
    conn.close()
    return db_path


if __name__ == "__main__":
    caminho = construir_banco()
    with CatalogoDB() as db:
        total = db.conn.execute("SELECT COUNT(*) AS n FROM titulos").fetchone()["n"]
        hist = db.conn.execute("SELECT COUNT(*) AS n FROM historico").fetchone()["n"]
    print(f"Banco criado em {caminho}: {total} titulos, {hist} registros de historico.")
