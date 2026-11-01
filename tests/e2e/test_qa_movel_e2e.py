"""QA móvel (etapa 16), um teste por item, em 360 e 390 px, com medição."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_retrato_da_lia_no_botao_e_no_painel(servidor_movel, movel):
    pagina, _, _ = movel
    pagina.goto(servidor_movel + "/")
    js = """() => [...document.querySelectorAll('img.lia-retrato')].filter(i => i.getBoundingClientRect().width > 0).map(i => {
        const r = i.getBoundingClientRect(), c = getComputedStyle(i);
        return {src: i.currentSrc, w: r.width, h: r.height, natural: i.naturalWidth, raio: c.borderRadius};})"""
    medidas = pagina.evaluate(js)  # fechada: só o botão
    pagina.click("#chat-alternar")
    medidas += pagina.evaluate(js)  # aberta: só o cabeçalho do painel
    assert len(medidas) == 2
    for m in medidas:
        assert "/static/lia-" in m["src"] and m["src"].split("?")[0].endswith(".webp") and m["natural"] > 0 and m["w"] == 44 == m["h"]
        assert m["raio"] in ("50%", "22px")
    assert "assistente virtual" in pagina.inner_text(".chat-id")


def test_post_sem_rede_mostra_aviso_e_mantem_dados(servidor_movel, movel):
    pagina, ctx, _ = movel
    pagina.goto(servidor_movel + "/rastreio")
    pagina.fill("#r-pedido", "PED-123")
    pagina.fill("#r-final", "8765")
    ctx.set_offline(True)
    pagina.tap("form.form-coluna button[type=submit]")
    pagina.wait_for_selector("[data-aviso-rede]")
    aviso = pagina.locator("[data-aviso-rede]")
    assert aviso.get_attribute("role") == "alert" and "Sem conexão" in aviso.inner_text()
    assert pagina.input_value("#r-pedido") == "PED-123" and pagina.input_value("#r-final") == "8765"
    assert pagina.url.endswith("/rastreio")
    caixa = aviso.bounding_box()
    assert 0 <= caixa["x"] and caixa["x"] + caixa["width"] <= pagina.viewport_size["width"]  # o aviso cabe na tela


def test_post_do_contato_sem_rede_mantem_dados(servidor_movel, movel):
    pagina, ctx, _ = movel
    pagina.goto(servidor_movel + "/fale-conosco")
    pagina.fill("#f-assunto", "Dúvida sobre prazo")
    ctx.set_offline(True)
    pagina.tap("main form[method=post] button[type=submit]")
    pagina.wait_for_selector("[data-aviso-rede]")
    assert pagina.input_value("#f-assunto") == "Dúvida sobre prazo" and pagina.url.endswith("/fale-conosco")


def test_urls_estaticas_versionadas_e_precache_com_reload(servidor_movel, movel):
    import re
    pagina, _, _ = movel
    pagina.goto(servidor_movel + "/")
    refs = pagina.evaluate("""() => [...document.querySelectorAll('link[href^="/static/"]:not([rel=preload]), script[src^="/static/"], img.lia-retrato')]
        .map(e => e.getAttribute('href') || e.getAttribute('src'))""")
    assert len(refs) >= 7
    for r in refs:
        assert re.fullmatch(r"/static/[\w./\-]+\?v=[0-9a-f]{10}", r), r
    sw = pagina.request.get(servidor_movel + "/sw.js").text()
    assert 'cache: "reload"' in sw
    pagina.evaluate("navigator.serviceWorker.ready.then(() => true)")
    pagina.wait_for_function("caches.keys().then(k => k.length > 0)")
    chaves = pagina.evaluate("caches.keys().then(async ks => (await (await caches.open(ks[0])).keys()).map(r => new URL(r.url).pathname))")
    assert "/static/site.css" in chaves and "/static/formularios.js" in chaves and "/static/lia-96.webp" in chaves
