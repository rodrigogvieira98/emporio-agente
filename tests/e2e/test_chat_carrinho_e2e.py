"""A Lia leva ao carrinho no navegador: "Quero comprar com a Lia" só preenche o campo, a resposta traz o botão,
o botão sobrevive à troca de página e o clique (e só o clique) coloca o produto no carrinho.

Fora da execução padrão: pytest -m e2e.
"""
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
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
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
            yield navegador.new_context(viewport={"width": 1280, "height": 900}).new_page()
        finally:
            navegador.close()


def test_quero_comprar_com_a_lia_ate_o_carrinho(url_site, pagina):
    pagina.goto(f"{url_site}/produto/81")
    pagina.click(".btn-compra")
    assert pagina.input_value("#chat-mensagem") == "Quero comprar Yamaha C40 Nylon Natural"
    assert pagina.locator("#chat-log .msg.voce").count() == 0  # preencheu, não enviou
    pagina.click("#chat-enviar")
    botao = pagina.locator("#chat-log form.chat-carrinho button")
    botao.wait_for(timeout=10000)
    assert pagina.locator("#chat-log a.chat-link").first.get_attribute("href") == "/produto/81"
    # nada no carrinho antes do clique
    pagina.goto(f"{url_site}/carrinho")
    assert "Yamaha C40" not in pagina.inner_text("main")
    # a conversa salva no navegador mantém o botão funcionando depois de mudar de página
    pagina.goto(f"{url_site}/catalogo")
    pagina.click("#chat-alternar")
    botao = pagina.locator("#chat-log form.chat-carrinho button")
    botao.wait_for(timeout=5000)
    botao.click()
    pagina.wait_for_url("**/carrinho")
    assert "Yamaha C40" in pagina.inner_text("main")
