"""Trace JSONL por turno. Nunca grava texto do cliente nem argumentos livres.

Só entram ids, estados, nomes de ferramenta, números inteiros e enumerações. Nome, telefone,
e-mail e o final de telefone digitado não passam por aqui.
"""
from __future__ import annotations

import json
from typing import Any

from .. import config

ARGS_TEXTUAIS_PERMITIDOS = {"forma", "tipo"}  # enumerações fechadas


def sanitizar_args(args: dict[str, Any]) -> dict[str, Any]:
    limpo: dict[str, Any] = {}
    for chave, valor in args.items():
        if isinstance(valor, bool) or valor is None or isinstance(valor, int):
            limpo[chave] = valor
        elif isinstance(valor, str) and chave in ARGS_TEXTUAIS_PERMITIDOS:
            limpo[chave] = valor
        elif isinstance(valor, list):
            limpo[chave] = f"[{len(valor)} itens]"
        else:
            limpo[chave] = "[omitido]"
    return limpo


def registrar_turno(registro: dict[str, Any]) -> None:
    caminho = config.caminho_trace()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")
