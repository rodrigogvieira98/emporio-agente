"""listar_promocoes: só promoções com is_active=1, nunca deduzidas por calendário."""
from __future__ import annotations

from pydantic import field_validator

from .. import dinheiro
from ..dados import banco
from ..texto import normalizar, radical, tokens
from .envelope import EntradaBase, Fonte, Resultado, ferramenta, resultado
from .produtos import situacao_venda

FONTE = Fonte(tipo="banco", referencia="promocoes")


class EntradaPromocoes(EntradaBase):
    termo: str | None = None

    @field_validator("termo")
    @classmethod
    def _termo(cls, v: str | None) -> str | None:
        if v is not None and not tokens(v):
            raise ValueError("termo vazio")
        return v


@ferramenta(EntradaPromocoes)
def listar_promocoes(e: EntradaPromocoes) -> Resultado:
    conn = banco.conectar()
    try:
        linhas = conn.execute(
            "SELECT pr.id, pr.produto_id, pr.percentual, pr.descricao, p.nome, p.preco_centavos, p.status, p.estoque "
            "FROM promocoes pr JOIN produtos p ON p.id = pr.produto_id WHERE pr.ativa = 1 ORDER BY pr.id").fetchall()
    finally:
        conn.close()
    if e.termo:
        partes = [radical(t) for t in tokens(e.termo)]
        linhas = [r for r in linhas if all(p in normalizar(f"{r['descricao']} {r['nome']}") for p in partes)]
    if not linhas:
        return resultado("vazio", {"termo": e.termo, "promocoes": []}, [FONTE], "promocao_nao_ativa")
    por_produto: dict[int, int] = {}
    for r in linhas:
        por_produto[r["produto_id"]] = por_produto.get(r["produto_id"], 0) + 1
    itens = []
    for r in linhas:
        conflito = por_produto[r["produto_id"]] > 1
        itens.append({
            "promocao_id": r["id"], "produto_id": r["produto_id"], "produto_nome": r["nome"],
            "descricao": r["descricao"], "percentual": r["percentual"],
            "original_centavos": r["preco_centavos"],
            "final_centavos": None if conflito else dinheiro.aplicar_desconto(r["preco_centavos"], r["percentual"]),
            "conflito": conflito, "situacao_venda": situacao_venda(r["status"], r["estoque"]),
        })
    return resultado("ok", {"termo": e.termo, "promocoes": itens, "total": len(itens)}, [FONTE])
