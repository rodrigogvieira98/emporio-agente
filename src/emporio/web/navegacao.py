"""Menu de categorias.

Nenhuma ferramenta lista categorias, então este é o único acesso direto ao banco da camada web:
só os nomes, para montar o menu. Preço, estoque e regras continuam vindo das ferramentas.
"""
from __future__ import annotations

import sqlite3

from ..dados import banco


def listar_categorias() -> list[str]:
    try:
        conn = banco.conectar()
        try:
            return [linha["nome"] for linha in conn.execute("SELECT nome FROM categorias ORDER BY id")]
        finally:
            conn.close()
    except sqlite3.Error:
        return []
