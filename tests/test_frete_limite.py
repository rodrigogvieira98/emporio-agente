"""Limite do frete grátis: R$ 500,00 em produtos, com promoções e antes do desconto do PIX (SPEC, etapa 8)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from emporio.agente.laco import Agente
from emporio.ferramentas.condicoes import calcular_condicoes
from emporio.web import carrinho, compra
from emporio.web.app import criar_app

KALANI_300S, KALANI_700T = 118, 127  # 179,90 e 359,00 com 10% de promoção ativa = 323,10
SHELBY_SU21S, KALA_KAC = 119, 120  # 159,90 (sem promoção ativa) e 349,90
CEP_CAMPO_GRANDE = "79002-000"
PEDIDOS = {
    "kalani": ([KALANI_300S, KALANI_700T], 50310),
    "shelby_kala": ([SHELBY_SU21S, KALA_KAC], 50980),
}


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


def montar(sessao, produtos):
    for p in produtos:
        carrinho.adicionar(sessao, p, 1)


@pytest.mark.parametrize("nome", list(PEDIDOS))
def test_pedido_acima_de_500_antes_do_pix_tem_frete_gratis_em_todas_as_formas(nome):
    produtos, bruto = PEDIDOS[nome]
    for forma in ("pix", "debito", "credito", "boleto"):
        montar(f"s-{nome}-{forma}", produtos)
        c = compra.calcular(f"s-{nome}-{forma}", forma, 1, CEP_CAMPO_GRANDE)
        assert c["frete"]["situacao"] == "gratis" and c["frete"]["taxa"] == 0, forma
    # o PIX reduz o total dos produtos, mas nunca o frete: o total fica abaixo do limite e segue grátis
    pix = compra.calcular(f"s-{nome}-pix", "pix", 1, CEP_CAMPO_GRANDE)
    assert pix["produtos_total"] < 50000 <= bruto
    assert pix["total"] == pix["produtos_total"]


@pytest.mark.parametrize("nome", list(PEDIDOS))
def test_pix_nao_muda_o_frete_do_pedido(nome):
    produtos, _ = PEDIDOS[nome]
    montar(f"a-{nome}", produtos)
    montar(f"b-{nome}", produtos)
    assert compra.calcular(f"a-{nome}", "pix", 1, CEP_CAMPO_GRANDE)["frete"] == \
        compra.calcular(f"b-{nome}", "boleto", 1, CEP_CAMPO_GRANDE)["frete"]


def test_abaixo_do_limite_cobra_a_taxa_mesmo_no_pix():
    montar("barato", [KALANI_300S])
    c = compra.calcular("barato", "debito", 1, CEP_CAMPO_GRANDE)
    assert c["frete"]["situacao"] == "taxa" and c["frete"]["taxa"] == 3500


def test_ferramenta_usa_o_valor_antes_do_pix_quando_nao_ha_valor_do_pedido():
    # Kala KA-C a R$ 349,90: com PIX vai a R$ 286,92, mas o frete olha 349,90 (abaixo de 500 nos dois casos)
    pix = calcular_condicoes(produto_id=KALA_KAC, forma="pix", cidade="Campo Grande")
    assert pix.dados["final_centavos"] < pix.dados["original_centavos"]
    assert pix.dados["frete"]["situacao"] == "taxa"
    # valor 51.000 em PIX: descontado cai abaixo de 500, mas o frete segue grátis
    r = calcular_condicoes(valor=51000, forma="pix", cidade="Campo Grande")
    assert r.dados["final_centavos"] < 50000 and r.dados["frete"]["situacao"] == "gratis"


def test_site_mostra_o_mesmo_frete_nas_formas_de_pagamento(cliente):
    for p in PEDIDOS["shelby_kala"][0]:
        cliente.post("/carrinho/adicionar", data={"produto_id": p, "quantidade": 1})
    pix = cliente.get("/checkout", params={"forma": "pix", "cep": CEP_CAMPO_GRANDE}).text
    boleto = cliente.get("/checkout", params={"forma": "boleto", "cep": CEP_CAMPO_GRANDE}).text
    assert "Frete grátis" in pix and "Frete grátis" in boleto


def test_lia_e_ferramenta_dizem_o_mesmo_para_o_valor_do_pedido():
    agente = Agente()
    for valor, esperado in (("R$ 509,80", "grátis"), ("R$ 503", "grátis"), ("R$ 499,90", "taxa fixa de R$ 35,00")):
        r = agente.responder(f"l-{valor}", f"qual o frete para Campo Grande de um pedido de {valor}?", "eval")
        assert esperado in r.texto, (valor, r.texto)


def test_lia_explica_que_o_limite_e_antes_do_pix():
    r = Agente().responder("l1", "como funciona o frete?", "eval")
    assert "antes do desconto do PIX" in r.texto and "promoções" in r.texto
