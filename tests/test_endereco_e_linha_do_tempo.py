"""Etapa 15: bloco de endereço do CEP no checkout e linha do tempo do rastreio (SPEC)."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from emporio.ferramentas import cep as cep_mod
from emporio.web.app import criar_app
from emporio.web.linha_do_tempo import STATUS_SITE, Etapa, etapas_do_rastreio

TAKAMINE = 95
ENDERECOS = {
    "79800000": {"logradouro": "Rua Marechal Deodoro", "bairro": "Jardim Central", "localidade": "Dourados", "uf": "MS"},
    "50030230": {"logradouro": "Avenida Conde da Boa Vista", "bairro": "Boa Vista", "localidade": "Recife", "uf": "PE"},
}


@pytest.fixture(autouse=True)
def cep_falso(monkeypatch):
    monkeypatch.setenv("EMPORIO_CEP_EXTERNO", "1")
    cep_mod._memoria.clear()

    def falso(digitos):
        if digitos not in ENDERECOS:
            raise OSError("fora do ar")
        return ENDERECOS[digitos]

    monkeypatch.setattr(cep_mod, "_consultar_externo", falso)
    yield
    cep_mod._memoria.clear()


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        c.post("/carrinho/adicionar", data={"produto_id": TAKAMINE, "quantidade": 1})
        yield c


def bloco(html: str) -> str:
    achado = re.search(r'<div id="cep-bloco".*?</section>\s*</div>|<div id="cep-bloco"[^>]*>\s*</div>', html, re.S)
    assert achado, "bloco do CEP ausente"
    return achado.group(0)


def texto(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


# ---- endereço do CEP -------------------------------------------------------------------------------------------------

def test_bloco_mostra_rua_bairro_e_cidade_uf_abaixo_do_campo_cep(cliente):
    html = cliente.get("/checkout", params={"forma": "pix", "cep": "79800-000"}).text
    assert html.index('id="cep"') < html.index('id="cep-bloco"') < html.index("Resumo")
    b = texto(bloco(html))
    assert "Endereço de entrega" in b
    assert "Rua Marechal Deodoro" in b and "Jardim Central" in b and "Dourados/MS" in b
    assert "Número" not in b and "Complemento" not in b  # só leitura, sem pedir número nem complemento
    assert "<input" not in bloco(html)


def test_bloco_atualiza_ao_trocar_o_cep_pelo_htmx(cliente):
    htmx = {"HX-Request": "true"}
    a = cliente.get("/checkout", params={"forma": "pix", "cep": "79800-000"}, headers=htmx).text
    b = cliente.get("/checkout", params={"forma": "pix", "cep": "50030-230"}, headers=htmx).text
    assert 'hx-swap-oob="outerHTML"' in bloco(a) and 'hx-swap-oob="outerHTML"' in bloco(b)
    assert "Dourados/MS" in texto(bloco(a)) and "Recife" not in texto(bloco(a))
    assert "Avenida Conde da Boa Vista" in texto(bloco(b)) and "Boa Vista" in texto(bloco(b)) and "Recife/PE" in texto(bloco(b))
    assert "Dourados" not in texto(bloco(b))


def test_bloco_em_contingencia_mantem_a_mensagem_e_so_a_cidade_da_loja(cliente):
    html = cliente.get("/checkout", params={"forma": "pix", "cep": "79002-000"}).text  # dublê levanta OSError
    b = texto(bloco(html))
    assert "Não foi possível confirmar o endereço agora" in b
    assert "Campo Grande/MS" in b and "Rua" not in b.replace("Mostramos", "")


def test_bloco_vazio_sem_cep_e_mensagem_quando_o_servico_e_a_contingencia_nao_resolvem(cliente, monkeypatch):
    assert texto(bloco(cliente.get("/checkout").text)) == ""
    monkeypatch.setattr(cep_mod, "_contingencia", lambda d: cep_mod.Localizacao("indisponivel", d))
    html = cliente.get("/checkout", params={"forma": "pix", "cep": "70000-000"}).text
    assert "Não localizamos o endereço agora" in texto(bloco(html))


# ---- linha do tempo (função pura) ------------------------------------------------------------------------------------

def resumo(etapas: list[Etapa]) -> list[tuple[str, str]]:
    return [(e.rotulo, e.estado) for e in etapas]


def test_pending_marca_so_a_primeira_com_a_data_do_pedido():
    e = etapas_do_rastreio("pending", data_pedido="2026-02-15")
    assert resumo(e) == [("Pedido recebido", "atual"), ("Pagamento confirmado", "pendente"),
                         ("Enviado", "pendente"), ("Entregue", "pendente")]
    assert e[0].detalhe == "Em 15/02/2026"


def test_confirmed_vai_ate_a_segunda():
    e = etapas_do_rastreio("confirmed", data_pedido="2026-02-15", previsao="2026-02-28")
    assert resumo(e) == [("Pedido recebido", "feita"), ("Pagamento confirmado", "atual"),
                         ("Enviado", "pendente"), ("Entregue", "pendente")]
    assert e[3].detalhe == "Previsão: 28/02/2026"


def test_shipped_vai_ate_a_terceira_com_o_codigo_e_a_previsao():
    e = etapas_do_rastreio("shipped", data_pedido="2026-02-15", rastreio="BRJL5544332BR", previsao="2026-02-28")
    assert resumo(e) == [("Pedido recebido", "feita"), ("Pagamento confirmado", "feita"),
                         ("Enviado", "atual"), ("Entregue", "pendente")]
    assert e[2].detalhe == "Código de rastreio: BRJL5544332BR" and e[3].detalhe == "Previsão: 28/02/2026"
    assert [x.estado_texto for x in e] == ["concluída", "concluída", "etapa atual", "a seguir"]


def test_delivered_conclui_todas_sem_previsao():
    e = etapas_do_rastreio("delivered", data_pedido="2026-02-15", rastreio="BR1", previsao="2026-02-28")
    assert resumo(e) == [("Pedido recebido", "feita"), ("Pagamento confirmado", "feita"),
                         ("Enviado", "feita"), ("Entregue", "atual")]
    assert e[2].detalhe == "Código de rastreio: BR1" and e[3].detalhe == ""


def test_cancelled_mostra_recebido_e_cancelado_com_a_observacao():
    e = etapas_do_rastreio("cancelled", data_pedido="2026-02-15", nota="Pagamento não aprovado", rastreio="BR1")
    assert resumo(e) == [("Pedido recebido", "feita"), ("Cancelado", "atual")]
    assert e[1].detalhe == "Pagamento não aprovado"


def test_pedido_do_site_mostra_so_pedido_recebido():
    e = etapas_do_rastreio(STATUS_SITE, data_pedido="2026-10-31")
    assert STATUS_SITE == "PED-" and resumo(e) == [("Pedido recebido", "atual")]
    assert e[0].detalhe == "Em 31/10/2026"


def test_sem_data_nem_codigo_nao_inventa_detalhe():
    e = etapas_do_rastreio("shipped")
    assert all(x.detalhe == "" for x in e)


# ---- linha do tempo no site ------------------------------------------------------------------------------------------

def test_rastreio_do_pedido_8_mostra_lista_ordenada_com_enviado_atual_e_codigo(cliente):
    html = cliente.post("/rastreio", data={"pedido": "8", "final_telefone": "7821"}).text
    assert re.search(r'<ol class="linha-tempo"', html)
    atual = re.search(r'<li class="etapa etapa-atual" aria-current="step">(.*?)</li>', html, re.S).group(1)
    assert "Enviado" in texto(atual) and "etapa atual" in texto(atual) and "BRJL5544332BR" in texto(atual)
    assert html.count('aria-current="step"') == 1 and html.count("<li class=\"etapa ") == 4
    assert "Previsão: 28/02/2026" in texto(html)


def test_rastreio_de_pedido_do_site_mostra_pedido_recebido(cliente):
    cliente.post("/checkout", data={"forma": "pix", "parcelas": "1", "cep": "79800-000", "total_visto": "0"})
    r = cliente.get("/checkout", params={"forma": "pix", "cep": "79800-000"})
    total = re.search(r'name="total_visto" value="(\d+)"', r.text).group(1)
    feito = cliente.post("/checkout", data={"forma": "pix", "parcelas": "1", "cep": "79800-000", "total_visto": total})
    assert feito.status_code == 303
    numero = feito.headers["location"].rsplit("/", 1)[1]
    html = cliente.post("/rastreio", data={"pedido": numero, "final_telefone": ""}).text
    assert html.count('<li class="etapa ') == 1 and "Pedido recebido" in texto(html)
