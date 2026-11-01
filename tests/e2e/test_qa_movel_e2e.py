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


def test_cabecalho_movel_compacto_com_menu_recolhido_e_carrinho_visivel(servidor_movel, movel):
    pagina, _, largura = movel
    pagina.goto(servidor_movel + "/catalogo")
    m = pagina.evaluate("""() => { const q = s => document.querySelector(s).getBoundingClientRect();
        return {topo: q('.topo').height, botao: q('.menu-botao'), carrinho: q('.link-carrinho'), busca: q('.busca-topo input'),
                itens_visiveis: document.querySelector('.menu-recolhido').open,
                sobra: document.documentElement.scrollWidth - innerWidth}; }""")
    assert m["topo"] <= 140, m  # antes do ajuste o cabeçalho passava de 200 px
    assert m["botao"]["height"] >= 44 and m["botao"]["width"] >= 44
    assert m["carrinho"]["height"] >= 44 and 0 <= m["carrinho"]["x"] and m["carrinho"]["x"] + m["carrinho"]["width"] <= largura
    assert not m["itens_visiveis"] and m["sobra"] <= 0
    pagina.tap(".menu-botao")
    alvos = pagina.evaluate("""() => ['/catalogo', '/rastreio'].map(h =>
        { const r = document.querySelector('.menu-itens > a[href="' + h + '"]').getBoundingClientRect(); return [h, r.height, r.width, r.right]; })""")
    for _, alt, lar, dir_ in alvos:
        assert alt >= 44 and dir_ <= largura
    pagina.tap(".menu-categorias summary")
    assert pagina.locator(".menu-itens").is_visible() and pagina.locator(".menu-categorias ul").is_visible()
    pagina.tap(".menu-itens a[href='/rastreio']")
    pagina.wait_for_url("**/rastreio")
    assert not pagina.evaluate("document.querySelector('.menu-recolhido').open")


def test_cabecalho_em_1280_nao_muda(servidor_movel):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = p.chromium.launch()
        try:
            pagina = nav.new_page(viewport={"width": 1280, "height": 800})
            pagina.goto(servidor_movel + "/")
            assert pagina.locator(".menu-botao").is_hidden()
            for h in ("/catalogo", "/rastreio", "/carrinho"):
                assert pagina.locator(f".menu a[href='{h}']").last.is_visible()
            assert pagina.locator(".menu a[href='/perguntas-frequentes']").count() == 0  # agora só no rodapé
            assert pagina.locator(".menu-categorias summary").is_visible()
            assert pagina.evaluate("document.querySelector('.topo').getBoundingClientRect().height") < 120
        finally:
            nav.close()


def test_ritmo_da_conversa_cliente_escrevendo_resposta(servidor_movel, movel):
    pagina, _, _ = movel
    pagina.goto(servidor_movel + "/")
    pagina.tap("#chat-alternar")
    pagina.wait_for_selector("#chat:not([hidden])")
    pagina.evaluate("""() => { window.__t = {}; const log = document.getElementById('chat-log'), t0 = () => performance.now();
        new MutationObserver(ms => { for (const m of ms) { m.addedNodes.forEach(n => { if (n.nodeType !== 1) return;
            if (n.classList.contains('voce')) window.__t.voce = t0();
            else if (n.classList.contains('escrevendo')) window.__t.esc_ini = t0();
            else if (n.classList.contains('lia')) window.__t.resposta = t0(); });
          m.removedNodes.forEach(n => { if (n.nodeType === 1 && n.classList.contains('escrevendo')) window.__t.esc_fim = t0(); }); } })
          .observe(log, {childList: true}); }""")
    pagina.fill("#chat-mensagem", "Quanto custa o frete?")
    pagina.tap("#chat-enviar")
    pagina.wait_for_selector("#chat-log .msg.voce")
    assert pagina.locator("#chat-log .msg.voce").is_visible()
    pagina.wait_for_function("window.__t.resposta", timeout=15000)
    t = pagina.evaluate("window.__t")
    assert t["voce"] <= t["esc_ini"] <= t["esc_fim"] <= t["resposta"] + 5
    assert t["esc_fim"] - t["esc_ini"] >= 600, t  # a bolha de escrevendo fica visível por pelo menos 600 ms
    assert pagina.locator("#chat-log .msg.voce").count() == 1
    assert pagina.locator("#chat-log .escrevendo").count() == 0
    assert pagina.locator("#chat-log .msg.lia").count() == 2  # saudação e uma única resposta
    pagina.reload()
    pagina.tap("#chat-alternar")
    assert pagina.locator("#chat-log .escrevendo").count() == 0
    assert pagina.locator("#chat-log .msg.voce").count() == 1 and pagina.locator("#chat-log .msg.lia").count() == 2


def test_campos_com_fonte_de_16px_e_atributos_de_teclado(servidor_movel, movel):
    pagina, _, _ = movel
    ruins = []
    for caminho in ("/", "/catalogo", "/fale-conosco", "/rastreio", "/carrinho"):
        pagina.goto(servidor_movel + caminho)
        ruins += pagina.evaluate("""() => [...document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]), select, textarea')]
            .filter(e => parseFloat(getComputedStyle(e).fontSize) < 16).map(e => e.name + ':' + getComputedStyle(e).fontSize)""")
    assert ruins == []  # abaixo de 16 px o iOS aproxima a tela ao focar o campo
    pagina.goto(servidor_movel + "/produto/90")
    pagina.click("text=Adicionar ao carrinho")
    pagina.goto(servidor_movel + "/checkout")
    assert pagina.get_attribute("#cep", "autocomplete") == "postal-code"
    assert pagina.evaluate("parseFloat(getComputedStyle(document.querySelector('#forma')).fontSize)") >= 16
    pagina.goto(servidor_movel + "/rastreio")
    assert pagina.get_attribute("#r-pedido", "autocapitalize") == "characters"


def test_rastreio_rola_e_leva_foco_ao_resultado(servidor_movel, movel):
    pagina, _, _ = movel
    pagina.goto(servidor_movel + "/rastreio")
    pagina.fill("#r-pedido", "PED-999999")
    pagina.fill("#r-final", "1234")
    pagina.tap("main form button[type=submit]")
    pagina.wait_for_selector("[data-resultado-rastreio]")
    pagina.wait_for_timeout(300)
    m = pagina.evaluate("""() => { const r = document.querySelector('[data-resultado-rastreio]');
        return {foco: document.activeElement === r, topo: r.getBoundingClientRect().top, h: innerHeight}; }""")
    assert m["foco"] and 0 <= m["topo"] < m["h"] * 0.6, m


def test_fotos_do_catalogo_e_carrosseis_lazy(servidor_movel, movel):
    pagina, _, _ = movel
    pagina.goto(servidor_movel + "/catalogo")
    modos = pagina.evaluate("[...document.querySelectorAll('.grade-catalogo img')].map(i => i.getAttribute('loading'))")
    assert len(modos) > 3 and modos[:2] == ["eager", "eager"] and set(modos[2:]) == {"lazy"}, modos
    pagina.goto(servidor_movel + "/")
    modos = pagina.evaluate("[...document.querySelectorAll('.carrossel img')].map(i => i.getAttribute('loading'))")
    assert modos and set(modos) == {"lazy"}, modos
