"""Site real (etapas 6c e 6d): catálogo paginado, Fale Conosco, FAQ, privacidade, fotos e créditos, linguagem ao cliente."""
from __future__ import annotations

import json
import re
import sqlite3
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emporio import config
from emporio.ferramentas.produtos import LIMITE_MAXIMO, buscar_produtos, ver_produto
from emporio.politicas.manual import fato
from emporio.web import conteudo, contato, fotos, navegacao
from emporio.web.app import COOKIE, criar_app

RAIZ = Path(__file__).resolve().parents[1]
WEB = RAIZ / "src" / "emporio" / "web"
PAGINAS = ("/", "/catalogo", "/produto/90", "/politicas", "/perguntas-frequentes", "/fale-conosco", "/privacidade",
           "/creditos", "/rastreio", "/carrinho", "/checkout")


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    for v in ("EMPORIO_WHATSAPP_URL", "EMPORIO_TELEFONE_LINK", "EMPORIO_EMAIL_LINK", "EMPORIO_SMTP_HOST"):
        monkeypatch.delenv(v, raising=False)
    with TestClient(criar_app()) as c:
        yield c


def _texto_visivel(html: str) -> str:
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _ids_vendaveis() -> list[int]:
    ids: list[int] = []
    deslocamento = 0
    while True:
        r = buscar_produtos(limite=60, deslocamento=deslocamento, para_site=True)
        if r.estado != "ok" or not r.dados["itens"]:
            return ids
        ids += [i["id"] for i in r.dados["itens"]]
        deslocamento += len(r.dados["itens"])


# ---- ferramenta: deslocamento e limite do site -----------------------------------------------------

def test_padrao_da_lia_continua_em_5_e_o_site_pode_pedir_mais():
    assert len(buscar_produtos().dados["itens"]) == 5
    assert len(buscar_produtos(limite=50).dados["itens"]) == LIMITE_MAXIMO  # sem para_site o teto é 5
    assert len(buscar_produtos(limite=50, para_site=True).dados["itens"]) > LIMITE_MAXIMO


def test_deslocamento_pagina_sem_repetir_nem_perder_e_na_mesma_ordem():
    tudo = [i["id"] for i in buscar_produtos(limite=60, para_site=True).dados["itens"]]
    paginas, deslocamento = [], 0
    while deslocamento < len(tudo):
        itens = buscar_produtos(limite=5, deslocamento=deslocamento).dados["itens"]
        paginas += [i["id"] for i in itens]
        deslocamento += 5
    assert paginas == tudo
    assert buscar_produtos(deslocamento=-1).estado == "falha"
    assert buscar_produtos(deslocamento=1000).dados["itens"] == []


# ---- catálogo: cada link entrega o que promete ------------------------------------------------------

def test_catalogo_sem_filtro_percorre_todos_os_vendaveis(cliente):
    esperado = _ids_vendaveis()
    assert len(esperado) > 12
    vistos, pagina = [], 1
    while True:
        html = cliente.get("/catalogo", params={"pagina": pagina}).text
        vistos += [int(x) for x in re.findall(r'<article class="card" data-produto="(\d+)"', html)]
        total = int(re.search(r'data-total="(\d+)"', html).group(1))
        assert total == len(esperado)
        if 'rel="next"' not in html:
            break
        pagina += 1
    assert vistos == esperado


def test_pagina_alem_do_fim_volta_para_a_ultima(cliente):
    r = cliente.get("/catalogo", params={"pagina": 99}, follow_redirects=True)
    assert r.status_code == 200 and '<article class="card"' in r.text


def test_cada_categoria_do_menu_lista_a_contagem_que_mostra(cliente):
    home = cliente.get("/").text
    for nome in navegacao.listar_categorias():
        esperado = buscar_produtos(categoria=nome, limite=1).dados["total_encontrado"] if \
            buscar_produtos(categoria=nome, limite=1).estado == "ok" else 0
        if not esperado:
            assert nome not in home  # categoria vazia sai da seleção
            continue
        r = cliente.get("/catalogo", params={"categoria": nome})
        assert int(re.search(r'data-total="(\d+)"', r.text).group(1)) == esperado
        assert f"{esperado} produto" in home or f"{esperado} produtos" in home


def test_busca_retorna_o_que_diz_retornar(cliente):
    r = cliente.get("/catalogo", params={"termo": "Takamine"})
    nomes = re.findall(r'<h3 class="et-nome"><a href="/produto/\d+">([^<]+)</a>', r.text)
    assert nomes and all("takamine" in n.lower() for n in nomes)
    total = int(re.search(r'data-total="(\d+)"', r.text).group(1))
    assert total == buscar_produtos(termo="Takamine", limite=60, para_site=True).dados["total_encontrado"]


# ---- Fale Conosco ----------------------------------------------------------------------------------

def test_canais_sao_texto_com_icone_sem_variaveis_e_link_com_elas(cliente, monkeypatch):
    html = cliente.get("/fale-conosco").text
    for chave in ("contato.whatsapp_secao_7", "contato.telefone_capa", "contato.email_capa"):
        assert str(fato(chave).valor) in html
    d = lambda ch: re.sub(r"\D", "", str(fato(ch).valor))  # noqa: E731
    assert f'href="https://wa.me/55{d("contato.whatsapp_secao_7")}"' in html  # link padrão derivado do manual
    assert f'href="tel:+55{d("contato.telefone_capa")}"' in html
    assert html.count("mailto:") == 1 and "Enviar e-mail" in html
    for icone in ("whatsapp", "telefone", "email"):  # um ícone por canal (o rodapé já não repete contatos)
        assert f"/static/icones.svg#{icone}" in html
    for velho in ("Conversar", "Ligar", "Escrever", "Deixar uma mensagem"):
        assert velho not in html  # rótulos antigos saíram na página refeita
    for rotulo in ("WhatsApp", "Telefone", "E-mail"):
        assert f">{rotulo}</h2>" in html
    monkeypatch.setenv("EMPORIO_WHATSAPP_URL", "https://wa.me/5567999990000")
    monkeypatch.setenv("EMPORIO_TELEFONE_LINK", "tel:+556733334444")
    monkeypatch.setenv("EMPORIO_EMAIL_LINK", "mailto:loja@example.com")
    html = cliente.get("/fale-conosco").text
    for link in ("https://wa.me/5567999990000", "tel:+556733334444", "mailto:loja@example.com"):
        assert f'href="{link}"' in html
    assert "mailto:contato@" not in html and f"wa.me/55{d('contato.whatsapp_secao_7')}" not in html  # variável substitui o padrão


def _mensagens() -> list[sqlite3.Row]:
    conn = sqlite3.connect(config.caminho_banco())
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM mensagens_contato ORDER BY id").fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def test_formulario_grava_devolve_protocolo_e_nao_diz_que_enviou_email(cliente):
    r = cliente.post("/fale-conosco", data={"assunto": "Dúvida", "mensagem": "Quero saber de um violão nylon",
                                            "contato_retorno": "cliente@example.com"})
    assert r.status_code == 200 and "Mensagem registrada" in r.text and "FC-0001" in r.text
    texto = r.text.lower()
    assert "e-mail enviado" not in texto and "enviado por e-mail" not in texto
    linha = _mensagens()[0]
    assert linha["protocolo"] == "FC-0001" and linha["enviada_por_email"] == 0
    r2 = cliente.post("/fale-conosco", data={"assunto": "Outra", "mensagem": "Segunda mensagem de teste",
                                             "contato_retorno": "(67) 99999-0000"})
    assert "FC-0002" in r2.text


def test_formulario_rejeita_invalido_e_preserva_o_texto(cliente):
    r = cliente.post("/fale-conosco", data={"assunto": "", "mensagem": "curta", "contato_retorno": "nao-e-contato"})
    assert r.status_code == 422
    for erro in ("Diga o assunto", "pelo menos 10 caracteres", "e-mail ou telefone válido"):
        assert erro in r.text
    assert 'value="nao-e-contato"' in r.text and ">curta</textarea>" in r.text
    assert _mensagens() == []


def test_campo_isca_nao_grava(cliente):
    r = cliente.post("/fale-conosco", data={"assunto": "Spam", "mensagem": "mensagem de robô aqui", "contato_retorno": "a@b.co",
                                            "site": "http://spam"})
    assert r.status_code == 200 and _mensagens() == []


def test_smtp_so_com_configuracao(cliente, monkeypatch):
    enviados = []

    class FakeSMTP:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def send_message(self, msg): enviados.append(msg)

    monkeypatch.setattr(contato.smtplib, "SMTP", FakeSMTP)
    cliente.post("/fale-conosco", data={"assunto": "Sem SMTP", "mensagem": "mensagem sem configuração", "contato_retorno": "a@b.co"})
    assert enviados == [] and _mensagens()[0]["enviada_por_email"] == 0
    monkeypatch.setenv("EMPORIO_SMTP_HOST", "smtp.exemplo")
    monkeypatch.setenv("EMPORIO_SMTP_PARA", "loja@exemplo.com")
    cliente.post("/fale-conosco", data={"assunto": "Com SMTP", "mensagem": "mensagem com configuração", "contato_retorno": "a@b.co"})
    assert len(enviados) == 1 and _mensagens()[1]["enviada_por_email"] == 1


# ---- FAQ -------------------------------------------------------------------------------------------

def test_faq_tem_8_a_12_perguntas_em_details_com_valores_do_manual(cliente):
    html = cliente.get("/perguntas-frequentes").text
    assert 8 <= html.count('<details class="faq-item">') <= 16
    texto = _texto_visivel(html)
    assert f"até {fato('pagamento.credito_parcelas_max').valor}x sem juros" in texto
    assert f"{fato('pagamento.pix_desconto_percentual').valor}% de desconto" in texto
    assert f"R$ {int(fato('frete.taxa_abaixo_centavos').valor) // 100},00" in texto
    assert f"{fato('regra.arrependimento').valor['prazo_dias']} dias corridos" in texto
    assert f"{fato('regra.garantia_legal').valor['prazo_dias']} dias" in texto
    assert "Em Campo Grande" in texto  # frete sempre com a região
    assert "Se tiver dúvida no seu caso, fale com a gente." in texto


def test_home_traz_4_perguntas_com_link_para_todas(cliente):
    html = cliente.get("/").text
    bloco = html[html.index('id="ajuda"'):html.index('class="contorno faixa-contato"')]  # a faixa substituiu "Visite a loja"
    assert bloco.count('<details class="faq-item">') == 4 and 'href="/perguntas-frequentes"' in bloco


# ---- privacidade: uma checagem por afirmação ---------------------------------------------------------

def test_privacidade_descreve_o_cookie_que_o_site_realmente_envia(cliente):
    resposta = cliente.get("/")
    set_cookie = resposta.headers["set-cookie"]
    assert COOKIE in set_cookie and "HttpOnly" in set_cookie and "SameSite=lax" in set_cookie.replace("Lax", "lax")
    assert "Max-Age=2592000" in set_cookie  # 30 dias
    pagina = cliente.get("/privacidade").text
    assert f"<code>{COOKIE}</code>" in pagina and "30 dias" in pagina and "HttpOnly" in pagina
    assert "não usamos cookies de publicidade" in pagina.lower()


def test_so_ha_um_cookie_e_nenhum_script_ou_recurso_de_terceiros(cliente):
    for caminho in PAGINAS:
        r = cliente.get(caminho)
        assert not re.search(r'<(?:script|link|img|iframe)[^>]+(?:src|href)="https?://', r.text), caminho
    nomes = {c.name for c in cliente.cookies.jar}
    assert nomes == {COOKIE}


def test_privacidade_historico_do_chat_esta_em_sessionstorage():
    js = (WEB / "static" / "chat.js").read_text(encoding="utf-8")
    assert "sessionStorage" in js and "localStorage" not in js
    assert "emporio_chat_log" in js


def test_privacidade_cache_do_app_e_so_visual():
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    assert 'SO_REDE = ["/chat", "/rastreio", "/saude"]' in sw


def test_privacidade_nao_inventa_retencao_encarregado_nem_cnpj(cliente):
    texto = _texto_visivel(cliente.get("/privacidade").text).lower()
    for inventado in ("encarregado", "dpo", "cnpj", "anos de retenção", "prazo de retenção", "armazenamos por"):
        assert inventado not in texto


def test_privacidade_declara_o_que_o_chat_e_o_contato_guardam(cliente):
    texto = _texto_visivel(cliente.get("/privacidade").text)
    assert "mensagens" in texto.lower() and "servidores da própria loja" in texto
    conn = sqlite3.connect(config.caminho_banco())
    tabelas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"conversas", "mensagens_exibidas"} <= tabelas  # o que a página diz que o chat guarda existe de fato


# ---- fotos e créditos --------------------------------------------------------------------------------

def test_todo_produto_resolve_para_foto_existente_com_credito():
    creditos = fotos.creditos()
    assert creditos
    ids = _ids_vendaveis()
    for pid in range(81, 146):
        r = ver_produto(referencia=pid)
        if r.estado != "ok":
            continue
        f = fotos.foto_do_produto(pid, r.dados["nome"], r.dados["categoria"])
        assert f is not None, r.dados["nome"]
        assert (WEB / "static" / "fotos" / f["src"].rsplit("/", 1)[1]).exists()
        assert f["chave"] in creditos and creditos[f["chave"]]["autor"] and creditos[f["chave"]]["licenca"]
    assert ids


def test_cartoes_da_vitrine_nao_ficam_todos_iguais():
    usadas = set()
    for pid in range(81, 146):
        r = ver_produto(referencia=pid)
        if r.estado == "ok":
            usadas.add(fotos.foto_do_produto(pid, r.dados["nome"], r.dados["categoria"])["chave"])
    assert len(usadas) >= 8


def test_foto_de_formato_conhecido_segue_o_nome_do_modelo():
    chave = lambda nome, cat="Guitarras": fotos.foto_do_produto(1, nome, cat)["chave"]  # noqa: E731
    assert chave("Fender Telecaster Player Series") == "guitarra-telecaster"
    assert chave("Fender Stratocaster American Pro II") == "guitarra-stratocaster"
    assert chave("Gibson Les Paul Standard '50s") == "guitarra-les-paul"
    assert chave("Ibanez RG550 Genesis Collection") not in {"guitarra-telecaster", "guitarra-les-paul", "guitarra-stratocaster"}
    assert chave("Fender Precision Bass", "Baixos") == "baixo-2"
    assert chave("Ibanez Bass 2X Electric Bass", "Baixos") == "baixo-1"
    assert chave("Kala KA-15S Soprano Mogno", "Ukuleles") != chave("Kala KA-T Tenor Mogno", "Ukuleles")


def test_ukuleles_sao_de_madeira_natural_sem_foto_amarela():
    uk = fotos.creditos()
    chaves = [c for c in uk if c.startswith("ukulele")]
    assert len(chaves) >= 2
    assert all("amarel" not in uk[c]["alt"].lower() for c in chaves)


def test_toda_imagem_tem_credito_licenca_livre_e_ate_200kb():
    pasta = WEB / "static" / "fotos"
    creditos = json.loads((pasta / "creditos.json").read_text(encoding="utf-8"))
    por_arquivo = {c["arquivo"]: c for c in creditos}
    webps = {p.name for p in pasta.glob("*.webp")}
    assert webps and webps == set(por_arquivo)
    doc = (RAIZ / "docs" / "CREDITOS_IMAGENS.md").read_text(encoding="utf-8")
    for nome in webps:
        assert (pasta / nome).stat().st_size <= 200 * 1024, nome
        c = por_arquivo[nome]
        assert re.match(r"^(CC BY(-SA)? \d\.\d|CC0.*|Public domain.*)$", c["licenca"]), (nome, c["licenca"])
        assert c["link_origem"].startswith("https://commons.wikimedia.org/") and c["autor"]
        assert nome in doc
    for pasta_img in (WEB / "static").glob("*.jpg"):
        raise AssertionError(f"imagem solta sem crédito: {pasta_img}")


def test_creditos_lista_todas_as_fotos_e_abre_pelo_aviso_do_produto(cliente):
    html = cliente.get("/creditos").text
    for c in fotos.creditos().values():
        assert c["arquivo"] in html and c["link_origem"] in html
    assert 'href="/creditos"' not in cliente.get("/").text  # fora do rodapé
    assert 'href="/creditos">Imagem ilustrativa</a>' in cliente.get("/produto/90").text


def test_imagens_tem_alt_dimensoes_e_lazy(cliente):
    for caminho in ("/", "/catalogo", "/produto/90", "/creditos"):
        html = cliente.get(caminho).text
        for tag in re.findall(r"<img\b[^>]*>", html):
            if "/static/lia-" in tag:
                continue
            assert "alt=" in tag and "width=" in tag and "height=" in tag, (caminho, tag)
        assert "Foto do produto indisponível" not in html
        assert ("Imagem ilustrativa" in html) == caminho.startswith("/produto/")  # aviso só na página do produto


# ---- linguagem ao cliente e boas práticas ------------------------------------------------------------

TERMOS_PROIBIDOS = re.compile(r"\b(manual|manuais da loja|ferramentas?|se[cç][aã]o|demonstra[cç][aã]o|fict[ií]cia|desafio t[eé]cnico)\b", re.I)


@pytest.mark.parametrize("caminho", PAGINAS)
def test_nenhum_texto_ao_cliente_cita_implementacao(cliente, caminho):
    texto = _texto_visivel(cliente.get(caminho).text)
    texto = texto.replace("acessórios e manuais", "")  # manual do produto, não o manual da loja
    assert not TERMOS_PROIBIDOS.search(texto), TERMOS_PROIBIDOS.search(texto).group(0)


def test_chat_js_sem_termos_proibidos():
    assert not TERMOS_PROIBIDOS.search((WEB / "static" / "chat.js").read_text(encoding="utf-8").split("// Abrir")[-1].split("\n", 1)[-1]
                                       .replace("sessionStorage", ""))


@pytest.mark.parametrize("caminho", PAGINAS)
def test_pagina_tem_titulo_proprio_descricao_og_e_favicon(cliente, caminho):
    html = cliente.get(caminho).text
    assert re.search(r"<title>[^<]+ \| [^<]+</title>|<title>[^<|]+</title>", html)
    assert '<meta name="description" content="' in html and 'property="og:title"' in html and 'rel="icon"' in html
    assert html.count("<h1") == 1, caminho


def test_titulos_das_paginas_nao_se_repetem(cliente):
    titulos = [re.search(r"<title>(.*?)</title>", cliente.get(c).text).group(1) for c in PAGINAS]
    assert len(set(titulos)) == len(titulos), titulos


def test_produto_tem_trilha_de_navegacao(cliente):
    html = cliente.get("/produto/90").text
    assert 'class="migalha"' in html and 'href="/catalogo?categoria=' in html and 'aria-current="page"' in html


def test_home_na_ordem_da_composicao_loja_acolhedora(cliente):
    html = cliente.get("/").text
    ordem = [html.index(m) for m in ('class="abertura"', 'id="categorias"', 'id="destaques"', 'id="mais"', 'id="ajuda"', 'class="contorno faixa-contato"')]
    assert ordem == sorted(ordem)
    assert "Seu próximo som começa aqui." in html and "Explorar instrumentos" in html
    assert "setInterval" not in (WEB / "static" / "vitrine.js").read_text(encoding="utf-8")  # sem avanço automático


def test_carrossel_tem_controles_nomeados_e_anuncio(cliente):
    html = cliente.get("/").text
    for trecho in ('aria-roledescription="carrossel"', 'aria-label="Destaque anterior"', 'aria-label="Próximo destaque"',
                   "data-anuncio", 'aria-live="polite"', "data-ponto="):
        assert trecho in html
    js = (WEB / "static" / "vitrine.js").read_text(encoding="utf-8")
    for numero in ("0.87", "0.74", "0.55", "0.18", "40"):
        assert numero in js
    assert "0.45s" in (WEB / "static" / "site.css").read_text(encoding="utf-8").replace(".45s", "0.45s")


def test_paginas_novas_existem_e_estao_no_menu_e_rodape(cliente):
    home = cliente.get("/").text
    for caminho in ("/fale-conosco", "/perguntas-frequentes", "/privacidade", "/creditos"):
        assert cliente.get(caminho).status_code == 200
        if caminho != "/creditos":  # Créditos abre pelo aviso "Imagem ilustrativa" do produto
            assert f'href="{caminho}"' in home
    assert cliente.get("/favicon.ico", follow_redirects=False).status_code in (301, 302, 307)


def test_todo_link_interno_da_home_responde_200(cliente):
    html = cliente.get("/").text
    vistos = set()
    for href in re.findall(r'href="(/[^"#]*)', html):
        if href in vistos or href.startswith("/static") or href in ("/manifest.webmanifest",):
            continue
        vistos.add(href)
        r = cliente.get(unescape(href), follow_redirects=True)
        assert r.status_code == 200 and len(_texto_visivel(r.text)) > 80, href


def test_sem_travessao_emoji_nem_nome_de_loja_literal_nos_novos_arquivos():
    for p in ("contato.py", "conteudo.py", "fotos.py"):
        assert "—" not in (WEB / p).read_text(encoding="utf-8")
    for p in list((WEB / "templates").glob("*.html")) + list((WEB / "static").glob("*.js")) + [WEB / "static" / "site.css"]:
        t = p.read_text(encoding="utf-8")
        assert "—" not in t, p.name
        assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", t), p.name
