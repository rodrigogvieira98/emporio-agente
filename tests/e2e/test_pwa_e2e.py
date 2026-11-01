"""PWA no navegador: service worker, offline, chat sem rede e a Lia em tela cheia no celular. pytest -m e2e"""
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


def _com_sw_ativo(navegador, url, largura=1280, altura=800):
    ctx = navegador.new_context(viewport={"width": largura, "height": altura})
    pagina = ctx.new_page()
    pagina.goto(url + "/")
    pagina.evaluate("navigator.serviceWorker.ready.then(() => true)")
    pagina.wait_for_function("navigator.serviceWorker.controller !== null || true")
    pagina.reload()  # a partir daqui a página é controlada
    pagina.wait_for_function("navigator.serviceWorker.controller !== null")
    return ctx, pagina


def _abrir_chat(pagina):
    if pagina.locator("#chat").is_hidden():
        pagina.click("#chat-alternar")


def test_service_worker_registrado_com_escopo_raiz(url_site, navegador):
    ctx, pagina = _com_sw_ativo(navegador, url_site)
    escopo = pagina.evaluate("navigator.serviceWorker.getRegistration().then(r => r.scope)")
    assert escopo == url_site + "/"
    estaticos = pagina.evaluate("caches.keys().then(ks => ks.length)")
    assert estaticos >= 1
    ctx.close()


def test_sem_rede_mostra_a_pagina_offline_do_site(url_site, navegador):
    ctx, pagina = _com_sw_ativo(navegador, url_site)
    ctx.set_offline(True)
    pagina.goto(url_site + "/catalogo")
    assert "Sem conexão" in pagina.inner_text("h1")
    assert "precisam de internet" in pagina.inner_text("main")
    pagina.goto(url_site + "/produto/90")  # preço nunca vem de cache
    assert "R$" not in pagina.inner_text("main")
    pagina.goto(url_site + "/rastreio")
    assert "Sem conexão" in pagina.inner_text("h1")
    ctx.close()


def test_pagina_offline_usa_estaticos_do_cache(url_site, navegador):
    ctx, pagina = _com_sw_ativo(navegador, url_site)
    ctx.set_offline(True)
    pagina.goto(url_site + "/")
    fonte = pagina.evaluate("getComputedStyle(document.querySelector('h1')).fontFamily")
    assert "Zilla Slab" in fonte
    ok = pagina.evaluate("document.fonts.check('700 16px \"Zilla Slab\"')")
    assert ok
    ctx.close()


def test_chat_sem_rede_avisa_e_mantem_o_texto(url_site, navegador):
    ctx, pagina = _com_sw_ativo(navegador, url_site)
    pagina.goto(url_site + "/catalogo")
    _abrir_chat(pagina)
    pagina.fill("#chat-mensagem", "quero falar com um atendente")
    ctx.set_offline(True)
    pagina.click("#chat-enviar")
    pagina.wait_for_selector("#chat-log .msg.aviso-chat:has-text('Sem conexão')")
    assert pagina.input_value("#chat-mensagem") == "quero falar com um atendente"
    assert pagina.locator("#chat-log .msg.lia").count() == 1  # só a saudação: nada de resposta inventada
    ctx.set_offline(False)
    pagina.click("#chat-enviar")
    pagina.wait_for_selector("#chat-log .msg.lia:has-text('EM-')", timeout=20000)
    ctx.close()


def test_chat_nunca_fica_em_cache(url_site, navegador):
    ctx, pagina = _com_sw_ativo(navegador, url_site)
    pagina.goto(url_site + "/catalogo")
    _abrir_chat(pagina)
    pagina.fill("#chat-mensagem", "oi")
    pagina.click("#chat-enviar")
    pagina.wait_for_selector("#chat-log .msg.voce")
    urls = pagina.evaluate("caches.keys().then(async ks => { const r = []; for (const k of ks) { const c = await caches.open(k); "
                           "for (const q of await c.keys()) r.push(new URL(q.url).pathname); } return r; })")
    assert not any(u in ("/chat", "/rastreio", "/saude") for u in urls)
    assert "/offline" in urls and "/static/site.css" in urls
    assert not any(u.startswith("/produto") or u == "/catalogo" for u in urls)  # nenhuma página com preço
    ctx.close()


def test_lia_em_390px_deixa_faixa_superior_sem_rolagem_horizontal(url_site, navegador):
    ctx = navegador.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    pagina = ctx.new_page()
    pagina.goto(url_site + "/")
    pagina.click("#chat-alternar")
    caixa = pagina.locator("#chat").bounding_box()
    assert caixa["x"] == 0 and caixa["width"] == 390 and 600 <= caixa["height"] < 800  # painel com faixa superior livre
    assert caixa["y"] >= 60
    assert pagina.evaluate("document.documentElement.scrollWidth") <= 390
    campo = pagina.locator("#chat-mensagem").bounding_box()
    assert campo["y"] + campo["height"] <= 844 and campo["height"] >= 44
    assert pagina.evaluate("getComputedStyle(document.querySelector('#chat-mensagem')).fontSize") == "16px"
    assert pagina.locator("#chat-enviar").bounding_box()["height"] >= 44
    assert pagina.locator("#chat-fechar").count() == 0  # sem botão Fechar
    pagina.mouse.click(195, 20)  # fechar é tocar fora, na faixa da página
    assert pagina.locator("#chat").is_hidden()
    pagina.click("#chat-alternar")
    pagina.keyboard.press("Escape")
    assert pagina.locator("#chat").is_hidden()
    ctx.close()


def test_toques_de_44px_nos_controles_do_celular(url_site, navegador):
    ctx = navegador.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    pagina = ctx.new_page()
    pagina.goto(url_site + "/")
    for seletor in ("#chat-alternar", ".menu > a", ".busca-topo button", ".busca-topo input", ".menu-categorias summary", "[data-seta='1']",
                    ".abertura-acoes .botao"):
        assert pagina.locator(seletor).first.bounding_box()["height"] >= 44, seletor
    ctx.close()
