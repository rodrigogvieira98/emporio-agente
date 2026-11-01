"""Fixtures compartilhadas dos testes de QA móvel: servidor local e página em 360 ou 390 px."""
from __future__ import annotations

import socket
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from emporio.web.app import criar_app  # noqa: E402


@pytest.fixture
def servidor_movel(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(criar_app(), host="127.0.0.1", port=porta, log_level="warning"))
    fio = threading.Thread(target=srv.run, daemon=True)
    fio.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{porta}"
    srv.should_exit = True
    fio.join(timeout=5)


@pytest.fixture(params=[360, 390], ids=["360px", "390px"])
def largura(request):
    return request.param


@pytest.fixture
def movel(largura):
    """(pagina, contexto, largura) em celular com toque."""
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            ctx = navegador.new_context(viewport={"width": largura, "height": 780}, has_touch=True, is_mobile=True,
                                        device_scale_factor=2)
            yield ctx.new_page(), ctx, largura
        finally:
            navegador.close()
