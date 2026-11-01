"""Site: frete estimado (simulação) no checkout, no total, nas parcelas e na confirmação (SPEC, etapa 8)."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from emporio.dinheiro import formatar as brl
from emporio.ferramentas import cep as cep_mod
from emporio.ferramentas.condicoes import calcular_condicoes
from emporio.ferramentas.frete import estimar_frete
from emporio.web.app import criar_app

TAKAMINE, BATERIA, UKULELE_SOPRANO = 95, 139, 117
LOCAIS = {"79800000": ("Dourados", "MS"), "50030230": ("Recife", "PE"), "59000000": ("Campo Grande", "RN"),
          "79002000": ("Campo Grande", "MS")}


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


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


def comprar(cliente, produto, quantidade=1):
    cliente.post("/carrinho/adicionar", data={"produto_id": produto, "quantidade": quantidade})


def texto(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def checkout(cliente, **params):
    return texto(cliente.get("/checkout", params=params).text)


def frete_ref(cep, produto, qtd=1):
    r = estimar_frete(itens=[{"produto_id": produto, "quantidade": qtd}], cep=cep)
    return {m["id"]: m["valor_centavos"] for m in r.dados["modalidades"]}


def unit(produto, forma):
    return calcular_condicoes(produto_id=produto, forma=forma).dados["final_centavos"]


def test_fora_de_campo_grande_mostra_pac_no_total_e_o_outro_como_informacao(cliente):
    comprar(cliente, TAKAMINE)
    f = frete_ref("79800-000", TAKAMINE)
    t = checkout(cliente, forma="debito", cep="79800-000")
    assert f"Frete estimado (simulação): {brl(f['economica'])}" in t
    assert f"SEDEX estimado (simulação): {brl(f['expressa'])}. Informação, não entra no total." in t
    assert f"Total estimado {brl(unit(TAKAMINE, 'debito') + f['economica'])}" in t
    assert "Entrega em: Rua A, Centro, Dourados/MS" in t and "Em outras cidades" not in t


def test_pix_nao_muda_o_frete_estimado(cliente):
    comprar(cliente, TAKAMINE)
    f = frete_ref("79800-000", TAKAMINE)
    for forma in ("pix", "debito", "boleto", "credito"):
        assert f"Frete estimado (simulação): {brl(f['economica'])}" in checkout(cliente, forma=forma, cep="79800-000")


def test_total_e_parcelas_incluem_o_frete_estimado(cliente):
    comprar(cliente, TAKAMINE)
    f = frete_ref("50030-230", TAKAMINE)
    total = unit(TAKAMINE, "credito") + f["economica"]
    parcela = calcular_condicoes(valor=total, forma="credito", parcelas=3).dados["parcela_centavos"]
    t = checkout(cliente, forma="credito", parcelas="3", cep="50030-230")
    assert f"Total estimado {brl(total)}" in t and f"3x de {brl(parcela)}" in t


def test_confirmacao_grava_o_frete_estimado_e_repete_os_rotulos(cliente, sql):
    comprar(cliente, TAKAMINE)
    f = frete_ref("79800-000", TAKAMINE)
    total = unit(TAKAMINE, "debito") + f["economica"]
    r = cliente.post("/checkout", data={"forma": "debito", "parcelas": "1", "cep": "79800-000", "total_visto": str(total)})
    assert r.status_code == 303
    linha = sql.execute("SELECT * FROM pedidos_demo").fetchone()
    assert (linha["frete_situacao"], linha["frete_centavos"], linha["total_centavos"]) == ("estimado", f["economica"], total)
    t = texto(cliente.get(r.headers["location"]).text)
    assert f"Frete estimado (simulação): {brl(f['economica'])}" in t and f"Total estimado {brl(total)}" in t


def test_grande_porte_fica_sem_valor_no_checkout_e_na_confirmacao(cliente):
    comprar(cliente, BATERIA)
    t = checkout(cliente, forma="debito", cep="79800-000")
    produtos = unit(BATERIA, "debito")
    assert "Frete: Cotação com a equipe" in t and f"Total dos produtos {brl(produtos)}" in t
    assert "Frete estimado" not in t and "SEDEX" not in t
    r = cliente.post("/checkout", data={"forma": "debito", "parcelas": "1", "cep": "79800-000", "total_visto": str(produtos)})
    assert r.status_code == 303
    c = texto(cliente.get(r.headers["location"]).text)
    assert "Frete: Cotação com a equipe" in c and f"Total dos produtos {brl(produtos)}" in c and "Frete estimado" not in c


def test_servico_de_cep_fora_do_ar_nao_inventa_valor(cliente):
    comprar(cliente, TAKAMINE)
    t = checkout(cliente, forma="debito", cep="30140-071")  # o dublê não conhece: rede caiu
    assert "Não localizamos o endereço agora" in t and "Frete: Cotação com a equipe" in t
    assert f"Total dos produtos {brl(unit(TAKAMINE, 'debito'))}" in t and "Frete estimado" not in t


def test_cidade_base_segue_a_regra_da_loja_com_rotulos_proprios(cliente):
    comprar(cliente, UKULELE_SOPRANO)
    t = checkout(cliente, forma="debito", cep="79002-000")
    assert "Frete: R$ 35,00" in t and f"Total {brl(unit(UKULELE_SOPRANO, 'debito') + 3500)}" in t
    assert "Total estimado" not in t and "Frete estimado" not in t
    comprar(cliente, TAKAMINE)
    assert "Frete: Grátis" in checkout(cliente, forma="pix", cep="79002-000")


def test_campo_grande_do_rio_grande_do_norte_recebe_estimativa(cliente):
    comprar(cliente, TAKAMINE)
    t = checkout(cliente, forma="debito", cep="59000-000")
    assert "Frete estimado (simulação):" in t and "Campo Grande/RN" in t and "Frete: R$ 35,00" not in t


def test_sem_cep_diz_informe_o_cep_sem_pendencia(cliente):
    comprar(cliente, TAKAMINE)
    html = cliente.get("/checkout", params={"forma": "debito"}).text
    assert "Frete: Informe o CEP" in texto(html) and 'class="pendencias"' not in html
    assert "disabled" in re.search(r"<button[^>]*>\s*Registrar pedido", html).group(0)


def test_pendencia_so_em_erro(cliente):
    comprar(cliente, TAKAMINE)
    assert "CEP não encontrado" in checkout(cliente, forma="debito", cep="99999-999")
    assert "O CEP precisa ter 8 números" in checkout(cliente, forma="debito", cep="123")


def test_texto_sobre_o_cep_aparece_uma_vez_no_checkout(cliente):
    comprar(cliente, TAKAMINE)
    t = checkout(cliente, forma="debito")
    assert t.count("calcular o frete") == 1


def test_carrinho_fala_do_cep_e_politicas_explica_as_demais_cidades(cliente):
    comprar(cliente, TAKAMINE)
    assert "forma de pagamento e do CEP" in cliente.get("/carrinho").text
    pol = texto(cliente.get("/politicas").text)
    assert "valem somente em Campo Grande" in pol and "frete estimado (simulação)" in pol
