"""Testes diretos dos limites de escrita — suíte de governança v1.0.0.

Versão publicada em 2026-10-16. Exercita Ferramentas, não apenas o verificador
offline de decisões já produzidas.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from catalogo_db import CatalogoDB, construir_banco  # noqa: E402
from ferramentas import Ferramentas  # noqa: E402


class TestLimitesDeAutoridade(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        db_path = Path(self.temp_dir.name) / "catalogo.db"
        construir_banco(db_path)
        self.db = CatalogoDB(db_path)
        self.addCleanup(self.db.fechar)

    def criar_ferramentas(self, **contexto):
        contexto_completo = {
            "user_id": "usuario-teste-novo",
            "subscriptions": [],
            "max_rating": "18+",
            "query": "",
            **contexto,
        }
        return Ferramentas(self.db, contexto_completo)

    def registrar(self, ferramentas, titulo, user_id=None):
        return ferramentas.registrar_recomendacao(
            user_id=user_id or ferramentas.ctx["user_id"],
            titulo=titulo,
            motivo="teste do limite de autoridade",
        )

    def test_recusa_titulo_fora_da_assinatura(self):
        ferramentas = self.criar_ferramentas(subscriptions=["Netflix"])

        resultado = self.registrar(ferramentas, "Severance")

        self.assertEqual(resultado["erro"], "fora_da_assinatura")
        self.assertEqual(self.db.historico(ferramentas.ctx["user_id"]), [])

    def test_recusa_titulo_acima_da_classificacao(self):
        ferramentas = self.criar_ferramentas(
            subscriptions=["Prime Video"], max_rating="10+"
        )

        resultado = self.registrar(ferramentas, "Severance")

        self.assertEqual(resultado["erro"], "classificacao_incompativel")
        self.assertEqual(self.db.historico(ferramentas.ctx["user_id"]), [])

    def test_recusa_recomendacao_repetida(self):
        ferramentas = self.criar_ferramentas(
            user_id="u-005", subscriptions=["Netflix"], max_rating="16+"
        )

        resultado = self.registrar(ferramentas, "Dark")

        self.assertEqual(resultado["erro"], "recomendacao_repetida")

    def test_busca_filtra_assinatura_e_classificacao(self):
        ferramentas = self.criar_ferramentas(
            subscriptions=["Prime Video"],
            max_rating="10+",
            query="mal-estar e misterio",
        )

        resultado = ferramentas.buscar_candidatos("mal-estar misterio")

        self.assertEqual(resultado["candidatos"], [])

    def test_registra_e_reverte_recomendacao_valida(self):
        ferramentas = self.criar_ferramentas(
            subscriptions=["Netflix"], max_rating="16+"
        )

        resultado = self.registrar(ferramentas, "Dark")

        self.assertTrue(resultado["gravado"])
        self.assertEqual(self.db.historico(ferramentas.ctx["user_id"])[0]["titulo"], "Dark")
        ids_revertidos = ferramentas.reverter_escritas()
        self.assertEqual(ids_revertidos, [resultado["id"]])
        self.assertEqual(self.db.historico(ferramentas.ctx["user_id"]), [])


if __name__ == "__main__":
    unittest.main()