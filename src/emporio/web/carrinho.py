"""Carrinho por sessão do navegador, guardado no servidor (tabela `carrinhos`).

Só guarda produto e quantidade. Preço, promoção, PIX, parcela e frete nunca são gravados no carrinho:
são recalculados por `calcular_condicoes` a cada vez (ver `compra.py`). Estoque não é baixado.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .. import config
from ..dados import banco
from ..ferramentas.produtos import ver_produto

MAX_POR_ITEM = 3  # limite da compra de demonstração (SPEC, incremento 1); não é fato de loja
MIN_POR_ITEM = 1


class RecusaCarrinho(Exception):
    """Motivo mostrável ao cliente; o carrinho não muda."""


def _conn() -> sqlite3.Connection:
    conn = banco.conectar()
    banco.garantir_tabelas_demo(conn)
    return conn


def listar(sessao: str) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        linhas = conn.execute("SELECT produto_id, quantidade FROM carrinhos WHERE sessao = ? ORDER BY id",
                              (sessao,)).fetchall()
    finally:
        conn.close()
    return [{"produto_id": l["produto_id"], "quantidade": l["quantidade"]} for l in linhas]


def quantidade_total(sessao: str) -> int:
    return sum(i["quantidade"] for i in listar(sessao))


def adicionar(sessao: str, produto_id: int, quantidade: int) -> None:
    """Só produto vendável entra; a situação vem de `ver_produto`. Levanta RecusaCarrinho."""
    if not MIN_POR_ITEM <= quantidade <= MAX_POR_ITEM:
        raise RecusaCarrinho(f"A quantidade por item vai de {MIN_POR_ITEM} a {MAX_POR_ITEM}.")
    r = ver_produto(referencia=produto_id)
    if r.estado == "vazio":
        raise RecusaCarrinho("Não achamos esse produto.")
    if r.estado != "ok":
        raise RecusaCarrinho("Não conseguimos consultar o produto agora. Tente de novo em instantes.")
    if r.dados["situacao_venda"] != "disponivel":
        raise RecusaCarrinho(f"{r.dados['nome']} não está disponível para compra, então não entra no carrinho.")
    conn = _conn()
    try:
        with conn:
            atual = conn.execute("SELECT quantidade FROM carrinhos WHERE sessao = ? AND produto_id = ?",
                                 (sessao, produto_id)).fetchone()
            nova = (atual["quantidade"] if atual else 0) + quantidade
            if nova > MAX_POR_ITEM:
                raise RecusaCarrinho(f"Cada item aceita no máximo {MAX_POR_ITEM} unidades por compra. "
                                     f"{r.dados['nome']} já está no carrinho.")
            if atual:
                conn.execute("UPDATE carrinhos SET quantidade = ? WHERE sessao = ? AND produto_id = ?",
                             (nova, sessao, produto_id))
            else:
                conn.execute("INSERT INTO carrinhos (sessao, produto_id, quantidade, criado_em) VALUES (?,?,?,?)",
                             (sessao, produto_id, nova, config.agora().isoformat()))
    finally:
        conn.close()


def definir_quantidade(sessao: str, produto_id: int, quantidade: int) -> None:
    """Zero remove o item. Fora de 1 a 3 levanta RecusaCarrinho."""
    if quantidade == 0:
        remover(sessao, produto_id)
        return
    if not MIN_POR_ITEM <= quantidade <= MAX_POR_ITEM:
        raise RecusaCarrinho(f"A quantidade por item vai de {MIN_POR_ITEM} a {MAX_POR_ITEM}.")
    conn = _conn()
    try:
        with conn:
            conn.execute("UPDATE carrinhos SET quantidade = ? WHERE sessao = ? AND produto_id = ?",
                         (quantidade, sessao, produto_id))
    finally:
        conn.close()


def remover(sessao: str, produto_id: int) -> None:
    conn = _conn()
    try:
        with conn:
            conn.execute("DELETE FROM carrinhos WHERE sessao = ? AND produto_id = ?", (sessao, produto_id))
    finally:
        conn.close()


def esvaziar(sessao: str) -> None:
    conn = _conn()
    try:
        with conn:
            conn.execute("DELETE FROM carrinhos WHERE sessao = ?", (sessao,))
    finally:
        conn.close()
