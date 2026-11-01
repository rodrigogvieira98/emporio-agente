"""Banner da home no navegador: troca automática, pausa, reduced-motion e rolagem horizontal. pytest -m e2e"""
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

ATIVO = ".banner-slide.e-ativo"


def _abrir(navegador, url, largura=1280, **kw):
    contexto = navegador.new_context(viewport={"width": largura, "height": 800}, **kw)
    pagina = contexto.new_page()
    pagina.clock.install()
    pagina.goto(url + "/")
    return pagina


def _indice(pagina) -> int:
    return pagina.evaluate("[...document.querySelectorAll('[data-slide]')].findIndex(s => s.classList.contains('e-ativo'))")


def test_banner_troca_sozinho_a_cada_6s_e_volta_ao_inicio(url_site, navegador):
    p = _abrir(navegador, url_site)
    assert p.locator("[data-slide]").count() == 5 and _indice(p) == 0
    p.clock.run_for(6100)
    assert _indice(p) == 1
    p.wait_for_function("document.querySelectorAll('[data-slide] img[src]').length >= 3")  # a seguinte já carregou
    p.clock.run_for(6000 * 4)
    assert _indice(p) == 0  # laço
    assert p.locator("[data-slide]:not(.e-ativo)").first.get_attribute("aria-hidden") == "true"


def test_pausa_e_retoma_pelo_botao(url_site, navegador):
    p = _abrir(navegador, url_site)
    botao = p.locator("[data-pausa]")
    assert botao.is_visible() and botao.get_attribute("aria-label") == "Pausar a troca de fotos"
    assert botao.bounding_box()["width"] >= 44 and botao.bounding_box()["height"] >= 44
    botao.click()
    assert botao.get_attribute("aria-pressed") == "true" and botao.get_attribute("aria-label") == "Retomar a troca de fotos"
    p.mouse.move(5, 5)
    p.clock.run_for(20000)
    assert _indice(p) == 0
    botao.click()
    p.mouse.move(5, 5)
    p.clock.run_for(6100)
    assert _indice(p) == 1


def test_pausa_ao_passar_o_mouse_e_ao_focar(url_site, navegador):
    p = _abrir(navegador, url_site)
    p.locator(".banner").hover()
    p.clock.run_for(13000)
    assert _indice(p) == 0
    p.mouse.move(5, 5)
    p.locator("[data-pausa]").focus()
    p.clock.run_for(13000)
    assert _indice(p) == 0
    p.locator("[data-pausa]").blur()
    p.clock.run_for(6100)
    assert _indice(p) == 1


def test_reduced_motion_mostra_so_a_primeira_sem_botao(url_site, navegador):
    p = _abrir(navegador, url_site, reduced_motion="reduce")
    p.clock.run_for(30000)
    assert _indice(p) == 0 and not p.locator("[data-pausa]").is_visible()


@pytest.mark.parametrize("largura", [360, 1280])
def test_sem_rolagem_horizontal_e_altura_mantida(url_site, navegador, largura):
    p = _abrir(navegador, url_site, largura)
    assert p.evaluate("document.documentElement.scrollWidth") <= largura
    altura = p.locator(".abertura-foto").bounding_box()["height"]
    assert altura == (432 if largura == 1280 else 288)
    img = p.locator(ATIVO + " img").bounding_box()
    assert img["width"] > 300 and img["height"] == altura
