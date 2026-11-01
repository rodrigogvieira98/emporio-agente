"""Fluxo completo da compra de demonstração em 390px: produto, carrinho, checkout, pedido e rastreio.

Fora da execução padrão: pytest -m e2e. Grava a captura docs/capturas/compra_390.png.
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from emporio.web.app import criar_app  # noqa: E402

pytestmark = pytest.mark.e2e

CAPTURAS = Path(__file__).resolve().parents[2] / "docs" / "capturas"
CRAFTER = 90  # tem promoção ativa


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
            contexto = navegador.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            yield contexto.new_page()
        finally:
            navegador.close()


def capturar(pagina, destino: Path) -> None:
    """Página inteira; a barra fixa da Lia sairia no meio da imagem, então fica fora só da captura."""
    pagina.add_style_tag(content="#chat { display: none !important; }")
    pagina.screenshot(path=str(destino), full_page=True)


def sem_rolagem_horizontal(pagina) -> bool:
    return pagina.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth") or print(
        pagina.evaluate("""() => { const W = document.documentElement.clientWidth; const o = [];
        document.querySelectorAll('body *').forEach(e => { const r = e.getBoundingClientRect();
          if (r.right > W + 1) o.push(e.tagName + '.' + e.className + ' ' + Math.round(r.right)); });
        return [...document.querySelectorAll('.menu > *')].map(e => e.className + ':' + Math.round(e.getBoundingClientRect().width)).concat(o); }""")
    )


def test_compra_de_demonstracao_completa_em_390px(url_site, celular):
    pagina = celular
    pagina.goto(f"{url_site}/produto/{CRAFTER}")
    assert "nenhum pagamento é feito" in pagina.inner_text("main")
    assert sem_rolagem_horizontal(pagina)
    pagina.click(".btn-comprar")

    pagina.wait_for_url("**/carrinho")
    assert "Crafter HT-100" in pagina.inner_text("main") and "R$ 1.967,18" in pagina.inner_text("main")
    assert pagina.locator(".contagem-carrinho").inner_text() == "1"
    assert sem_rolagem_horizontal(pagina)
    pagina.click("text=Ir para o checkout")

    pagina.wait_for_url("**/checkout")
    assert pagina.locator("button:has-text('Finalizar')").is_disabled()  # falta a cidade
    pagina.select_option("select[name=forma]", "pix")
    pagina.fill("input[name=cidade]", "Campo Grande")
    pagina.click("button:has-text('Atualizar valores')")
    pagina.wait_for_load_state()
    texto = pagina.inner_text("main")
    assert "R$ 1.967,18" in texto and "promoção -18%" in texto and "desconto do PIX" not in texto
    assert "Frete grátis" in texto
    assert sem_rolagem_horizontal(pagina)
    pagina.locator("button:has-text('Finalizar')").click()

    pagina.wait_for_url("**/pedido/DEMO-0001")
    assert "DEMO-0001" in pagina.inner_text("main") and "nenhum pagamento é feito" in pagina.inner_text("main")
    assert sem_rolagem_horizontal(pagina)
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    capturar(pagina, CAPTURAS / "compra_390.png")

    pagina.goto(f"{url_site}/rastreio")
    pagina.fill("input[name=pedido]", "DEMO-0001")
    pagina.click("button:has-text('Consultar')")
    pagina.wait_for_load_state()
    assert "DEMO-0001" in pagina.inner_text("main") and "demonstração" in pagina.inner_text("main")


def test_parcela_a_confirmar_bloqueia_a_finalizacao_em_390px(url_site, celular):
    pagina = celular
    pagina.goto(f"{url_site}/produto/89")  # Shelby SN-100: 6x fica a confirmar
    pagina.click(".btn-comprar")
    pagina.wait_for_url("**/carrinho")
    pagina.goto(f"{url_site}/checkout?forma=credito&parcelas=6&cidade=Campo+Grande")
    assert "a confirmar com a equipe" in pagina.inner_text("main").lower()  # o selo é exibido em caixa alta
    assert pagina.locator("button:has-text('Finalizar')").is_disabled()
    assert sem_rolagem_horizontal(pagina)
    capturar(pagina, CAPTURAS / "compra_confirmar_390.png")
