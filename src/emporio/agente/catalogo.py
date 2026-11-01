"""Vocabulário de reconhecimento lido do banco: nomes de produto, cidades e campanhas.

Serve só para reconhecer o que o cliente citou. Nenhum valor ou regra de loja sai daqui.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache

from .. import config
from ..dados import banco
from ..texto import normalizar, tokens


@dataclass
class Vocabulario:
    df: dict[str, int] = field(default_factory=dict)  # token de nome de produto -> em quantos produtos aparece
    cidades: list[str] = field(default_factory=list)
    campanhas: list[str] = field(default_factory=list)


@lru_cache(maxsize=4)
def _ler(caminho: str, mtime_ns: int) -> Vocabulario:
    voc = Vocabulario()
    conn = banco.conectar(caminho)
    try:
        for (nome,) in conn.execute("SELECT nome FROM produtos"):
            for t in set(tokens(nome)):
                voc.df[t] = voc.df.get(t, 0) + 1
        voc.cidades = sorted({normalizar(c) for (c,) in conn.execute("SELECT cidade FROM clientes WHERE cidade IS NOT NULL")},
                             key=len, reverse=True)
        voc.campanhas = sorted({normalizar(c) for (c,) in conn.execute("SELECT descricao FROM promocoes")},
                               key=len, reverse=True)
    finally:
        conn.close()
    return voc


def vocabulario() -> Vocabulario:
    caminho = config.caminho_banco()
    try:
        return _ler(str(caminho), caminho.stat().st_mtime_ns)
    except (OSError, sqlite3.Error):
        return Vocabulario()
