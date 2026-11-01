"""Homepage no navegador: carrossel por teclado, perguntas da Lia, sem rolagem horizontal. pytest -m e2e"""
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


def test_carrossel_navega_por_teclado(url_site, navegador):
    pagina = _pagina(navegador, 1280)
    pagina.goto(url_site + "/")
    trilho = pagina.locator("[data-trilho]")
    trilho.focus()
    assert pagina.evaluate("document.querySelector('[data-trilho]').scrollLeft") == 0
    for _ in range(6):
        pagina.keyboard.press("ArrowRight")
    pagina.wait_for_function("document.querySelector('[data-trilho]').scrollLeft > 0")
    antes = pagina.evaluate("document.querySelector('[data-trilho]').scrollLeft")
    pagina.keyboard.press("ArrowLeft")
    pagina.keyboard.press("ArrowLeft")
    pagina.wait_for_function(f"document.querySelector('[data-trilho]').scrollLeft < {antes}")


def test_carrossel_tab_leva_o_ultimo_produto_para_a_vista(url_site, navegador):
    pagina = _pagina(navegador, 1280)
    pagina.goto(url_site + "/")
    ultimo = pagina.locator(".vitrine-item .et-nome a").last
    ultimo.focus()
    pagina.wait_for_timeout(300)
    caixa = ultimo.bounding_box()
    trilho = pagina.locator("[data-trilho]").bounding_box()
    assert trilho["x"] <= caixa["x"] and caixa["x"] + caixa["width"] <= trilho["x"] + trilho["width"] + 1


def test_setas_visiveis_percorrem_a_vitrine(url_site, navegador):
    pagina = _pagina(navegador, 1280)
    pagina.goto(url_site + "/")
    proxima = pagina.locator("[data-seta='1']")
    assert proxima.is_visible()
    assert pagina.locator("[data-seta='-1']").is_disabled()
    proxima.click()
    pagina.wait_for_function("document.querySelector('[data-trilho]').scrollLeft > 0")
    pagina.wait_for_function("!document.querySelector(\"[data-seta='-1']\").disabled")


def test_carrossel_funciona_sem_js(url_site, navegador):
    ctx = navegador.new_context(viewport={"width": 1280, "height": 800}, java_script_enabled=False)
    pagina = ctx.new_page()
    pagina.goto(url_site + "/")
    assert pagina.locator("[data-setas]").is_hidden()  # setas são realce progressivo
    assert pagina.locator(".vitrine-item").count() >= 4
    assert pagina.evaluate("getComputedStyle(document.querySelector('[data-trilho]')).scrollSnapType") != "none"


def test_pergunta_da_lia_abre_o_chat_preenchido(url_site, navegador):
    pagina = _pagina(navegador, 1280)
    pagina.goto(url_site + "/")
    assert pagina.locator("#chat-corpo").is_hidden()  # a homepage abre com o chat fechado
    primeira = pagina.locator("[data-pergunta]").first
    texto = primeira.get_attribute("data-pergunta")
    primeira.click()
    assert pagina.locator("#chat-corpo").is_visible()
    assert pagina.input_value("#chat-mensagem") == texto


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
