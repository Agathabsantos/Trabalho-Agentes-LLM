"""O 429 da camada gratis espera e tenta de novo; outros erros nao."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("TRACE_FILE", str(Path(tempfile.gettempdir()) / "agente-testes-traces.jsonl"))
sys.path.insert(0, str(ROOT / "src"))

import httpx  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from openai import RateLimitError  # noqa: E402

from catalogo_db import construir_banco  # noqa: E402
from graph import create_graph, invocar, resultado_publico  # noqa: E402


def _429():
    resposta = httpx.Response(429, request=httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions"))
    return RateLimitError("limite", response=resposta, body=None)


def _ok():
    conteudo = '{"intent": "recommendation", "mood": "leve", "ambiguous": false, "clarification": ""}'
    return SimpleNamespace(model="ministral-8b-2512",
                           usage=SimpleNamespace(prompt_tokens=700, completion_tokens=30),
                           choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=conteudo))])


class TestRetry429(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        db = Path(self.temp.name) / "c.db"
        construir_banco(db)
        self.graph = create_graph(db, InMemorySaver())
        env = mock.patch.dict(os.environ, {"OPENAI_API_KEY": "teste", "LLM_BASE_URL": "https://api.mistral.ai/v1"})
        env.start()
        self.addCleanup(env.stop)

    def _rodar(self, efeitos):
        cliente = mock.MagicMock()
        cliente.chat.completions.create.side_effect = efeitos
        with mock.patch("openai.OpenAI", return_value=cliente), mock.patch("graph.time.sleep") as dormir:
            state = invocar(self.graph, {"message": "Quero algo leve e cotidiano, para rir.", "user_id": "r",
                                         "subscriptions": ["Netflix"], "max_rating": "16+", "session_id": "r"})
        return state, cliente, dormir

    def test_429_seguido_de_sucesso_responde(self):
        state, cliente, dormir = self._rodar([_429(), _ok()])
        self.assertEqual(resultado_publico(state)["status"], "awaiting_human")
        self.assertEqual(cliente.chat.completions.create.call_count, 2)
        dormir.assert_called_once_with(2)

    def test_429_persistente_vira_erro_depois_de_quatro_tentativas(self):
        state, cliente, _ = self._rodar([_429()] * 4)
        self.assertEqual(resultado_publico(state)["status"], "error")
        self.assertEqual(cliente.chat.completions.create.call_count, 4)


if __name__ == "__main__":
    unittest.main()
