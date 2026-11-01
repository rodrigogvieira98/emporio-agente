"""Ponta a ponta com navegador. Fora da execução padrão: pytest -m e2e (precisa de playwright e chromium)."""
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
def pagina():
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            yield navegador.new_page()
        finally:
            navegador.close()


def test_catalogo_produto_rastreio_e_chat(url_site, pagina):
    pagina.goto(url_site + "/catalogo?categoria=Ukuleles")
    pagina.locator(".card a").first.click()
    pagina.wait_for_selector("h1")
    assert pagina.locator(".btn-compra").count() == 1

    pagina.goto(url_site + "/rastreio")
    pagina.fill("input[name=pedido]", "8")
    pagina.fill("input[name=final_telefone]", "7821")
    pagina.click("button:has-text('Consultar')")
    assert "BRJL5544332BR" in pagina.inner_text("main")

    pagina.click("#chat-alternar")
    pagina.fill("#chat-mensagem", "quero falar com um atendente")
    pagina.click("#chat-enviar")
    pagina.wait_for_selector("#chat-log .msg.lia:has-text('EM-')", timeout=20000)

    pagina.goto(url_site + "/politicas")  # o histórico sobrevive à troca de página (o painel volta fechado)
    pagina.click("#chat-alternar")
    assert "EM-" in pagina.inner_text("#chat-log")
