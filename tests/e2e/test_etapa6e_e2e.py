"""Etapa 6e no navegador: checkout que recalcula sozinho, foco no CEP, faixa Fale conosco, página de contato e Lia.

Fora da execução padrão: pytest -m e2e. Grava as capturas docs/capturas/fale_conosco_1280.png e fale_conosco_390.png.
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from emporio.politicas.manual import fato  # noqa: E402
from emporio.web.app import criar_app  # noqa: E402

pytestmark = pytest.mark.e2e

CAPTURAS = Path(__file__).resolve().parents[2] / "docs" / "capturas"
PRODUTO_5400 = 134  # tabela R$ 5.400,00, sem promoção: PIX R$ 5.130,00, 12x de R$ 450,00


@pytest.fixture
def url_site(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    servidor = uvicorn.Server(uvicorn.Config(criar_app(), host="127.0.0.1", port=porta, log_level="warning"))
    fio = threading.Thread(target=servidor.run, daemon=True)
    fio.start()
    for _ in range(100):
        if servidor.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{porta}"
    servidor.should_exit = True
    fio.join(timeout=5)


@pytest.fixture
def navegador():
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            yield b
        finally:
            b.close()


def pagina_de(navegador, largura, altura=800):
    return navegador.new_context(viewport={"width": largura, "height": altura}).new_page()


def sem_rolagem_horizontal(pagina) -> bool:
    return pagina.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


def ir_ao_checkout(pagina, url_site):
    pagina.goto(f"{url_site}/produto/{PRODUTO_5400}")
    pagina.click(".btn-comprar")
    pagina.wait_for_url("**/carrinho")
    pagina.goto(f"{url_site}/checkout")


def total(pagina) -> str:
    return pagina.inner_text(".resumo-final dd")


# ---- checkout --------------------------------------------------------------------------------------

def test_trocar_forma_recalcula_sem_clicar_em_atualizar(url_site, navegador):
    pagina = pagina_de(navegador, 1280)
    ir_ao_checkout(pagina, url_site)
    assert pagina.locator("button:has-text('Atualizar valores')").count() == 0  # com JavaScript o botão (noscript) não existe
    pagina.fill("#cep", "79002-000")
    pagina.wait_for_function("document.querySelector('.resumo-final dd') && document.querySelector('.resumo-final dd').innerText.includes('5.130,00')")
    assert "R$ 5.130,00" in total(pagina)  # PIX: 5% sobre a tabela
    assert pagina.locator("#parcelas").count() == 0  # parcelas só no crédito
    pagina.select_option("#forma", "debito")
    pagina.wait_for_function("document.querySelector('.resumo-final dd').innerText.includes('5.400,00')")
    assert "R$ 5.400,00" in total(pagina) and pagina.locator("#parcelas").count() == 0
    pagina.select_option("#forma", "credito")
    pagina.wait_for_selector("#parcelas")
    pagina.select_option("#parcelas", "12")
    pagina.wait_for_function("document.querySelector('.resumo-total').innerText.includes('12x de')")
    resumo = pagina.inner_text(".resumo-total")
    assert "R$ 450,00" in resumo and "R$ 5.400,00" in total(pagina)
    assert pagina.locator("button:has-text('Registrar pedido')").is_enabled()
    pagina.select_option("#forma", "pix")  # volta ao PIX: o campo de parcelas some
    pagina.wait_for_function("!document.querySelector('#parcelas')")


def test_foco_permanece_no_cep_durante_o_recalculo(url_site, navegador):
    pagina = pagina_de(navegador, 1280)
    ir_ao_checkout(pagina, url_site)
    pagina.click("#cep")
    pagina.keyboard.type("79002000", delay=60)
    pagina.wait_for_function("document.querySelector('.resumo-final dd') && document.querySelector('.resumo-final dd').innerText.includes('5.130,00')")
    assert pagina.evaluate("document.activeElement.id") == "cep"
    assert pagina.input_value("#cep") == "79002000"
    pagina.keyboard.type("1", delay=30)  # continua digitando no mesmo campo
    assert pagina.input_value("#cep").endswith("1")


def test_cep_invalido_deixa_o_registro_desabilitado(url_site, navegador):
    pagina = pagina_de(navegador, 390)
    ir_ao_checkout(pagina, url_site)
    pagina.fill("#cep", "123")
    pagina.wait_for_selector(".pendencias")
    assert pagina.locator("button:has-text('Registrar pedido')").is_disabled()
    assert pagina.locator("a:has-text('Não sei meu CEP')").get_attribute("target") == "_blank"


# ---- faixa Fale conosco ---------------------------------------------------------------------------------

@pytest.mark.parametrize("largura", [390, 1280])
def test_cabecalho_sem_fale_conosco_e_rodape_com_o_link(url_site, navegador, largura):
    pagina = pagina_de(navegador, largura)
    pagina.goto(url_site + "/")
    assert pagina.locator("header.topo a:has-text('Fale conosco')").count() == 0
    pagina.locator("footer a:has-text('Fale conosco')").click()
    pagina.wait_for_url("**/fale-conosco")


def test_faixa_botoes_chegam_ao_destino_e_sem_rolagem_em_390(url_site, navegador):
    pagina = pagina_de(navegador, 390, 844)
    pagina.goto(url_site + "/")
    assert sem_rolagem_horizontal(pagina)
    assert pagina.locator(".faixa-contato .bloco-3").count() == 3
    pagina.locator(".faixa-contato a:has-text('Fale conosco')").click()
    pagina.wait_for_url("**/fale-conosco")
    assert pagina.locator(".faixa-contato").count() == 0
    pagina.goto(url_site + "/")
    pagina.locator(".faixa-contato a:has-text('Rastrear pedido')").click()
    pagina.wait_for_url("**/rastreio")


@pytest.mark.parametrize("largura", [390, 1280])
def test_botao_da_lia_nao_cobre_a_faixa_ao_final_da_rolagem(url_site, navegador, largura):
    pagina = pagina_de(navegador, largura, 800)
    pagina.goto(url_site + "/")
    pagina.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    pagina.wait_for_timeout(200)
    lia = pagina.locator("#chat-alternar").bounding_box()
    for botao in pagina.locator(".faixa-contato .botao").all():
        b = botao.bounding_box()
        separados = (b["x"] + b["width"] <= lia["x"] or lia["x"] + lia["width"] <= b["x"]
                     or b["y"] + b["height"] <= lia["y"] or lia["y"] + lia["height"] <= b["y"])
        assert separados, (b, lia)
        assert botao.is_visible()


# ---- página /fale-conosco ---------------------------------------------------------------------------------

def test_fale_conosco_em_duas_colunas_de_mesma_altura_em_1280(url_site, navegador):
    pagina = pagina_de(navegador, 1280, 900)
    pagina.goto(url_site + "/fale-conosco")
    form = pagina.locator("#mensagem").bounding_box()
    horario = pagina.locator(".fc-horario").bounding_box()
    assert abs(form["height"] - horario["height"]) < 1.5 and abs(form["y"] - horario["y"]) < 1.5
    assert horario["x"] > form["x"] + form["width"] - 1  # lado a lado
    assert pagina.locator(".fc-canais .bloco-3").count() == 3
    assert [t.strip() for t in pagina.locator(".fc-canais h2").all_inner_texts()] == ["WhatsApp", "Telefone", "E-mail"]
    assert fato("empresa.endereco").valor["logradouro"] in pagina.inner_text(".fc-horario")
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    pagina.screenshot(path=str(CAPTURAS / "fale_conosco_1280.png"), full_page=True)


def test_fale_conosco_empilha_em_390_na_ordem_canais_formulario_horario(url_site, navegador):
    pagina = pagina_de(navegador, 390, 844)
    pagina.goto(url_site + "/fale-conosco")
    assert sem_rolagem_horizontal(pagina)
    canais = pagina.locator(".fc-canais").bounding_box()
    form = pagina.locator("#mensagem").bounding_box()
    horario = pagina.locator(".fc-horario").bounding_box()
    assert canais["y"] + canais["height"] <= form["y"] + 1 and form["y"] + form["height"] <= horario["y"] + 1
    pagina.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    pagina.wait_for_timeout(200)
    lia = pagina.locator("#chat-alternar").bounding_box()
    b = pagina.locator("#mensagem button[type=submit]").bounding_box()
    assert (b["y"] + b["height"] <= lia["y"] or lia["y"] + lia["height"] <= b["y"] or b["x"] + b["width"] <= lia["x"])
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    pagina.screenshot(path=str(CAPTURAS / "fale_conosco_390.png"), full_page=True)


def test_envio_pela_pagina_mostra_protocolo(url_site, navegador):
    pagina = pagina_de(navegador, 1280, 900)
    pagina.goto(url_site + "/fale-conosco")
    pagina.fill("#f-assunto", "Dúvida sobre prazo")
    pagina.fill("#f-mensagem", "Gostaria de saber o prazo de entrega.")
    pagina.fill("#f-contato", "cliente@example.com")
    pagina.click("#mensagem button[type=submit]")
    pagina.wait_for_selector(".protocolo")
    assert "Mensagem registrada" in pagina.inner_text("main")


# ---- Lia: quero comprar só prepara a conversa ------------------------------------------------------------------

def test_quero_comprar_com_a_lia_nao_envia(url_site, navegador):
    pagina = pagina_de(navegador, 1280, 900)
    pagina.goto(f"{url_site}/produto/{PRODUTO_5400}")
    antes = pagina.locator("#chat-log .msg.voce").count()
    pagina.click(".btn-compra")
    pagina.wait_for_timeout(500)
    assert pagina.locator("#chat").is_visible() and pagina.locator("#chat-log .msg.voce").count() == antes
    assert pagina.input_value("#chat-mensagem").strip() != "" and pagina.evaluate("document.activeElement.id") == "chat-mensagem"


# ---- ajustes de layout de /fale-conosco ----------------------------------------------------------------

@pytest.mark.parametrize("largura", [390, 1280])
def test_email_do_fale_conosco_cabe_em_uma_linha(url_site, navegador, largura):
    pagina = pagina_de(navegador, largura, 900)
    pagina.goto(url_site + "/fale-conosco")
    email = pagina.locator(".bloco-email")
    altura_linha = pagina.evaluate("el => parseFloat(getComputedStyle(el).lineHeight)", email.element_handle())
    assert email.bounding_box()["height"] <= altura_linha * 1.5
    assert sem_rolagem_horizontal(pagina)


def test_sem_vao_entre_tabela_e_rastreio_com_colunas_de_mesma_altura(url_site, navegador):
    pagina = pagina_de(navegador, 1280, 900)
    pagina.goto(url_site + "/fale-conosco")
    tabela = pagina.locator(".fc-horario table.horario").bounding_box()
    rastreio = pagina.locator(".fc-rastreio").bounding_box()
    assert rastreio["y"] - (tabela["y"] + tabela["height"]) <= 40
    form = pagina.locator("#mensagem").bounding_box()
    horario = pagina.locator(".fc-horario").bounding_box()
    assert abs(form["height"] - horario["height"]) < 1.5
