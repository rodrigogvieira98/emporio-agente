"""Linha do tempo do rastreio do pedido 8 (Enviado) em 1280 e 390 px. Rodar com: pytest -m e2e"""
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


@pytest.mark.parametrize("largura,altura", [(1280, 800), (390, 844)])
def test_linha_do_tempo_do_pedido_8_com_enviado_atual_e_codigo_visivel(url_site, navegador, largura, altura):
    p = navegador.new_context(viewport={"width": largura, "height": altura}).new_page()
    p.goto(url_site + "/rastreio")
    p.fill("input[name=pedido]", "8")
    p.fill("input[name=final_telefone]", "7821")
    p.click("button:has-text('Consultar')")
    p.wait_for_selector("ol.linha-tempo")
    etapas = p.locator("ol.linha-tempo > li")
    assert etapas.count() == 5
    atual = p.locator("ol.linha-tempo > li[aria-current=step]")
    assert atual.count() == 1
    assert "Enviado" in atual.inner_text() and "etapa atual" in atual.inner_text()
    codigo = atual.get_by_text("BRJL5544332BR")
    assert codigo.is_visible()
    box = codigo.bounding_box()
    assert 0 <= box["x"] and box["x"] + box["width"] <= largura
    assert p.evaluate("document.documentElement.scrollWidth") <= largura
