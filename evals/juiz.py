"""Juiz LLM binario: o trecho citado sustenta o clima pedido?

A rubrica e versionada em evals/juiz/rubrica.txt. O juiz so conta na nota da
suite se a validacao (python -m evals.validar_juiz) atingir o limiar declarado
em docs/evals.md antes da medicao.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

RUBRICA = Path(__file__).resolve().parent / "juiz" / "rubrica.txt"


class Veredito(BaseModel):
    veredito: Literal["sustenta", "nao_sustenta"]
    justificativa: str


def versao_rubrica() -> str:
    match = re.search(r"^# versao:\s*(\S+)", RUBRICA.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else "?"


def julgar(pedido: str, titulo: str, trecho: str, tentativas: int = 3) -> dict:
    from openai import OpenAI, RateLimitError

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("o juiz precisa de OPENAI_API_KEY no .env")
    client = OpenAI(base_url=os.environ.get("LLM_BASE_URL") or None,
                    api_key=os.environ["OPENAI_API_KEY"], timeout=30, max_retries=0)
    modelo = os.environ.get("JUDGE_MODEL") or os.environ.get("MODEL_NAME", "ministral-8b-2512")
    mensagem = f"PEDIDO: {pedido}\nTITULO: {titulo}\nTRECHO: {trecho}"
    for tentativa in range(tentativas):
        try:
            resposta = client.chat.completions.create(
                model=modelo, temperature=0,
                messages=[{"role": "system", "content": RUBRICA.read_text(encoding="utf-8")},
                          {"role": "user", "content": mensagem}],
                response_format={"type": "json_object"}, max_tokens=150)
            break
        except RateLimitError:
            if tentativa == tentativas - 1:
                raise
            time.sleep(2 ** tentativa)
    bruto = resposta.choices[0].message.content or "{}"
    try:
        v = Veredito.model_validate_json(bruto)
        return {"veredito": v.veredito, "justificativa": v.justificativa,
                "modelo": modelo, "rubrica": versao_rubrica()}
    except Exception:
        # saida fora do contrato conta como nao_sustenta, e fica registrada
        return {"veredito": "nao_sustenta", "justificativa": f"saida invalida: {bruto[:200]}",
                "modelo": modelo, "rubrica": versao_rubrica(), "invalido": True}
