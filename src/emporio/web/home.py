"""Dados da homepage. Tudo vem das ferramentas do agente; nada é calculado nem escrito aqui.

Vitrine: produtos com promoção ativa e, para completar, os mais baratos vendáveis de categorias diferentes.
"""
from __future__ import annotations

from typing import Any

from ..ferramentas.condicoes import calcular_condicoes
from ..ferramentas.politica import consultar_politica
from ..ferramentas.produtos import buscar_produtos, ver_produto
from ..ferramentas.promocoes import listar_promocoes
from ..politicas.manual import fato
from . import apresentacao, navegacao

TAMANHO_VITRINE = 8

# Seções do manual que alimentam "Como funciona comprar aqui". Os ids são só endereços no manual:
# o texto, as condições e as ressalvas vêm de consultar_politica.
BLOCOS_COMO_FUNCIONA = (
    ("Pagamento", "pagamento", (("3.1", 4),), "3"),
    ("Frete", "frete", (("5.1", 4),), "5"),
    ("Troca", "trocas", (("4.1", 2), ("4.2", 1)), "4"),
    ("Garantia", "garantia", (("8.1", 1),), "8"),
)


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


def com_categoria(item: dict[str, Any]) -> dict[str, Any]:
    """Liga o item de busca à categoria (a busca não a devolve) para escolher a ilustração."""
    r = ver_produto(referencia=item["id"])
    categoria = r.dados["categoria"] if r.estado == "ok" else None
    item["categoria"] = categoria
    item["ilustracao"] = apresentacao.ilustracao(categoria)
    return item


def _com_condicoes(item: dict[str, Any], categoria: str | None) -> dict[str, Any]:
    item["categoria"] = categoria
    item["ilustracao"] = apresentacao.ilustracao(categoria)
    item["pix"] = _condicao_pix(item["id"])
    item["parcelamento"] = _parcelamento(item["id"])
    return item


def vitrine() -> list[dict[str, Any]]:
    promos = _promocoes_por_produto()
    saida: list[dict[str, Any]] = []
    vistos: set[int] = set()
    for p in promos.values():
        if p["conflito"] or p["situacao_venda"] != "disponivel" or p["produto_id"] in vistos:
            continue
        r = ver_produto(referencia=p["produto_id"])
        if r.estado != "ok":
            continue
        vistos.add(p["produto_id"])
        saida.append(_com_condicoes(apresentacao.preparar_item(r.dados, promos), r.dados["categoria"]))
    # completar: o mais barato vendável de cada categoria que ainda não tem produto na vitrine
    candidatos = []
    representadas = {s["categoria"] for s in saida}
    for nome in navegacao.listar_categorias():
        if nome in representadas:
            continue
        r = buscar_produtos(categoria=nome, limite=1)
        if r.estado == "ok":
            candidatos.append((r.dados["itens"][0], nome))
    candidatos.sort(key=lambda c: c[0]["preco_centavos"])
    for item, nome in candidatos:
        if len(saida) >= TAMANHO_VITRINE:
            break
        if item["id"] in vistos:
            continue
        saida.append(_com_condicoes(apresentacao.preparar_item(item, promos), nome))
    return saida


def categorias() -> list[dict[str, Any]]:
    """Cada categoria com contagem e menor preço vendável; sem produto vendável, 'em breve' e sem link."""
    saida = []
    for nome in navegacao.listar_categorias():
        r = buscar_produtos(categoria=nome, limite=1)
        entrada: dict[str, Any] = {"nome": nome, "ilustracao": apresentacao.ilustracao(nome), "total": 0,
                                   "a_partir_de": None}
        if r.estado == "ok":
            entrada["total"] = r.dados["total_encontrado"]
            entrada["a_partir_de"] = r.dados["itens"][0]["preco_centavos"]
        saida.append(entrada)
    return saida


def como_funciona() -> list[dict[str, Any]]:
    """Blocos curtos de pagamento, frete, troca e garantia, com as ressalvas do manual."""
    saida = []
    ja_ditas: set[str] = set()  # a mesma ressalva liga seções de blocos diferentes: aparece uma vez só
    for titulo, tema, ids, ancora in BLOCOS_COMO_FUNCIONA:
        r = consultar_politica(temas=[tema])
        if r.estado != "ok":
            continue
        por_id = {s["id"]: s for s in r.dados["secoes"]}
        linhas: list[str] = []
        ressalvas: list[str] = []
        for i, quantas in ids:
            s = por_id.get(i)
            if not s or not s["publico"] or not s["texto"]:
                continue
            texto = [ln.lstrip("• ").strip() for ln in s["texto"].splitlines() if ln.strip()]
            linhas += texto[:quantas]
            ressalvas += [a["descricao"] for a in s["ambiguidades"] if a["id"] not in ja_ditas]
            ja_ditas.update(a["id"] for a in s["ambiguidades"])
        if linhas:
            saida.append({"titulo": titulo, "linhas": linhas, "ressalvas": ressalvas, "ancora": f"secao-{ancora}"})
    return saida
