"""Carrosseis da home no navegador: independencia, teclado, botoes, alcance dos produtos e 390 px."""
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

CENTRO = ".carrossel-item.e-centro"


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


def abrir(navegador, url, largura):
    pagina = navegador.new_context(viewport={"width": largura, "height": 900}).new_page()
    pagina.goto(url + "/")
    pagina.wait_for_selector("#mais .carrossel-ativo")
    return pagina


def centro(pagina, secao):
    return pagina.locator(f"#{secao} {CENTRO}").get_attribute("data-produto")


@pytest.mark.parametrize("largura", [1280, 390])
def test_avancar_um_carrossel_nao_muda_o_outro(url_site, navegador, largura):
    pagina = abrir(navegador, url_site, largura)
    antes_d, antes_m = centro(pagina, "destaques"), centro(pagina, "mais")
    pagina.locator("#mais [data-seta='1']").click()
    assert centro(pagina, "mais") != antes_m and centro(pagina, "destaques") == antes_d
    pagina.locator("#destaques [data-seta='1']").click()
    assert centro(pagina, "destaques") != antes_d


@pytest.mark.parametrize("largura", [1280, 390])
def test_teclado_e_botoes_no_para_comecar(url_site, navegador, largura):
    pagina = abrir(navegador, url_site, largura)
    a = centro(pagina, "mais")
    pagina.locator("#mais [data-carrossel]").focus()
    pagina.keyboard.press("ArrowRight")
    b = centro(pagina, "mais")
    assert b != a
    pagina.keyboard.press("ArrowLeft")
    assert centro(pagina, "mais") == a
    pagina.locator("#mais [data-seta='-1']").click()
    assert centro(pagina, "mais") != a
    assert pagina.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


@pytest.mark.parametrize("largura", [1280, 390])
def test_todos_os_produtos_da_secao_sao_alcancaveis_e_cada_card_abre_o_produto(url_site, navegador, largura):
    pagina = abrir(navegador, url_site, largura)
    ids = pagina.eval_on_selector_all("#mais .carrossel-item", "els => els.map(e => e.dataset.produto)")
    vistos = set()
    for _ in ids:
        vistos.add(centro(pagina, "mais"))
        pagina.locator("#mais [data-seta='1']").click()
    assert vistos == set(ids)
    alvo = centro(pagina, "mais")
    pagina.locator(f"#mais {CENTRO} a[href^='/produto/']").first.click()
    pagina.wait_for_url(f"**/produto/{alvo}")


@pytest.mark.parametrize("largura", [1280, 390])
def test_lia_nao_cobre_os_controles_do_para_comecar(url_site, navegador, largura):
    pagina = abrir(navegador, url_site, largura)
    pagina.evaluate("document.querySelector('#mais [data-controles]').scrollIntoView({block: 'center'})")
    pagina.wait_for_timeout(200)
    lia = pagina.locator("#chat-alternar").bounding_box()
    for botao in pagina.locator("#mais [data-controles] button").all():
        b = botao.bounding_box()
        assert (b["x"] + b["width"] <= lia["x"] or lia["x"] + lia["width"] <= b["x"]
                or b["y"] + b["height"] <= lia["y"] or lia["y"] + lia["height"] <= b["y"]), (b, lia)
