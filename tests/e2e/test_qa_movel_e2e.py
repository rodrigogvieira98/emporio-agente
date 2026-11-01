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


def test_lia_esconde_sugestoes_com_campo_em_foco_e_apos_primeira_mensagem(servidor_movel, movel):
    pagina, _, _ = movel
    pagina.goto(servidor_movel + "/")
    pagina.tap("#chat-alternar")
    pagina.wait_for_selector("#chat:not([hidden])")
    pagina.locator("#chat-mensagem").blur()
    assert pagina.locator(".chat-sugestoes").is_visible()
    pagina.locator("#chat-mensagem").focus()
    assert pagina.locator(".chat-sugestoes").is_hidden()
    pagina.locator("#chat-mensagem").blur()
    pagina.evaluate("document.querySelector('#chat-log').insertAdjacentHTML('beforeend', '<p class=\"msg voce\">oi</p>')")
    pagina.evaluate("document.querySelector('#chat-corpo').classList.add('ja-conversou')")
    assert pagina.locator(".chat-sugestoes").is_hidden()


@pytest.mark.parametrize("altura", [380, 300])
def test_lia_cabe_na_area_visivel_com_teclado_e_em_paisagem(servidor_movel, largura, altura):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = p.chromium.launch()
        try:
            for vp in ({"width": largura, "height": altura}, {"width": 844, "height": 390}):
                ctx = nav.new_context(viewport=vp, has_touch=True, is_mobile=True)
                pagina = ctx.new_page()
                pagina.goto(servidor_movel + "/")
                pagina.tap("#chat-alternar")
                pagina.wait_for_selector("#chat:not([hidden])")
                m = pagina.evaluate("""() => { const r = document.querySelector('#chat').getBoundingClientRect(),
                    f = document.querySelector('#chat-form').getBoundingClientRect();
                    return {topo: r.top, base: r.bottom, form_base: f.bottom, h: innerHeight, scroll: document.scrollingElement.scrollHeight <= innerHeight || getComputedStyle(document.body).overflow === 'hidden'}; }""")
                assert m["topo"] >= 0 and m["base"] <= m["h"] + 1 and m["form_base"] <= m["h"] + 1, (vp, m)
                ctx.close()
        finally:
            nav.close()


def test_lia_prende_o_foco_e_camada_absorve_o_toque_na_faixa(servidor_movel, movel):
    pagina, _, _ = movel
    pagina.goto(servidor_movel + "/")
    pagina.tap("#chat-alternar")
    pagina.wait_for_selector("#chat:not([hidden])")
    for _ in range(14):
        pagina.keyboard.press("Tab")
        assert pagina.evaluate("document.getElementById('lia').contains(document.activeElement)")
    for _ in range(14):
        pagina.keyboard.press("Shift+Tab")
        assert pagina.evaluate("document.getElementById('lia').contains(document.activeElement)")
    topo = pagina.evaluate("document.elementFromPoint(40, 20).id")
    assert topo == "lia-camada"
    url = pagina.url
    pagina.touchscreen.tap(40, 20)
    pagina.wait_for_selector("#chat", state="hidden")
    assert pagina.url == url
