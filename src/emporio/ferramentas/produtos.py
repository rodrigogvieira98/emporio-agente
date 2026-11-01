"""buscar_produtos e ver_produto."""
from __future__ import annotations

import sqlite3
from typing import Any

from ..dados import banco
from ..texto import normalizar, radical, tokens
from .envelope import EntradaBase, Fonte, Resultado, ferramenta, resultado

LIMITE_MAXIMO = 5  # limite de sistema, não é fato de loja
LIMITE_SITE = 60  # teto da interface do site (para_site=True); a Lia continua com 5
FONTE_BANCO = Fonte(tipo="banco", referencia="produtos")

SITUACAO = {"active": "disponivel", "discontinued": "descontinuado", "coming_soon": "em_breve"}


def situacao_venda(status: str, estoque: int) -> str:
    if status == "active":
        return "disponivel" if estoque > 0 else "esgotado"
    return SITUACAO.get(status, "descontinuado")


def promocoes_ativas(conn: sqlite3.Connection, produto_id: int) -> list[sqlite3.Row]:
    """Promoção vale só por is_active=1, nunca por calendário."""
    return conn.execute(
        "SELECT id, percentual, descricao FROM promocoes WHERE produto_id = ? AND ativa = 1 ORDER BY id",
        (produto_id,)).fetchall()


def resumo_promocao(linhas: list[sqlite3.Row]) -> dict[str, Any] | None:
    if not linhas:
        return None
    if len(linhas) > 1:
        return {"ambigua": True, "quantidade": len(linhas)}
    p = linhas[0]
    return {"id": p["id"], "percentual": p["percentual"], "descricao": p["descricao"]}


def _item(conn: sqlite3.Connection, linha: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": linha["id"],
        "nome": linha["nome"],
        "preco_centavos": linha["preco_centavos"],
        "situacao_venda": situacao_venda(linha["status"], linha["estoque"]),
        "promocao": resumo_promocao(promocoes_ativas(conn, linha["id"])),
    }


class EntradaBusca(EntradaBase):
    categoria: str | None = None
    termo: str | None = None
    preco_min: int | None = None
    preco_max: int | None = None
    limite: int = 5
    deslocamento: int = 0
    para_site: bool = False
    incluir_indisponiveis: bool = False


@ferramenta(EntradaBusca)
def buscar_produtos(e: EntradaBusca) -> Resultado:
    if e.limite < 1 or e.deslocamento < 0:
        return resultado("falha", motivo="entrada_invalida")
    if (e.preco_min is not None and e.preco_min < 0) or (e.preco_max is not None and e.preco_max < 0):
        return resultado("falha", motivo="faixa_incoerente")
    if e.preco_min is not None and e.preco_max is not None and e.preco_min > e.preco_max:
        return resultado("falha", motivo="faixa_incoerente")
    limite = min(e.limite, LIMITE_SITE if e.para_site else LIMITE_MAXIMO)

    conn = banco.conectar()
    try:
        filtros, params = [], []
        if e.categoria is not None:
            consulta = {radical(t) for t in tokens(e.categoria)}
            ids = [c["id"] for c in conn.execute("SELECT id, nome FROM categorias")
                   if consulta and consulta <= {radical(t) for t in tokens(c["nome"])}]
            if not ids:
                return resultado("vazio", {"total_encontrado": 0, "itens": []}, [FONTE_BANCO],
                                 "categoria_inexistente")
            filtros.append(f"categoria_id IN ({','.join('?' * len(ids))})")
            params += ids
        if e.preco_min is not None:
            filtros.append("preco_centavos >= ?")
            params.append(e.preco_min)
        if e.preco_max is not None:
            filtros.append("preco_centavos <= ?")
            params.append(e.preco_max)
        if not e.incluir_indisponiveis:
            filtros.append("status = 'active' AND estoque > 0")
        where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
        linhas = conn.execute(f"SELECT * FROM produtos{where} ORDER BY preco_centavos, id", params).fetchall()
        if e.termo:
            partes = [radical(t) for t in tokens(e.termo)]
            linhas = [r for r in linhas
                      if all(p in normalizar(r["nome"] + " " + (r["descricao"] or "")) for p in partes)]
        if not linhas:
            return resultado("vazio", {"total_encontrado": 0, "itens": []}, [FONTE_BANCO], "sem_produtos")
        itens = [_item(conn, r) for r in linhas[e.deslocamento:e.deslocamento + limite]]
        return resultado("ok", {"total_encontrado": len(linhas), "itens": itens}, [FONTE_BANCO])
    finally:
        conn.close()


class EntradaProduto(EntradaBase):
    referencia: str | int


@ferramenta(EntradaProduto)
def ver_produto(e: EntradaProduto) -> Resultado:
    conn = banco.conectar()
    try:
        if isinstance(e.referencia, int):
            linhas = conn.execute("SELECT * FROM produtos WHERE id = ?", (e.referencia,)).fetchall()
        else:
            alvo = normalizar(e.referencia)
            if not alvo:
                return resultado("falha", motivo="entrada_invalida")
            todos = conn.execute("SELECT * FROM produtos ORDER BY id").fetchall()
            linhas = [r for r in todos if normalizar(r["nome"]) == alvo]
            if not linhas:
                partes = tokens(e.referencia)
                linhas = [r for r in todos if all(p in tokens(r["nome"]) for p in partes)]
        if not linhas:
            return resultado("vazio", fontes=[FONTE_BANCO], motivo="produto_nao_encontrado")
        if len(linhas) > 1:
            opcoes = [{"id": r["id"], "nome": r["nome"]} for r in linhas[:5]]
            return resultado("ambiguo", {"opcoes": opcoes, "total_opcoes": len(linhas)}, [FONTE_BANCO],
                             "varios_produtos")
        r = linhas[0]
        categoria = conn.execute("SELECT nome FROM categorias WHERE id = ?", (r["categoria_id"],)).fetchone()
        dados = _item(conn, r)
        dados.update({"categoria": categoria["nome"] if categoria else None, "descricao": r["descricao"],
                      "estoque_unidades": r["estoque"]})
        return resultado("ok", dados, [FONTE_BANCO])
    finally:
        conn.close()
