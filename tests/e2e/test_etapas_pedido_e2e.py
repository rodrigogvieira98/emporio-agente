"""Etapas do pedido do site (PIX e boleto) na confirmação e no rastreio, em 1280 e 390 px. Rodar com: pytest -m e2e"""
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


def fazer_pedido(pagina, url, forma):
    pagina.request.post(url + "/carrinho/adicionar", form={"produto_id": "95", "quantidade": "1"})
    pagina.goto(f"{url}/checkout?forma={forma}&cep=79002-000")
    pagina.click("button:has-text('Registrar pedido')")
    pagina.wait_for_url("**/pedido/PED-*")
    return pagina.url.rsplit("/", 1)[1]


@pytest.mark.parametrize("largura,altura", [(1280, 800), (390, 844)])
@pytest.mark.parametrize("forma,atual", [("pix", "Em separação"), ("boleto", "Aguardando pagamento")])
def test_etapas_do_pedido_do_site_sem_rolagem_horizontal(url_site, navegador, largura, altura, forma, atual):
    p = navegador.new_context(viewport={"width": largura, "height": altura}).new_page()
    numero = fazer_pedido(p, url_site, forma)
    # confirmação do pedido
    p.wait_for_selector("ol.linha-tempo")
    assert p.locator("ol.linha-tempo > li").count() == 5
    assert atual in p.locator("ol.linha-tempo > li[aria-current=step]").inner_text()
    assert p.evaluate("document.documentElement.scrollWidth") <= largura
    # rastreio
    p.goto(url_site + "/rastreio")
    p.fill("input[name=pedido]", numero)
    p.click("button:has-text('Consultar')")
    p.wait_for_selector("ol.linha-tempo")
    assert p.locator("ol.linha-tempo > li").count() == 5
    assert atual in p.locator("ol.linha-tempo > li[aria-current=step]").inner_text()
    ultimo = p.locator("ol.linha-tempo > li").last.bounding_box()
    assert 0 <= ultimo["x"] and ultimo["x"] + ultimo["width"] <= largura
    assert p.evaluate("document.documentElement.scrollWidth") <= largura
