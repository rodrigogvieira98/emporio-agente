"""Persona da Lia, lida de persona.yaml. Entra nas instruções do modelo em todo turno redigido."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CAMINHO = Path(__file__).with_name("persona.yaml")
CAMPOS_OBRIGATORIOS = ("nome", "identificacao", "tom", "comportamentos_a_evitar", "exemplos", "expressoes_proibidas")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF]")


@lru_cache(maxsize=1)
def carregar() -> dict[str, Any]:
    dados = yaml.safe_load(CAMINHO.read_text(encoding="utf-8"))
    faltando = [c for c in CAMPOS_OBRIGATORIOS if not dados.get(c)]
    if faltando:
        raise ValueError(f"persona.yaml sem os campos {faltando}")
    return dados


def instrucoes() -> str:
    """Trecho de instruções do modelo: quem é a Lia, como fala e o que evita."""
    p = carregar()
    return (f"Você é {p['nome']}, {p['identificacao']}. Tom: {'; '.join(p['tom'])}. "
            f"Evite: {'; '.join(p['comportamentos_a_evitar'])}. Nunca use emoji nem tratamento formal.")


def proibida_em(texto: str) -> list[str]:
    """Expressões proibidas e emoji presentes no texto."""
    baixo = texto.lower()
    achadas = [x for x in carregar()["expressoes_proibidas"] if re.search(rf"\b{re.escape(x.lower())}\b", baixo)]
    if EMOJI.search(texto):
        achadas.append("emoji")
    return achadas
