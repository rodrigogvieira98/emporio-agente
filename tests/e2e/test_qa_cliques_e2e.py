"""QA de cliques no navegador: URL do checkout sem total_visto e botão da Lia compacto em 390 px."""
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
def celular():
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            contexto = navegador.new_context(viewport={"width": 390, "height": 844})
            yield contexto.new_page()
        finally:
            navegador.close()


def test_checkout_nao_grava_total_visto_na_url(url_site, celular):
    celular.goto(url_site + "/catalogo")
    celular.goto(url_site + "/produto/90")
    celular.click("text=Adicionar ao carrinho")
    celular.goto(url_site + "/checkout?forma=pix&parcelas=1")
    celular.fill("#cep", "79002-000")
    celular.wait_for_function("location.search.includes('cep=')")
    celular.wait_for_timeout(500)
    url = celular.url
    assert "total_visto" not in url and "cep=79002-000" in url and "forma=pix" in url


def test_botao_da_lia_compacto_e_nomeado_em_390(url_site, celular):
    celular.goto(url_site + "/catalogo")
    caixa = celular.locator("#chat-alternar").bounding_box()
    assert caixa["width"] <= 64
    assert "Lia" in celular.locator("#chat-alternar").inner_text()
    assert celular.locator("#chat-alternar span").bounding_box()["width"] <= 2
