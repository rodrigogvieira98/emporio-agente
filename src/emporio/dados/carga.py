"""Carga dos CSV originais para var/emporio.db.

Uso: python -m emporio.dados.carga
Falha com mensagem clara em chave órfã, preço inválido ou JSON inválido em specs.
Nada é corrigido: totais, status e datas entram como gravados.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .. import config
from ..dinheiro import para_centavos
from . import banco


class CargaErro(Exception):
    pass


def _ler(raw: Path, nome: str, colunas: set[str]) -> list[dict[str, str]]:
    arquivo = raw / nome
    if not arquivo.exists():
        raise CargaErro(f"arquivo ausente: {arquivo}")
    with arquivo.open(encoding="utf-8", newline="") as f:
        leitor = csv.DictReader(f)
        faltando = colunas - set(leitor.fieldnames or [])
        if faltando:
            raise CargaErro(f"{nome}: colunas ausentes {sorted(faltando)}")
        return list(leitor)


def _preco(texto: str, onde: str) -> int:
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        raise CargaErro(f"{onde}: preco invalido {texto!r}") from None
    if not valor.is_finite() or valor <= 0:
        raise CargaErro(f"{onde}: preco invalido {texto!r} (precisa ser maior que zero)")
    return para_centavos(texto)


def _inteiro(texto: str, onde: str, minimo: int = 0) -> int:
    try:
        n = int(texto)
    except ValueError:
        raise CargaErro(f"{onde}: inteiro invalido {texto!r}") from None
    if n < minimo:
        raise CargaErro(f"{onde}: valor {n} abaixo de {minimo}")
    return n


def _nulo(texto: str | None) -> str | None:
    return texto if texto not in (None, "") else None


def carregar(raw: Path | None = None, destino: Path | None = None) -> dict[str, int]:
    raw = Path(raw) if raw else config.caminho_raw()
    destino = Path(destino) if destino else config.caminho_banco()
    categorias = _ler(raw, "categories.csv", {"category_id", "name", "description"})
    produtos = _ler(raw, "products.csv", {"product_id", "price_brl", "name", "category_id", "description",
                                          "stock_quantity", "status", "specs", "created_at"})
    promocoes = _ler(raw, "promotions.csv", {"promotion_id", "product_id", "discount_percent",
                                             "description", "is_active"})
    clientes = _ler(raw, "customers.csv", {"customer_id", "name", "phone", "email", "city"})
    pedidos = _ler(raw, "orders.csv", {"order_id", "customer_id", "order_date", "status", "total_brl",
                                       "payment_method", "tracking_code", "estimated_delivery", "notes"})
    itens = _ler(raw, "order_items.csv", {"order_id", "quantity", "product_id"})

    ids_cat = {_inteiro(c["category_id"], "categories.category_id", 1) for c in categorias}
    ids_prod = {_inteiro(p["product_id"], "products.product_id", 1) for p in produtos}
    ids_cli = {_inteiro(c["customer_id"], "customers.customer_id", 1) for c in clientes}
    ids_ped = {_inteiro(p["order_id"], "orders.order_id", 1) for p in pedidos}

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".tmp")
    temporario.unlink(missing_ok=True)
    conn = banco.conectar(temporario)
    try:
        banco.criar_esquema(conn)
        conn.executemany("INSERT INTO categorias VALUES (?,?,?)",
                         [(int(c["category_id"]), c["name"], c["description"]) for c in categorias])
        for p in produtos:
            onde = f"products[{p['product_id']}]"
            if _inteiro(p["category_id"], onde + ".category_id", 1) not in ids_cat:
                raise CargaErro(f"{onde}: categoria {p['category_id']} nao existe (chave orfa)")
            try:
                json.loads(p["specs"])
            except json.JSONDecodeError as erro:
                raise CargaErro(f"{onde}: JSON invalido em specs ({erro.msg})") from None
            conn.execute("INSERT INTO produtos VALUES (?,?,?,?,?,?,?,?,?)", (
                int(p["product_id"]), p["name"], _preco(p["price_brl"], onde), int(p["category_id"]),
                p["description"], _inteiro(p["stock_quantity"], onde + ".stock_quantity"),
                p["status"], p["specs"], _nulo(p["created_at"])))
        for pr in promocoes:
            onde = f"promotions[{pr['promotion_id']}]"
            if _inteiro(pr["product_id"], onde + ".product_id", 1) not in ids_prod:
                raise CargaErro(f"{onde}: produto {pr['product_id']} nao existe (chave orfa)")
            conn.execute("INSERT INTO promocoes VALUES (?,?,?,?,?)", (
                int(pr["promotion_id"]), int(pr["product_id"]),
                _inteiro(pr["discount_percent"], onde + ".discount_percent", 1),
                pr["description"], _inteiro(pr["is_active"], onde + ".is_active")))
        conn.executemany("INSERT INTO clientes VALUES (?,?,?,?,?)",
                         [(int(c["customer_id"]), c["name"], c["phone"], _nulo(c["email"]), _nulo(c["city"]))
                          for c in clientes])
        for o in pedidos:
            onde = f"orders[{o['order_id']}]"
            if _inteiro(o["customer_id"], onde + ".customer_id", 1) not in ids_cli:
                raise CargaErro(f"{onde}: cliente {o['customer_id']} nao existe (chave orfa)")
            conn.execute("INSERT INTO pedidos VALUES (?,?,?,?,?,?,?,?,?)", (
                int(o["order_id"]), int(o["customer_id"]), o["order_date"], o["status"],
                _preco(o["total_brl"], onde + ".total_brl"), o["payment_method"],
                _nulo(o["tracking_code"]), _nulo(o["estimated_delivery"]), _nulo(o["notes"])))
        for i, it in enumerate(itens, start=2):
            onde = f"order_items[linha {i}]"
            if _inteiro(it["order_id"], onde + ".order_id", 1) not in ids_ped:
                raise CargaErro(f"{onde}: pedido {it['order_id']} nao existe (chave orfa)")
            if _inteiro(it["product_id"], onde + ".product_id", 1) not in ids_prod:
                raise CargaErro(f"{onde}: produto {it['product_id']} nao existe (chave orfa)")
            conn.execute("INSERT INTO itens_pedido (pedido_id, produto_id, quantidade) VALUES (?,?,?)",
                         (int(it["order_id"]), int(it["product_id"]), _inteiro(it["quantity"], onde + ".quantity", 1)))
        conn.commit()
        contagem = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("categorias", "produtos", "promocoes", "clientes", "pedidos", "itens_pedido")}
    except sqlite3.IntegrityError as erro:
        conn.close()
        temporario.unlink(missing_ok=True)
        raise CargaErro(f"violacao de integridade: {erro}") from None
    except BaseException:
        conn.close()
        temporario.unlink(missing_ok=True)
        raise
    conn.close()
    temporario.replace(destino)
    return contagem


def main() -> int:
    try:
        contagem = carregar()
    except CargaErro as erro:
        print(f"ERRO na carga: {erro}", file=sys.stderr)
        return 1
    print(f"Banco criado em {config.caminho_banco()}")
    for tabela, n in contagem.items():
        print(f"  {tabela}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
