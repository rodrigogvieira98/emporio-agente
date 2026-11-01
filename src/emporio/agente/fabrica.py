"""Monta o Agente: controle por regras, ou decisor e redação com modelo local.

EMPORIO_MODELO escolhe o modelo. EMPORIO_REDACAO=0 desliga a redação (só o decisor usa o modelo).
EMPORIO_DECISOR=regras mantém o RegrasDecisor e deixa o modelo só na redação.
Com modelo, a concisão fica ligada; o controle por regras não muda.
"""
from __future__ import annotations

import os
from typing import Any

from . import llm
from .laco import Agente
from .llm_decisor import LlmDecisor
from .redacao import Redator


def criar_agente(modelo: str | None = None, cliente: Any = None, redacao: bool | None = None) -> Agente:
    modelo = modelo or llm.modelo_padrao()
    if not modelo:
        return Agente()
    if redacao is None:
        redacao = os.environ.get("EMPORIO_REDACAO", "1") != "0"
    if os.environ.get("EMPORIO_DECISOR", "modelo") == "regras":  # regras decidem; o modelo só redige
        return Agente(None, Redator(modelo, cliente) if redacao else None, concisao=True)
    return Agente(LlmDecisor(modelo, cliente), Redator(modelo, cliente) if redacao else None, concisao=True)
