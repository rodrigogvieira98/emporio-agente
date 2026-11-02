"""Banner da home com cinco instrumentos (etapa 20): estrutura, créditos, peso e acessibilidade do script."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emporio.web import fotos
from emporio.web.app import criar_app

WEB = Path(__file__).resolve().parents[1] / "src" / "emporio" / "web"


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    with TestClient(criar_app()) as c:
        yield c


CHAVES = ("banner-violao", "banner-guitarra", "banner-baixo", "banner-teclado", "banner-bateria")


def test_home_tem_cinco_fotos_com_alt_e_so_a_primeira_carrega_de_imediato(cliente):
    html = cliente.get("/").text
    banner = html[html.index("data-banner"):]
    banner = banner[:banner.index("</ul>")]
    assert banner.count("data-slide") == 5
    assert len(re.findall(r'<img [^>]*alt="[^"]{12,}"', banner)) == 5
    assert banner.count(' src="') == 1 and banner.count("data-src=") == 4
    assert 'fetchpriority="high"' in banner and 'aria-roledescription="carrossel"' in html
    assert 'aria-live' not in banner  # a troca automática nunca é anunciada


def test_botao_de_pausa_existe_nomeado_e_comeca_oculto_sem_js(cliente):
    html = cliente.get("/").text
    botao = re.search(r"<button[^>]*data-pausa[^>]*>", html).group(0)
    assert 'aria-label="Pausar a troca de fotos"' in botao and 'aria-pressed="false"' in botao and "hidden" in botao


def test_script_do_banner_cumpre_wcag_222():
    js = (WEB / "static" / "banner.js").read_text(encoding="utf-8")
    assert "6000" in js and "prefers-reduced-motion" in js and "visibilitychange" in js
    assert "focusin" in js and "pointerenter" in js and "Retomar a troca de fotos" in js
    assert "aria-live" not in js and "location.reload" not in js
    # o carrossel de produtos continua controlado só pela pessoa
    assert "setInterval" not in (WEB / "static" / "vitrine.js").read_text(encoding="utf-8")


def test_base_carrega_o_script_versionado(cliente):
    assert re.search(r'/static/banner\.js\?v=[0-9a-f]{10}', cliente.get("/").text)


def test_fotos_do_banner_na_ordem_e_com_credito_livre():
    lista = fotos.fotos_do_banner()
    assert tuple(f["chave"] for f in lista) == CHAVES
    cred = fotos.creditos()
    livre = re.compile(r"^(CC BY(-SA)? \d\.\d|CC0.*|Public domain.*|PD.*)$", re.I)
    for c in CHAVES:
        assert livre.match(cred[c]["licenca"]) and cred[c]["autor"] and cred[c]["link_origem"].startswith("https://commons.wikimedia.org/wiki/File:")
        assert (cred[c]["largura"], cred[c]["altura"]) == (800, 600)


def test_peso_das_fotos_do_banner():
    tamanhos = [(WEB / "static" / "fotos" / f"{c}.webp").stat().st_size for c in CHAVES]
    assert all(t <= 120 * 1024 for t in tamanhos[1:]), tamanhos
    assert sum(tamanhos) <= 600 * 1024, sum(tamanhos)


def test_creditos_pagina_e_documento_listam_as_cinco(cliente):
    pagina = cliente.get("/creditos").text
    doc = (Path(__file__).resolve().parents[1] / "docs" / "CREDITOS_IMAGENS.md").read_text(encoding="utf-8")
    for c in CHAVES:
        assert f"{c}.webp" in pagina and f"{c}.webp" in doc
    assert "Retrato da Lia" in doc
    assert json.loads((WEB / "static" / "fotos" / "creditos.json").read_text(encoding="utf-8"))


def test_cinco_bolinhas_com_rotulo_aria_current_e_sem_abertura(cliente):
    html = cliente.get("/").text
    html = html[html.index("data-banner"):html.index("data-pausa")]
    pontos = re.findall(r"<button[^>]*data-ponto=\"(\d)\"[^>]*>", html)
    assert pontos == ["0", "1", "2", "3", "4"]
    rotulos = re.findall(r'data-ponto="\d" aria-label="([^"]+)"', html)
    assert rotulos == ["Ver violão", "Ver guitarra", "Ver baixo", "Ver teclado", "Ver bateria"]
    assert len(re.findall(r'data-ponto[^>]*aria-current="true"', html)) == 1
    assert "abertura.webp" not in html


def test_nenhuma_foto_do_banner_e_abertura_e_o_arquivo_saiu():
    assert all(f["chave"] != "abertura" and "abertura" not in f["src"] for f in fotos.fotos_do_banner())
    assert not (WEB / "static" / "fotos" / "abertura.webp").exists()
    assert "abertura" not in {c["chave"] for c in fotos.creditos().values()}


def test_script_liga_as_bolinhas_e_reinicia_a_contagem():
    js = (WEB / "static" / "banner.js").read_text(encoding="utf-8")
    assert "data-ponto" in js and "aria-current" in js and "atualizar()" in js
