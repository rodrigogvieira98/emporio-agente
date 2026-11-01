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
    assert pagina.locator(".rodape").bounding_box()["height"] <= 96
    links = [pagina.locator(".rodape a").nth(i).bounding_box() for i in range(pagina.locator(".rodape a").count())]
    assert len(links) == 6 and len({round(b["y"]) for b in links}) == 1  # linha única
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
