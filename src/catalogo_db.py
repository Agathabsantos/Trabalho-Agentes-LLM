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


def _ensure_memory_schema(conn: sqlite3.Connection) -> None:
    """Migra bancos da Parte 1 sem apagar histórico já persistido."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS acoes_idempotentes (
            chave TEXT PRIMARY KEY,
            history_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS episodios (
            user_id TEXT NOT NULL,
            titulo TEXT NOT NULL,
            contexto TEXT NOT NULL,
            chave TEXT PRIMARY KEY,
            criado_em TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS episodios_fts USING fts5(
            contexto, user_id UNINDEXED, titulo UNINDEXED, chave UNINDEXED
        );
        CREATE TABLE IF NOT EXISTS memoria_semantica (
            user_id TEXT PRIMARY KEY,
            resumo TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        );
        """
    )
    conn.commit()


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
            _ensure_memory_schema(self.conn)
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

    def registrar_idempotente(self, user_id: str, titulo: str, desfecho: str,
                              contexto: str, chave: str,
                              preferencia: str | None = None) -> dict:
        """Grava recomendacao e episodio uma unica vez por conteudo canonico."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            existente = self.conn.execute(
                "SELECT history_id FROM acoes_idempotentes WHERE chave = ?", (chave,)
            ).fetchone()
            if existente:
                self.conn.commit()
                return {
                    "gravado": False,
                    "ja_existia": True,
                    "id": existente["history_id"],
                    "chave_idempotencia": chave,
                }
            cur = self.conn.execute(
                "INSERT INTO historico (user_id, titulo, desfecho) VALUES (?, ?, ?)",
                (user_id, titulo, desfecho),
            )
            history_id = cur.lastrowid
            self.conn.execute(
                "INSERT INTO episodios (user_id, titulo, contexto, chave, criado_em) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                (user_id, titulo, contexto, chave),
            )
            self.conn.execute(
                "INSERT INTO episodios_fts (contexto, user_id, titulo, chave) "
                "VALUES (?, ?, ?, ?)",
                (contexto, user_id, titulo, chave),
            )
            self.conn.execute(
                "INSERT INTO acoes_idempotentes (chave, history_id) VALUES (?, ?)",
                (chave, history_id),
            )
            if preferencia:
                self.conn.execute(
                    "INSERT INTO memoria_semantica (user_id, resumo, atualizado_em) "
                    "VALUES (?, ?, datetime('now')) ON CONFLICT(user_id) DO UPDATE SET "
                    "resumo = excluded.resumo, atualizado_em = excluded.atualizado_em",
                    (user_id, preferencia),
                )
            self.conn.commit()
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise ErroDeAcesso(f"falha ao gravar memoria idempotente: {exc}") from exc
        return {
            "gravado": True,
            "ja_existia": False,
            "id": history_id,
            "chave_idempotencia": chave,
        }

    def buscar_episodios(self, user_id: str, pergunta: str, limite: int = 5) -> list[dict]:
        """Busca episodios do usuario por relevancia lexical via SQLite FTS5."""
        termos = [t for t in normalizar(pergunta).split("_") if len(t) > 1]
        if not termos:
            return []
        consulta = " OR ".join('"' + termo.replace('"', '') + '"' for termo in termos)
        linhas = self.conn.execute(
            "SELECT e.titulo, e.contexto, e.criado_em, bm25(episodios_fts) AS score "
            "FROM episodios_fts JOIN episodios e ON e.chave = episodios_fts.chave "
            "WHERE episodios_fts MATCH ? AND e.user_id = ? "
            "ORDER BY score, e.criado_em DESC LIMIT ?",
            (consulta, user_id, limite),
        ).fetchall()
        return [dict(linha) for linha in linhas]

    def obter_preferencia(self, user_id: str) -> dict | None:
        linha = self.conn.execute(
            "SELECT resumo, atualizado_em FROM memoria_semantica WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return dict(linha) if linha else None

    def atualizar_preferencia(self, user_id: str, resumo: str) -> None:
        self.conn.execute(
            "INSERT INTO memoria_semantica (user_id, resumo, atualizado_em) "
            "VALUES (?, ?, datetime('now')) ON CONFLICT(user_id) DO UPDATE SET "
            "resumo = excluded.resumo, atualizado_em = excluded.atualizado_em",
            (user_id, resumo),
        )
        self.conn.commit()

    def remover_registro(self, registro_id: int):
        """Reversao da escrita acima. E o que torna `registrar` reversivel de fato."""
        self.conn.execute("DELETE FROM historico WHERE id = ?", (registro_id,))
        self.conn.commit()

    def remover_titular(self, user_id: str) -> dict:
        """Apaga o titular de todas as tabelas de memoria numa unica transacao.

        A chave idempotente sai junto: se ficasse, uma nova aprovacao identica
        responderia ja_existia=true apontando para um historico que nao existe.
        """
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            removidos = {
                "acoes_idempotentes": self.conn.execute(
                    "DELETE FROM acoes_idempotentes WHERE history_id IN "
                    "(SELECT id FROM historico WHERE user_id = ?)", (user_id,)).rowcount,
                "episodios_fts": self.conn.execute(
                    "DELETE FROM episodios_fts WHERE user_id = ?", (user_id,)).rowcount,
                "episodios": self.conn.execute(
                    "DELETE FROM episodios WHERE user_id = ?", (user_id,)).rowcount,
                "memoria_semantica": self.conn.execute(
                    "DELETE FROM memoria_semantica WHERE user_id = ?", (user_id,)).rowcount,
                "historico": self.conn.execute(
                    "DELETE FROM historico WHERE user_id = ?", (user_id,)).rowcount,
            }
            self.conn.commit()
        except sqlite3.Error as exc:
            self.conn.rollback()
            raise ErroDeAcesso(f"falha ao remover titular: {exc}") from exc
        return removidos

    def volume_titular(self, user_id: str) -> dict:
        """Linhas e bytes de texto guardados para o titular, por tabela (§5.3)."""
        consultas = {
            "historico": "SELECT COUNT(*), COALESCE(SUM(length(CAST(user_id || titulo || desfecho AS BLOB))), 0) "
                         "FROM historico WHERE user_id = ?",
            "episodios": "SELECT COUNT(*), COALESCE(SUM(length(CAST(user_id || titulo || contexto || chave AS BLOB))), 0) "
                         "FROM episodios WHERE user_id = ?",
            "memoria_semantica": "SELECT COUNT(*), COALESCE(SUM(length(CAST(user_id || resumo AS BLOB))), 0) "
                                 "FROM memoria_semantica WHERE user_id = ?",
        }
        volume = {}
        for tabela, sql in consultas.items():
            linhas, tamanho = self.conn.execute(sql, (user_id,)).fetchone()
            volume[tabela] = {"linhas": linhas, "bytes": tamanho}
        return volume

    def ocorrencias_titular(self, user_id: str) -> dict:
        """Varredura independente da remocao: conta linhas que ainda citam o titular."""
        return {
            "historico": self.conn.execute(
                "SELECT COUNT(*) FROM historico WHERE user_id = ?", (user_id,)).fetchone()[0],
            "episodios": self.conn.execute(
                "SELECT COUNT(*) FROM episodios WHERE user_id = ?", (user_id,)).fetchone()[0],
            "episodios_fts": self.conn.execute(
                "SELECT COUNT(*) FROM episodios_fts WHERE user_id = ?", (user_id,)).fetchone()[0],
            "memoria_semantica": self.conn.execute(
                "SELECT COUNT(*) FROM memoria_semantica WHERE user_id = ?", (user_id,)).fetchone()[0],
            # a chave nao guarda user_id; sobra dele aparece como chave orfa
            "acoes_idempotentes_orfas": self.conn.execute(
                "SELECT COUNT(*) FROM acoes_idempotentes WHERE history_id NOT IN "
                "(SELECT id FROM historico)").fetchone()[0],
        }

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
        CREATE TABLE IF NOT EXISTS acoes_idempotentes (
            chave TEXT PRIMARY KEY,
            history_id INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS episodios (
            user_id TEXT NOT NULL,
            titulo TEXT NOT NULL,
            contexto TEXT NOT NULL,
            chave TEXT PRIMARY KEY,
            criado_em TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS episodios_fts USING fts5(
            contexto, user_id UNINDEXED, titulo UNINDEXED, chave UNINDEXED
        );
        CREATE TABLE IF NOT EXISTS memoria_semantica (
            user_id TEXT PRIMARY KEY,
            resumo TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
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
