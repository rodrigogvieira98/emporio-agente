"""Ajustes finais de tela (etapa 12): bolha otimista do chat, falha que devolve o texto, FAQ da home. Rodar com: pytest -m e2e"""
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
TEXTO = "quero falar com um atendente"


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


def _pagina(navegador, largura=1280, altura=800):
    return navegador.new_context(viewport={"width": largura, "height": altura}).new_page()


def test_bolha_aparece_antes_da_resposta_e_nao_duplica(url_site, navegador):
    pagina = _pagina(navegador)
    presas = []
    pagina.route("**/chat", lambda rota: presas.append(rota))  # segura a resposta do servidor
    pagina.goto(url_site + "/")
    pagina.click("#chat-alternar")
    pagina.fill("#chat-mensagem", TEXTO)
    pagina.click("#chat-enviar")
    pagina.wait_for_selector("#chat-log .msg.voce")
    assert pagina.locator("#chat-log .msg.voce").inner_text().strip() == TEXTO
    assert pagina.input_value("#chat-mensagem") == ""  # campo limpo
    assert pagina.locator("#chat-espera").is_visible()  # indicador "A Lia está respondendo..."
    assert pagina.locator("#chat-log .msg.lia").count() == 1  # só a saudação: a resposta ainda não chegou
    assert len(presas) == 1
    presas[0].continue_()
    pagina.wait_for_selector("#chat-log .msg.lia:has-text('EM-')", timeout=20000)
    assert pagina.locator("#chat-log .msg.voce").count() == 1  # sem duplicar
    classes = pagina.eval_on_selector_all("#chat-log .msg", "ns => ns.map(n => n.classList.contains('voce') ? 'voce' : 'lia')")
    assert classes == ["lia", "voce", "lia"]  # ordem: saudação, cliente, Lia
    pagina.reload()  # o histórico guardado também não duplica
    pagina.click("#chat-alternar")
    assert pagina.locator("#chat-log .msg.voce").count() == 1


@pytest.mark.parametrize("modo", ["sem_rede", "ocupada", "invalida"])
def test_falha_tira_a_bolha_e_devolve_o_texto(url_site, navegador, modo):
    pagina = _pagina(navegador)
    fragmento = '<p class="msg voce">%s</p><p class="msg aviso-chat">Aviso do servidor.</p>' % TEXTO

    def rota(r):
        if modo == "sem_rede":
            r.abort()
        else:
            r.fulfill(status=503 if modo == "ocupada" else 422, content_type="text/html; charset=utf-8", body=fragmento)

    pagina.route("**/chat", rota)
    pagina.goto(url_site + "/")
    pagina.click("#chat-alternar")
    pagina.fill("#chat-mensagem", TEXTO)
    pagina.click("#chat-enviar")
    pagina.wait_for_selector("#chat-log .msg.aviso-chat")
    assert pagina.locator("#chat-log .msg.voce").count() == 0  # a bolha saiu
    assert pagina.input_value("#chat-mensagem") == TEXTO  # o texto voltou ao campo
    assert pagina.locator("#chat-log .msg.lia").count() == 1  # nenhuma resposta inventada
    pagina.reload()
    pagina.click("#chat-alternar")
    assert pagina.locator("#chat-log .msg.voce").count() == 0  # nem no histórico guardado


def test_faq_da_home_tem_a_largura_da_faixa_de_contato_e_o_link_alinhado(url_site, navegador):
    pagina = _pagina(navegador, 1280)
    pagina.goto(url_site + "/")
    faq = pagina.locator("#ajuda .faq").bounding_box()
    faixa = pagina.locator(".faixa-contato .cartao-3").bounding_box()
    assert abs(faq["x"] - faixa["x"]) <= 1 and abs(faq["width"] - faixa["width"]) <= 1
    link = pagina.locator("#ajuda .secao-cabeca a").bounding_box()
    titulo = pagina.locator("#t-ajuda").bounding_box()
    assert abs((link["x"] + link["width"]) - (faq["x"] + faq["width"])) <= 1  # à direita, na borda do bloco
    assert abs((link["y"] + link["height"] / 2) - (titulo["y"] + titulo["height"] / 2)) <= 12  # na linha do título
    assert pagina.evaluate("document.documentElement.scrollWidth") <= 1280
