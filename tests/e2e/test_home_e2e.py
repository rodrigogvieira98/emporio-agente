"""Homepage no navegador: sem rolagem horizontal. Carrossel e Lia: ver test_site_real_e2e.py. pytest -m e2e"""
from __future__ import annotations

import socket
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from emporio.web.app import criar_app  # noqa: E402

pytestmark = pytest.mark.e2e


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


def _pagina(navegador, largura: int, altura: int = 800):
    return navegador.new_context(viewport={"width": largura, "height": altura}).new_page()


@pytest.mark.parametrize("caminho", ["/", "/catalogo", "/produto/90", "/politicas", "/rastreio"])
def test_sem_rolagem_horizontal_em_360px(url_site, navegador, caminho):
    pagina = _pagina(navegador, 360, 740)
    pagina.goto(url_site + caminho)
    assert pagina.evaluate("document.documentElement.scrollWidth") <= 360


@pytest.mark.parametrize("largura", [768, 1024, 1440])
def test_sem_rolagem_horizontal_nas_larguras_intermediarias(url_site, navegador, largura):
    pagina = _pagina(navegador, largura)
    pagina.goto(url_site + "/")
    assert pagina.evaluate("document.documentElement.scrollWidth") <= largura


def test_rodape_compacto_altura_em_1280_links_em_linha_e_lia_fora_dos_links(url_site, navegador):
    pagina = _pagina(navegador, 1280)
    pagina.goto(url_site + "/")
    pagina.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    assert pagina.locator(".rodape").bounding_box()["height"] <= 160
    links = [pagina.locator(".rodape a").nth(i).bounding_box() for i in range(pagina.locator(".rodape a").count())]
    assert len(links) == 3 and len({round(b["y"]) for b in links}) == 1  # linha única
    assert pagina.locator(".rodape h2").count() == 0
    lia = pagina.locator("#chat-alternar").bounding_box()
    for b in links:
        assert b["x"] + b["width"] <= lia["x"] or b["y"] + b["height"] <= lia["y"] or b["y"] >= lia["y"] + lia["height"]


def test_rodape_em_390px_sem_rolagem_horizontal_alvos_de_toque_e_lia_fora_dos_links(url_site, navegador):
    pagina = _pagina(navegador, 390, 800)
    pagina.goto(url_site + "/")
    pagina.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    assert pagina.evaluate("document.documentElement.scrollWidth") <= 390
    lia = pagina.locator("#chat-alternar").bounding_box()
    for i in range(pagina.locator(".rodape a").count()):
        b = pagina.locator(".rodape a").nth(i).bounding_box()
        assert b["height"] >= 44
        assert (b["x"] + b["width"] <= lia["x"] or b["x"] >= lia["x"] + lia["width"]
                or b["y"] + b["height"] <= lia["y"] or b["y"] >= lia["y"] + lia["height"])


@pytest.mark.parametrize("largura", [1280, 390])
def test_catalogo_no_cabecalho_leva_ao_catalogo_sem_rolagem_horizontal(url_site, navegador, largura):
    pagina = _pagina(navegador, largura, 800)
    pagina.goto(url_site + "/")
    assert pagina.evaluate("document.documentElement.scrollWidth") <= largura
    if largura < 900:
        pagina.locator(".menu-botao").click()  # no celular a navegação fica recolhida no botão de menu
    pagina.locator(".menu-itens > a", has_text="Catálogo").click()
    pagina.wait_for_url("**/catalogo")
    assert pagina.evaluate("document.documentElement.scrollWidth") <= largura


def test_aviso_imagem_ilustrativa_abre_creditos(url_site, navegador):
    pagina = _pagina(navegador, 1280, 800)
    pagina.goto(url_site + "/produto/90")
    pagina.locator("a.legenda-ilustrativa").click()
    pagina.wait_for_url("**/creditos")


def test_abertura_compacta_e_categorias_na_primeira_tela(url_site, navegador):
    p = _pagina(navegador, 1280, 800)
    p.goto(url_site + "/")
    altura_abertura = p.locator(".abertura").bounding_box()["height"]
    assert 420 <= altura_abertura <= 460
    box = p.locator("#t-categorias").bounding_box()
    assert box["y"] + box["height"] <= 800
    m = _pagina(navegador, 390, 800)
    m.goto(url_site + "/")
    assert m.locator(".abertura-foto").bounding_box()["height"] <= 300
    assert m.evaluate("document.documentElement.scrollWidth") <= 390


def test_faq_mesma_largura_da_faixa_de_contato_e_alinhada_a_esquerda_em_1280(url_site, navegador):
    p = _pagina(navegador, 1280, 800)
    p.goto(url_site + "/perguntas-frequentes")
    faixa = p.locator(".faixa-contato .cartao-3").bounding_box()
    faq = p.locator(".faq").first.bounding_box()
    h1 = p.locator("h1").bounding_box()
    assert abs(faq["x"] - faixa["x"]) <= 1 and abs(faq["width"] - faixa["width"]) <= 1
    assert abs(h1["x"] - faq["x"]) <= 1
    assert p.evaluate("getComputedStyle(document.querySelector('.faq-pagina')).textAlign") in ("start", "left")
    p.locator(".faq-item summary").first.click()
    resp = p.locator(".faq-item[open] p").first.bounding_box()
    assert abs(resp["x"] - faq["x"]) <= 1 and resp["width"] > 300


def test_faq_sem_rolagem_horizontal_em_390px(url_site, navegador):
    p = _pagina(navegador, 390, 800)
    p.goto(url_site + "/perguntas-frequentes")
    p.locator(".faq-item summary").first.click()
    assert p.evaluate("document.documentElement.scrollWidth") <= 390
