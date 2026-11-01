"""Lia: CEP na mensagem, estimativa de frete (simulação) com a mesma ferramenta do site (SPEC, etapa 8)."""
from __future__ import annotations

import pytest

from emporio.agente.laco import Agente
from emporio.dinheiro import formatar as brl
from emporio.ferramentas import cep as cep_mod
from emporio.ferramentas.frete import estimar_frete
from emporio.web import carrinho, compra

LOCAIS = {"79800000": ("Dourados", "MS"), "50030230": ("Recife", "PE"), "59000000": ("Campo Grande", "RN"),
          "79002000": ("Campo Grande", "MS")}
YAMAHA_C40 = 81  # violão
TAKAMINE_GD20 = 95
BATERIA = 139


@pytest.fixture(autouse=True)
def cep_falso(monkeypatch):
    monkeypatch.setenv("EMPORIO_CEP_EXTERNO", "1")
    cep_mod._memoria.clear()

    def falso(digitos):
        if digitos == "99999999":
            return {"erro": "true"}
        if digitos not in LOCAIS:
            raise OSError("fora do ar")
        cidade, uf = LOCAIS[digitos]
        return {"localidade": cidade, "uf": uf, "logradouro": "Rua A", "bairro": "Centro"}

    monkeypatch.setattr(cep_mod, "_consultar_externo", falso)
    yield
    cep_mod._memoria.clear()


def dizer(*mensagens, conversa="f1"):
    agente = Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def ferramentas(r):
    return [a["ferramenta"] for a in r.acoes if "ferramenta" in a]


def valores(cep, produto):
    r = estimar_frete(itens=[{"produto_id": produto, "quantidade": 1}], cep=cep)
    return {m["id"]: m["valor_centavos"] for m in r.dados["modalidades"]}


def test_produto_e_cep_na_mesma_mensagem_dao_pac_e_modalidade_expressa_com_rotulo_de_simulacao():
    (r,) = dizer("quanto fica o frete do Yamaha C40 para o CEP 79800-000?")
    v = valores("79800-000", YAMAHA_C40)
    assert "estimar_frete" in ferramentas(r)
    assert "frete estimado (simulação)" in r.texto and "Dourados/MS" in r.texto
    assert f"PAC: {brl(v['economica'])}" in r.texto and f"SEDEX: {brl(v['expressa'])}" in r.texto
    assert "não a tarifa" in r.texto and r.estado == "concluido"


def test_lia_e_site_mostram_o_mesmo_valor():
    (r,) = dizer("frete do Takamine GD20 para o CEP 50030-230")
    carrinho.adicionar("s1", TAKAMINE_GD20, 1)
    site = compra.calcular("s1", "debito", 1, "50030-230")["frete"]["taxa"]
    assert brl(site) in r.texto and site == valores("50030-230", TAKAMINE_GD20)["economica"]


def test_pede_o_que_faltar_e_aceita_a_ordem_inversa():
    r1, r2 = dizer("qual o frete para o CEP 79800-000?", "o Yamaha C40")
    assert "qual é o produto" in r1.texto and r1.estado == "aguardando:referencia_produto"
    assert "frete estimado (simulação)" in r2.texto and "R$" in r2.texto
    s1, s2, s3 = dizer("quanto custa o Yamaha C40?", "e o frete?", "meu CEP é 79800-000", conversa="f2")
    assert "frete estimado (simulação)" in s3.texto


def test_cep_solto_depois_de_pedir_o_cep():
    r1, r2 = dizer("frete do Yamaha C40", "79800000")
    assert "estimar_frete" in ferramentas(r2) or "frete estimado" in r2.texto


def test_so_cidade_e_valor_segue_dizendo_cotacao_e_explica_o_que_permite_estimar():
    (r,) = dizer("qual o frete para Dourados de um pedido de R$ 800?")
    assert "depende de cotação" in r.texto and "produto e o CEP" in r.texto and "estimativa" in r.texto
    assert "estimar_frete" not in ferramentas(r)


def test_grande_porte_nao_recebe_valor():
    (r,) = dizer("frete da Bateria Acústica Yamaha Kit 1 Studio para o CEP 79800-000")
    assert "cotação individual" in r.texto and "R$" not in r.texto


def test_servico_de_cep_fora_do_ar_nao_inventa_valor():
    (r,) = dizer("frete do Yamaha C40 para o CEP 30140-071")
    assert "Não consegui consultar esse CEP" in r.texto and "R$" not in r.texto


def test_cep_inexistente_pede_de_novo():
    (r,) = dizer("frete do Yamaha C40 para o CEP 99999-999")
    assert "Não encontrei esse CEP" in r.texto and r.estado == "aguardando:cep"


def test_campo_grande_do_rio_grande_do_norte_nao_recebe_a_regra_da_base():
    (rn,) = dizer("frete para Campo Grande/RN de um pedido de R$ 600", conversa="a")
    assert "grátis" not in rn.texto and "depende de cotação" in rn.texto and "Campo Grande/RN" in rn.texto
    (ms,) = dizer("frete para Campo Grande/MS de um pedido de R$ 600", conversa="b")
    assert "grátis" in ms.texto
    (sem,) = dizer("frete para Campo Grande de um pedido de R$ 600", conversa="c")
    assert "grátis" in sem.texto


def test_cep_de_campo_grande_rn_e_estimado_e_o_de_ms_segue_a_regra_da_loja():
    (rn,) = dizer("frete do Yamaha C40 para o CEP 59000-000", conversa="a")
    assert "frete estimado (simulação)" in rn.texto and "Campo Grande/RN" in rn.texto
    (ms,) = dizer("frete do Takamine GD20 para o CEP 79002-000", conversa="b")
    assert "grátis" in ms.texto or "taxa fixa" in ms.texto
    assert "estimar_frete" in ferramentas(ms)


def test_pix_nao_aparece_no_calculo_do_frete_e_a_regra_menciona_antes_do_pix():
    (r,) = dizer("o frete muda se eu pagar no PIX? Compra em Campo Grande de R$ 503")
    assert "grátis" in r.texto
