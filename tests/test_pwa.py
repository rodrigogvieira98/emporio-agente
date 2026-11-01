"""PWA: manifest, service worker, página offline e ícones."""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emporio.politicas.manual import fato
from emporio.web import apresentacao
from emporio.web.app import criar_app

WEB = Path(__file__).resolve().parents[1] / "src" / "emporio" / "web"


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    with TestClient(criar_app()) as c:
        yield c


def _png_tamanho(caminho: Path) -> tuple[int, int]:
    dados = caminho.read_bytes()
    assert dados[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", dados[16:24])


def test_manifest_valido_e_com_tipo_correto(cliente):
    r = cliente.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    assert m["name"] == fato("empresa.nome_fantasia").valor and m["short_name"] in m["name"]
    assert m["start_url"] == "/" and m["scope"] == "/" and m["display"] == "standalone" and m["lang"] == "pt-BR"
    cores = apresentacao.cores()
    assert m["theme_color"] == cores["tinta"] and m["background_color"] == cores["papel"]  # dos tokens do CSS


def test_manifest_tem_icones_192_512_e_maskable_que_existem(cliente):
    icones = cliente.get("/manifest.webmanifest").json()["icons"]
    por_proposito = {(i["sizes"], i["purpose"]) for i in icones}
    assert {("192x192", "any"), ("512x512", "any"), ("192x192", "maskable"), ("512x512", "maskable")} <= por_proposito
    for i in icones:
        assert i["type"] == "image/png"
        arquivo = WEB / i["src"].removeprefix("/")
        lado = int(i["sizes"].split("x")[0])
        assert _png_tamanho(arquivo) == (lado, lado), i["src"]
        assert cliente.get(i["src"]).status_code == 200


def test_pagina_declara_manifest_metas_e_registro_do_sw(cliente):
    html = cliente.get("/").text
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert "viewport-fit=cover" in html and 'name="theme-color"' in html
    assert 'rel="apple-touch-icon"' in html and 'name="apple-mobile-web-app-capable"' in html
    assert 'enterkeyhint="send"' in html
    assert cliente.get("/static/pwa.js").status_code == 200
    assert "apple-touch-icon" in html and cliente.get("/static/icones/apple-touch-icon-180.png").status_code == 200


def test_sw_servido_na_raiz_sem_cache_e_com_escopo_raiz(cliente):
    r = cliente.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")
    assert r.headers["service-worker-allowed"] == "/"
    cache = r.headers["cache-control"]
    assert "no-cache" in cache and "max-age=0" in cache
    assert "/*VERSAO*/" not in r.text and "/*ESTATICOS*/" not in r.text
    assert re.search(r'const VERSAO = "[^"]+";', r.text)


def test_sw_precache_lista_so_arquivos_estaticos_que_existem(cliente):
    texto = cliente.get("/sw.js").text
    lista = json.loads(re.search(r"const ESTATICOS = (\[.*?\]);", texto, re.S).group(1))
    assert "/static/site.css" in lista and "/static/ilustracoes.svg" in lista and "/static/chat.js" in lista
    assert any(x.endswith(".woff2") for x in lista) and "/static/icones/icon-512.png" in lista
    for caminho in lista:
        assert cliente.get(caminho).status_code == 200, caminho
    assert not any(x.endswith(".txt") for x in lista)  # licenças não vão para o cache


def test_sw_nunca_guarda_chat_rastreio_saude_nem_post(cliente):
    texto = cliente.get("/sw.js").text
    assert 'const SO_REDE = ["/chat", "/rastreio", "/saude"];' in texto
    assert 'pedido.method !== "GET"' in texto  # POST e qualquer outro método passam direto à rede
    # a única escrita em cache é de estático, e nunca de HTML: só há um cache.put e ele fica no ramo estático
    assert texto.count("cache.put(") == 1
    ramo_estatico = texto[texto.index("if (ehEstatico(url))"):]
    assert "cache.put(" in ramo_estatico
    assert "PAGINA_OFFLINE" in texto and "caches.match(PAGINA_OFFLINE)" in texto


def test_rota_offline_existe_e_traz_endereco_e_horario_do_manual(cliente):
    r = cliente.get("/offline")
    assert r.status_code == 200
    assert "Sem conexão" in r.text and "Preços, estoque, pedidos e a Lia precisam de internet" in r.text
    assert fato("empresa.endereco").valor["logradouro"] in r.text
    for faixa in apresentacao.loja()["horario"]:
        assert faixa.split(": ")[1] in r.text


def test_pagina_offline_nao_guarda_estado_que_envelhece(cliente):
    html = cliente.get("/offline").text
    assert "Aberta agora" not in html and "Fechada" not in html  # a faixa muda com a hora, a página fica no aparelho
    assert "R$" not in html and 'data-produto=' not in html  # nenhum preço nem produto
    assert "menu-categorias" not in html  # contagens de produto também envelhecem


def test_sw_e_manifest_nao_criam_sessao(cliente):
    for caminho in ("/sw.js", "/manifest.webmanifest", "/offline"):
        assert "set-cookie" not in cliente.get(caminho).headers, caminho


def test_icones_gerados_da_marca_propria():
    pasta = WEB / "static" / "icones"
    assert _png_tamanho(pasta / "apple-touch-icon-180.png") == (180, 180)
    assert (WEB / "static" / "marca.svg").exists()
    assert "<symbol id=\"marca\"" in (WEB / "static" / "ilustracoes.svg").read_text(encoding="utf-8")


def test_chat_mobile_usa_dvh_area_segura_e_fonte_de_16px_no_campo():
    css = (WEB / "static" / "site.css").read_text(encoding="utf-8")
    assert "100dvh" in css and "env(safe-area-inset-bottom)" in css and "env(safe-area-inset-top)" in css
    assert re.search(r"\.chat-form input \{[^}]*font-size: 1rem", css)  # 16px: o iOS não dá zoom no foco
    assert "max-width: 767px" in css  # tela cheia abaixo de 768px
