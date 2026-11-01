"""Site real no navegador (6c e 6d), em 390 e 1280 px e por teclado. Rodar com: pytest -m e2e

Cobre: catálogo até o fim com contagem conferida no banco, rastreador de links, Lia flutuante, fechar ao clicar fora e
com Esc para cada elemento aberto, carrossel por teclado, clique e toque, Fale Conosco e percursos do cliente.
"""
from __future__ import annotations

import re
import socket
import threading
import time
from collections import deque

import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from emporio.ferramentas.produtos import buscar_produtos  # noqa: E402
from emporio.web.app import criar_app  # noqa: E402

pytestmark = pytest.mark.e2e
LARGURAS = (390, 1280)


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


def _pagina(navegador, largura: int, altura: int = 800, **kw):
    return navegador.new_context(viewport={"width": largura, "height": altura}, **kw).new_page()


def _foco(pagina) -> str:
    return pagina.evaluate("document.activeElement && (document.activeElement.id || document.activeElement.tagName)")


def _ids_vendaveis() -> int:
    return buscar_produtos(limite=1).dados["total_encontrado"]


# ---- catálogo e rastreador de links ----------------------------------------------------------------

@pytest.mark.parametrize("largura", LARGURAS)
def test_catalogo_percorre_ate_o_fim_e_a_contagem_bate_com_o_banco(url_site, navegador, largura):
    pagina = _pagina(navegador, largura)
    pagina.goto(url_site + "/catalogo")
    esperado = _ids_vendaveis()
    ids, paginas = [], 0
    while True:
        paginas += 1
        ids += pagina.eval_on_selector_all(".grade-catalogo .card", "els => els.map(e => e.dataset.produto)")
        assert int(pagina.get_attribute("[data-total]", "data-total")) == esperado
        proxima = pagina.locator("a[rel=next]")
        if proxima.count() == 0:
            break
        proxima.click()
        pagina.wait_for_load_state()
    assert paginas > 1 and len(ids) == len(set(ids)) == esperado


def _rotulo_esperado(rotulo: str) -> str | None:
    """Trecho que o título ou o h1 da página aberta precisa conter, dado o rótulo do link."""
    r = re.sub(r"^Ver produto:\s*", "", rotulo.replace("→", "").replace("←", "")).strip()
    genericos = {"Todos os instrumentos": "Catálogo", "Explorar instrumentos": "Catálogo", "Ver o catálogo completo": "Catálogo",
                 "Ver todos os instrumentos": "Catálogo", "Catálogo": "Catálogo", "Voltar ao catálogo": "Catálogo",
                 "Ver todas as perguntas": "Perguntas frequentes",
                 "Fale conosco": "Fale conosco", "Rastrear pedido": "Rastrear pedido", "Carrinho": "Carrinho", "Início": "",
                 "Voltar ao início": "", "Políticas da Loja": "Políticas", "Imagem ilustrativa": "Créditos", "Privacidade e cookies": "Privacidade", "Créditos das imagens": "Créditos",
                 "Perguntas frequentes": "Perguntas frequentes", "política de privacidade": "Privacidade",
                 "Ir para o conteúdo": None, "Página anterior": None, "Próxima página": None}
    if r in genericos:
        return genericos[r]
    if re.match(r"^\d+$", r):
        return None
    return r


@pytest.mark.parametrize("largura", LARGURAS)
def test_rastreador_visita_todo_link_interno_sem_404_500_vazio_ou_titulo_trocado(url_site, navegador, largura):
    pagina = _pagina(navegador, largura)
    fila, vistos, falhas = deque([("/", "Início")]), set(), []
    while fila and len(vistos) < 120:
        href, rotulo = fila.popleft()
        if href in vistos:
            continue
        vistos.add(href)
        resposta = pagina.goto(url_site + href)
        corpo = pagina.inner_text("main").strip()
        titulo, h1 = pagina.title(), (pagina.locator("h1").first.inner_text() if pagina.locator("h1").count() else "")
        if resposta is None or resposta.status != 200:
            falhas.append((href, "status", resposta and resposta.status))
        elif len(corpo) < 30:
            falhas.append((href, "página vazia"))
        else:
            esperado = _rotulo_esperado(rotulo)
            if esperado and esperado.lower() not in (titulo + " " + h1).lower():
                falhas.append((href, "rótulo", rotulo, titulo, h1))
        for a in pagina.locator("a[href^='/']").all():
            alvo = a.get_attribute("href")
            if not alvo or alvo.startswith(("/static", "/manifest", "/sw.js")) or alvo == "/favicon.ico":
                continue
            nome = (a.inner_text() or a.get_attribute("aria-label") or "").strip().split("\n")[0]
            if "#" in alvo and alvo.split("#")[0] in ("", "/"):
                continue
            if alvo.split("#")[0] not in vistos:
                fila.append((alvo.split("#")[0], nome))
    assert falhas == [], falhas
    assert len(vistos) >= 20  # home, catálogo paginado, categorias, produtos, FAQ, contato, privacidade, créditos...


def test_busca_do_cabecalho_retorna_o_que_diz_retornar(url_site, navegador):
    pagina = _pagina(navegador, 390)
    pagina.goto(url_site + "/")
    pagina.fill("#busca-termo", "Takamine")
    pagina.press("#busca-termo", "Enter")
    pagina.wait_for_load_state()
    nomes = pagina.eval_on_selector_all(".card .et-nome", "els => els.map(e => e.innerText)")
    total = int(pagina.get_attribute("[data-total]", "data-total"))
    assert nomes and all("takamine" in n.lower() for n in nomes) and total == len(nomes)


def test_cada_categoria_do_menu_abre_a_lista_com_a_contagem(url_site, navegador):
    pagina = _pagina(navegador, 1280)
    pagina.goto(url_site + "/")
    pagina.click(".menu-categorias summary")
    links = pagina.eval_on_selector_all(".menu-categorias li a", "els => els.map(e => [e.innerText.trim(), e.getAttribute('href')])")
    assert len(links) >= 2
    for nome, href in links[1:]:
        pagina.goto(url_site + href)
        assert pagina.locator("h1").inner_text() == nome
        assert int(pagina.get_attribute("[data-total]", "data-total")) == buscar_produtos(categoria=nome, limite=1).dados["total_encontrado"]


# ---- Lia flutuante ---------------------------------------------------------------------------------

@pytest.mark.parametrize("largura", LARGURAS)
def test_lia_abre_conversa_e_fecha_sem_abrir_sozinha(url_site, navegador, largura):
    pagina = _pagina(navegador, largura)
    for caminho in ("/", "/catalogo", "/produto/90"):
        pagina.goto(url_site + caminho)
        assert pagina.locator("#chat").is_hidden(), caminho  # começa fechada em todas as páginas
    pagina.click("#chat-alternar")
    assert pagina.locator("#chat").is_visible() and "assistente virtual" in pagina.inner_text("#chat")
    pagina.fill("#chat-mensagem", "quero falar com um atendente")
    pagina.click("#chat-enviar")
    pagina.wait_for_selector("#chat-log .msg.lia:has-text('EM-')", timeout=20000)
    pagina.goto(url_site + "/politicas")  # a conversa sobrevive à navegação, mas o painel volta fechado
    assert pagina.locator("#chat").is_hidden()
    pagina.click("#chat-alternar")
    assert "EM-" in pagina.inner_text("#chat-log")
    assert pagina.locator("#chat-fechar").count() == 0  # sem botão Fechar
    pagina.keyboard.press("Escape")
    assert pagina.locator("#chat").is_hidden() and _foco(pagina) == "chat-alternar"
    assert pagina.evaluate("document.documentElement.scrollWidth") <= largura


def _sobrepoe(a: dict, b: dict) -> bool:
    return not (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"]
                or a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"])


@pytest.mark.parametrize("largura", LARGURAS)
def test_botao_da_lia_nao_cobre_acao_de_compra_nem_o_fim_da_pagina(url_site, navegador, largura):
    pagina = _pagina(navegador, largura, 800)
    for caminho in ("/produto/95", "/carrinho", "/checkout", "/catalogo"):
        pagina.goto(url_site + caminho)
        lia = pagina.locator("#chat-alternar").bounding_box()
        for seletor in (".btn-comprar", ".btn-compra", "form button[type=submit]"):
            alvo = pagina.locator(seletor)
            if not alvo.count() or not alvo.first.is_visible():
                continue
            alvo.first.focus()  # foco por teclado rola o elemento; ele não pode parar debaixo do botão
            assert not _sobrepoe(alvo.first.bounding_box(), lia), (caminho, seletor)
        pagina.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        pagina.wait_for_timeout(100)
        for texto in pagina.locator(".rodape a, .rodape p").all():
            caixa = texto.bounding_box()
            assert not caixa or not _sobrepoe(caixa, lia), (caminho, texto.inner_text()[:40])


@pytest.mark.parametrize("largura", LARGURAS)
def test_sugestoes_da_lia_recebem_resposta_util(url_site, navegador, largura):
    pagina = _pagina(navegador, largura)
    esperado = {"Encontrar instrumento": r"Qual tipo de instrumento|opções|R\$ \d", "Consultar pedido": r"pedido|número",
                "Trocas e devoluções": r"\d+ dias|troca|devolu"}
    for rotulo, padrao in esperado.items():
        pagina.goto(url_site + "/")
        pagina.click("#chat-alternar")
        antes = pagina.locator("#chat-log .msg.lia:not(.escrevendo)").count()
        enviadas_antes = pagina.locator("#chat-log .msg.voce").count()
        botao = pagina.locator(f"#chat .chat-sugestoes button:has-text('{rotulo}')")
        enviada = botao.get_attribute("data-pergunta")
        botao.click()
        pagina.wait_for_timeout(400)
        assert pagina.locator("#chat-log .msg.voce").count() == enviadas_antes  # clicar na sugestão não envia
        assert pagina.input_value("#chat-mensagem") == enviada and pagina.evaluate("document.activeElement.id") == "chat-mensagem"
        pagina.keyboard.press("Enter")
        pagina.wait_for_function(f"document.querySelectorAll('#chat-log .msg.lia:not(.escrevendo)').length > {antes}", timeout=20000)
        assert pagina.locator("#chat-log .msg.voce").last.inner_text().strip() == enviada  # o texto enviado é o do botão
        resposta = pagina.locator("#chat-log .msg.lia:not(.escrevendo)").last.inner_text()
        assert len(resposta) > 25 and re.search(padrao, resposta, re.I), (rotulo, resposta)
        assert "Não consegui" not in resposta, (rotulo, resposta)


# ---- fechar ao clicar fora e com Esc: um teste por elemento ------------------------------------------

def test_menu_de_categorias_fecha_fora_e_com_esc_devolvendo_o_foco(url_site, navegador):
    pagina = _pagina(navegador, 1280)
    pagina.goto(url_site + "/")
    menu = pagina.locator(".menu-categorias")
    pagina.click(".menu-categorias summary")
    assert menu.get_attribute("open") is not None
    pagina.click(".menu-categorias ul", position={"x": 2, "y": 2})  # dentro (na moldura da lista) não fecha
    assert menu.get_attribute("open") is not None
    pagina.mouse.click(900, 12)  # fora (faixa de estado da loja; com a abertura compacta, (600, 600) cai em um card)
    assert menu.get_attribute("open") is None and pagina.evaluate("document.activeElement.tagName") == "SUMMARY"
    pagina.click(".menu-categorias summary")
    pagina.keyboard.press("Escape")
    assert menu.get_attribute("open") is None and pagina.evaluate("document.activeElement.tagName") == "SUMMARY"


def test_lia_no_desktop_fecha_fora_e_com_esc_e_clique_dentro_nao_fecha(url_site, navegador):
    pagina = _pagina(navegador, 1280)
    pagina.goto(url_site + "/")
    pagina.click("#chat-alternar")
    pagina.click("#chat-log")  # dentro
    assert pagina.locator("#chat").is_visible()
    pagina.mouse.click(300, 300)  # fora
    assert pagina.locator("#chat").is_hidden() and _foco(pagina) == "chat-alternar"
    pagina.click("#chat-alternar")
    pagina.keyboard.press("Escape")
    assert pagina.locator("#chat").is_hidden() and _foco(pagina) == "chat-alternar"


def test_lia_no_celular_tem_faixa_superior_e_fecha_por_toque_fora_e_por_esc(url_site, navegador):
    pagina = _pagina(navegador, 390, 800, has_touch=True, is_mobile=True)
    pagina.goto(url_site + "/")
    pagina.click("#chat-alternar")
    caixa = pagina.locator("#chat").bounding_box()
    assert caixa["width"] >= 389 and 600 <= caixa["height"] < 780 and caixa["y"] >= 60  # painel com faixa superior livre
    campo = pagina.locator("#chat-mensagem").bounding_box()
    assert campo["y"] + campo["height"] <= 800  # campo acima da borda inferior
    assert pagina.locator("#chat-fechar").count() == 0  # sem botão Fechar
    pagina.touchscreen.tap(195, 20)  # toque fora, na faixa da página
    assert pagina.locator("#chat").is_hidden()
    pagina.click("#chat-alternar")
    pagina.keyboard.press("Escape")
    assert pagina.locator("#chat").is_hidden() and _foco(pagina) == "chat-alternar"


def test_filtros_recolhidos_no_celular_fecham_fora_e_com_esc(url_site, navegador):
    pagina = _pagina(navegador, 390, 800)
    pagina.goto(url_site + "/catalogo")
    caixa = pagina.locator(".filtros-caixa")
    assert caixa.get_attribute("open") is None  # recolhidos
    pagina.click(".filtros-caixa summary")
    assert caixa.get_attribute("open") is not None
    pagina.click(".filtros-caixa input[name=termo]")  # dentro
    assert caixa.get_attribute("open") is not None
    pagina.mouse.click(195, 10)  # fora
    assert caixa.get_attribute("open") is None
    pagina.click(".filtros-caixa summary")
    pagina.keyboard.press("Escape")
    assert caixa.get_attribute("open") is None and pagina.evaluate("document.activeElement.tagName") == "SUMMARY"
    pagina.set_viewport_size({"width": 1280, "height": 800})  # no desktop ficam sempre à vista
    pagina.wait_for_function("document.querySelector('.filtros-caixa').open === true")


def test_abrir_um_elemento_fecha_o_outro(url_site, navegador):
    pagina = _pagina(navegador, 1280)
    pagina.goto(url_site + "/catalogo")
    pagina.click(".menu-categorias summary")
    pagina.click("#chat-alternar")
    assert pagina.locator(".menu-categorias").get_attribute("open") is None and pagina.locator("#chat").is_visible()
    pagina.click(".menu-categorias summary")
    assert pagina.locator("#chat").is_hidden() and pagina.locator(".menu-categorias").get_attribute("open") is not None


# ---- carrossel ---------------------------------------------------------------------------------------

def _centro(pagina) -> str:
    return pagina.evaluate("document.querySelector('.carrossel-item.e-centro').dataset.nome")


@pytest.mark.parametrize("largura", LARGURAS)
def test_carrossel_por_teclado_clique_pontos_e_arrasto(url_site, navegador, largura):
    pagina = _pagina(navegador, largura)
    pagina.goto(url_site + "/")
    pagina.wait_for_selector(".carrossel-ativo")
    pagina.evaluate("document.querySelector('[data-carrossel]').scrollIntoView({block: 'center'})")
    primeiro = _centro(pagina)
    pagina.locator("#destaques [data-carrossel]").focus()
    pagina.keyboard.press("ArrowRight")
    segundo = _centro(pagina)
    assert segundo != primeiro
    assert segundo in pagina.locator("#destaques [data-anuncio]").text_content()  # aria-live anuncia o destaque
    pagina.keyboard.press("ArrowLeft")
    assert _centro(pagina) == primeiro
    for _ in range(pagina.locator("#destaques .carrossel-item").count()):  # em laço: volta ao começo
        pagina.keyboard.press("ArrowRight")
    assert _centro(pagina) == primeiro
    pagina.click("#destaques [data-seta='1']")
    assert _centro(pagina) == segundo
    pagina.locator("#destaques [data-ponto='0']").click()
    assert _centro(pagina) == primeiro
    # clique no vizinho da direita (o de menor escala logo depois do centro) o centraliza
    pagina.evaluate("document.querySelector('[data-carrossel]').scrollIntoView({block: 'center'})")
    pagina.wait_for_timeout(700)  # termina a transição de 0,45 s antes de medir
    alvo = pagina.evaluate("""() => { const c = document.querySelector('.carrossel-item.e-centro').getBoundingClientRect();
        const lista = document.querySelector('.carrossel-lista').getBoundingClientRect(); const y = c.top + 40;
        for (let x = lista.right - 6; x > c.right + 2; x -= 4) {  // faixa visível do vizinho da direita, atrás do cartão central
          const it = (document.elementFromPoint(x, y) || document.body).closest('.carrossel-item');
          if (it && !it.classList.contains('e-centro')) return [it.dataset.nome, x, y];
        }
        return null; }""")
    assert alvo, "nenhum vizinho visível à direita do cartão central"
    pagina.mouse.click(alvo[1], alvo[2])
    assert _centro(pagina) == alvo[0]
    antes = _centro(pagina)
    caixa = pagina.locator("#destaques .carrossel-item.e-centro .preco").bounding_box()  # área sem link: um toque curto não navega
    x, y = caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2
    pagina.mouse.move(x, y)
    pagina.mouse.down()
    pagina.mouse.move(x + 20, y, steps=3)  # 20 px: abaixo do limite de 40, não navega
    pagina.mouse.up()
    assert _centro(pagina) == antes
    pagina.mouse.move(x, y)
    pagina.mouse.down()
    pagina.mouse.move(x - 80, y, steps=6)  # 80 px: acima do limite
    pagina.mouse.up()
    assert _centro(pagina) != antes
    assert pagina.evaluate("document.documentElement.scrollWidth") <= largura


def test_carrossel_toque_navega_acima_de_40px(url_site, navegador):
    pagina = _pagina(navegador, 390, has_touch=True, is_mobile=True)
    pagina.goto(url_site + "/")
    pagina.wait_for_selector(".carrossel-ativo")
    pagina.evaluate("document.querySelector('[data-carrossel]').scrollIntoView({block: 'center'})")
    antes = _centro(pagina)
    caixa = pagina.locator("#destaques .carrossel-item.e-centro").bounding_box()
    x, y = caixa["x"] + caixa["width"] / 2, caixa["y"] + 40
    pagina.evaluate("""([x, y]) => { const alvo = document.elementFromPoint(x, y); const o = {bubbles: true, pointerId: 1, isPrimary: true, pointerType: 'touch'};
        alvo.dispatchEvent(new PointerEvent('pointerdown', {...o, clientX: x, clientY: y}));
        alvo.dispatchEvent(new PointerEvent('pointerup', {...o, clientX: x - 90, clientY: y})); }""", [x, y])
    assert _centro(pagina) != antes


def test_carrossel_sem_movimento_com_reduced_motion(url_site, navegador):
    pagina = _pagina(navegador, 1280, reduced_motion="reduce")
    pagina.goto(url_site + "/")
    assert pagina.evaluate("getComputedStyle(document.querySelector('.carrossel-item')).transitionDuration") in ("0s", "1e-05s")


def test_carrossel_cai_na_grade_rolavel_sem_js(url_site, navegador):
    ctx = navegador.new_context(viewport={"width": 1280, "height": 800}, java_script_enabled=False)
    pagina = ctx.new_page()
    pagina.goto(url_site + "/")
    assert pagina.locator("#destaques [data-controles]").is_hidden()
    assert pagina.evaluate("getComputedStyle(document.querySelector('.carrossel-lista')).overflowX") == "auto"
    assert pagina.locator(".carrossel-item").count() >= 4


# ---- Fale Conosco, compra e percursos --------------------------------------------------------------

@pytest.mark.parametrize("largura", LARGURAS)
def test_fale_conosco_envia_mensagem_e_mostra_protocolo(url_site, navegador, largura):
    pagina = _pagina(navegador, largura)
    pagina.goto(url_site + "/fale-conosco")
    pagina.fill("#f-mensagem", "curta")
    pagina.click("button:has-text('Enviar mensagem')")
    assert "Diga o assunto" in pagina.inner_text("main") and pagina.input_value("#f-mensagem") == "curta"  # texto preservado em erro
    pagina.fill("#f-assunto", "Dúvida sobre um violão")
    pagina.fill("#f-mensagem", "Gostaria de saber se há violão nylon abaixo de mil reais.")
    pagina.fill("#f-contato", "cliente@example.com")
    pagina.click("button:has-text('Enviar mensagem')")
    assert "Mensagem registrada" in pagina.inner_text("main") and re.search(r"FC-\d{4}", pagina.inner_text("main"))
    assert "enviado" not in pagina.inner_text("main").lower()
    assert pagina.evaluate("document.documentElement.scrollWidth") <= largura


@pytest.mark.parametrize("largura", LARGURAS)
def test_percurso_por_teclado_encontrar_condicoes_comprar_e_acompanhar(url_site, navegador, largura):
    pagina = _pagina(navegador, largura)
    pagina.goto(url_site + "/")
    pagina.focus("#busca-termo")  # encontrar um instrumento: busca pelo teclado
    pagina.keyboard.type("Crafter HT-100")
    pagina.keyboard.press("Enter")
    pagina.wait_for_load_state()
    pagina.focus(".card .et-nome a")
    pagina.keyboard.press("Enter")
    pagina.wait_for_load_state()
    texto = pagina.inner_text("main")  # consultar condições
    assert "R$ 1.967,18" in texto and "18%" in texto and "Formas de pagamento" in texto
    pagina.focus(".btn-comprar")
    pagina.keyboard.press("Enter")
    pagina.wait_for_url("**/carrinho")
    pagina.focus("a:has-text('Finalizar pedido')")
    pagina.keyboard.press("Enter")
    pagina.wait_for_url("**/checkout**")
    assert "não gera cobrança nem entrega" in pagina.inner_text("main")  # entender o alcance da compra
    pagina.fill("input[name=cep]", "79002-000")
    pagina.wait_for_selector("#checkout-dinamico :text('Frete: Grátis')")
    pagina.focus("button:has-text('Registrar pedido')")
    pagina.keyboard.press("Enter")
    pagina.wait_for_url("**/pedido/PED-*")
    assert "Nenhum valor foi cobrado" in pagina.inner_text("main")
    numero = re.search(r"PED-\d{4}", pagina.inner_text("main")).group(0)
    pagina.goto(url_site + "/rastreio")  # acompanhar o pedido
    pagina.fill("#r-pedido", numero)
    pagina.click("button:has-text('Consultar')")
    assert numero in pagina.inner_text("main") and "R$" in pagina.inner_text("main")
    assert pagina.evaluate("document.documentElement.scrollWidth") <= largura


@pytest.mark.parametrize("caminho", ["/", "/catalogo", "/produto/90", "/politicas", "/perguntas-frequentes", "/fale-conosco", "/privacidade",
                                     "/creditos", "/rastreio", "/carrinho", "/checkout"])
def test_sem_rolagem_horizontal_em_360px(url_site, navegador, caminho):
    pagina = _pagina(navegador, 360, 740)
    pagina.goto(url_site + caminho)
    assert pagina.evaluate("document.documentElement.scrollWidth") <= 360
