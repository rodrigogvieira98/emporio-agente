"""Rodapé colado no fim da tela em página curta e sem rolagem horizontal em larguras estreitas. Rodar com: pytest -m e2e"""
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


def _pagina(navegador, largura, altura):
    return navegador.new_context(viewport={"width": largura, "height": altura}).new_page()


@pytest.mark.parametrize("largura,altura", [(1280, 800), (1920, 1080), (2560, 1440)])
@pytest.mark.parametrize("caminho", ["/carrinho", "/nao-existe", "/checkout", "/rastreio"])
def test_rodape_termina_no_fim_da_tela_em_pagina_curta(url_site, navegador, caminho, largura, altura):
    p = _pagina(navegador, largura, altura)
    p.goto(url_site + caminho)
    medidas = p.evaluate("""() => {
        const f = document.querySelector('footer.rodape').getBoundingClientRect();
        return {fim: f.bottom + scrollY, doc: document.documentElement.scrollHeight, tela: innerHeight};
    }""")
    alvo = max(medidas["doc"], medidas["tela"])
    assert abs(alvo - medidas["fim"]) <= 2, medidas


@pytest.mark.parametrize("largura", [320, 768, 1024])
@pytest.mark.parametrize("caminho", ["/", "/catalogo", "/produto/81", "/carrinho", "/checkout", "/rastreio", "/fale-conosco",
                                     "/perguntas-frequentes", "/politicas", "/privacidade", "/creditos", "/nao-existe"])
def test_sem_rolagem_horizontal_em_largura_estreita(url_site, navegador, caminho, largura):
    p = _pagina(navegador, largura, 800)
    p.goto(url_site + caminho)
    assert p.evaluate("document.documentElement.scrollWidth") <= largura


def test_rodape_compacto_no_celular_com_alvos_de_44px(url_site, navegador):
    p = _pagina(navegador, 390, 844)
    p.goto(url_site + "/")
    assert p.locator("footer.rodape").bounding_box()["height"] <= 265
    for a in p.locator("footer.rodape a").all():
        assert a.bounding_box()["height"] >= 44
