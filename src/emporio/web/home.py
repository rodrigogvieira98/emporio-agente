"""Dados da homepage. Tudo vem das ferramentas do agente; nada é calculado nem escrito aqui.

Destaques (carrossel): produtos com promoção ativa. Grade: o mais barato vendável de cada categoria, sem repetir
destaque. Categorias: só as que têm produto vendável.
"""
from __future__ import annotations

from typing import Any

from ..ferramentas.condicoes import calcular_condicoes
from ..ferramentas.produtos import buscar_produtos, ver_produto
from ..ferramentas.promocoes import listar_promocoes
from ..politicas.manual import fato
from . import apresentacao, fotos, navegacao

TAMANHO_GRADE = 8


def _promocoes_por_produto() -> dict[int, dict[str, Any]]:
    r = listar_promocoes()
    return {p["produto_id"]: p for p in r.dados["promocoes"]} if r.estado == "ok" else {}


def _parcelamento(produto_id: int) -> dict[str, Any] | None:
    """Maior parcelamento que a ferramenta aprova (permitido=sim)."""
    f = fato("pagamento.credito_parcelas_max")
    maximo = int(f.valor) if f else 1
    for n in range(maximo, 1, -1):
        r = calcular_condicoes(produto_id=produto_id, forma="credito", parcelas=n)
        if r.estado == "ok" and r.dados["permitido"] == "sim":
            sem_juros = fato("pagamento.credito_sem_juros")
            return {"parcelas": n, "parcela": r.dados["parcela_centavos"],
                    "sem_juros": bool(sem_juros and sem_juros.valor)}
    return None


def _condicao_pix(produto_id: int) -> dict[str, Any] | None:
    r = calcular_condicoes(produto_id=produto_id, forma="pix")
    if r.estado != "ok":
        return None
    d = r.dados
    return {"valor": d["final_centavos"], "desconto": d.get("pix_percentual") if d.get("pix_aplicado") else None}


def com_foto(item: dict[str, Any], categoria: str | None) -> dict[str, Any]:
    """Liga o item à categoria, à foto do seu tipo e à ilustração de reserva."""
    item["categoria"] = categoria
    item["foto"] = fotos.foto_do_produto(item["id"], item["nome"], categoria)
    item["ilustracao"] = apresentacao.ilustracao(categoria)
    return item


def com_categoria(item: dict[str, Any]) -> dict[str, Any]:
    """Item de busca (que não traz a categoria) ligado a ela e à foto."""
    r = ver_produto(referencia=item["id"])
    categoria = r.dados["categoria"] if r.estado == "ok" else None
    return _com_condicoes(item, categoria) if item.get("pode_comprar") else com_foto(item, categoria)


def _com_condicoes(item: dict[str, Any], categoria: str | None) -> dict[str, Any]:
    com_foto(item, categoria)
    item["pix"] = _condicao_pix(item["id"])
    item["parcelamento"] = _parcelamento(item["id"])
    return item


def destaques() -> list[dict[str, Any]]:
    """Produtos vendáveis com promoção ativa e inequívoca."""
    promos = _promocoes_por_produto()
    saida: list[dict[str, Any]] = []
    for p in promos.values():
        if p["conflito"] or p["situacao_venda"] != "disponivel":
            continue
        r = ver_produto(referencia=p["produto_id"])
        if r.estado == "ok":
            saida.append(_com_condicoes(apresentacao.preparar_item(r.dados, promos), r.dados["categoria"]))
    return saida


def grade(excluir: set[int]) -> list[dict[str, Any]]:
    """O mais barato vendável de cada categoria, de preços variados, fora dos destaques."""
    promos = _promocoes_por_produto()
    candidatos = []
    for c in categorias():
        r = buscar_produtos(categoria=c["nome"], limite=3)
        if r.estado == "ok":
            candidatos += [(i, c["nome"]) for i in r.dados["itens"] if i["id"] not in excluir]
    candidatos.sort(key=lambda x: x[0]["preco_centavos"])
    saida, por_categoria = [], {}
    for item, nome in candidatos:  # no máximo 2 por categoria, para a grade ter variedade
        if por_categoria.get(nome, 0) >= 2 or len(saida) >= TAMANHO_GRADE:
            continue
        por_categoria[nome] = por_categoria.get(nome, 0) + 1
        saida.append(_com_condicoes(apresentacao.preparar_item(item, promos), nome))
    return saida


def categorias() -> list[dict[str, Any]]:
    """Categorias com produto vendável, com contagem e menor preço. Categoria vazia não aparece."""
    saida = []
    for nome in navegacao.listar_categorias():
        r = buscar_produtos(categoria=nome, limite=1)
        if r.estado != "ok":
            continue
        saida.append({"nome": nome, "ilustracao": apresentacao.ilustracao(nome), "foto": fotos.foto_da_categoria(nome),
                      "total": r.dados["total_encontrado"], "a_partir_de": r.dados["itens"][0]["preco_centavos"]})
    return saida
