"""Homepage e identidade visual (etapa 6b): vitrine, categorias, expediente, aviso e regras da SPEC."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emporio.ferramentas.condicoes import calcular_condicoes
from emporio.ferramentas.produtos import buscar_produtos
from emporio.ferramentas.promocoes import listar_promocoes
from emporio.politicas.manual import fato
from emporio.web import apresentacao, navegacao
from emporio.web.app import criar_app

WEB = Path(__file__).resolve().parents[1] / "src" / "emporio" / "web"
PROMOCOES_ATIVAS = (127, 121, 90, 94)


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    with TestClient(criar_app()) as c:
        yield c


def _vitrine(html: str) -> str:
    """Destaques (carrossel) e grade, as duas faixas de produtos da homepage (6d)."""
    return html[html.index('id="destaques"'):html.index('id="ajuda"')]


def _itens(vitrine: str) -> list[int]:
    return [int(x) for x in re.findall(r'<article class="card" data-produto="(\d+)"', vitrine)]


def test_vitrine_traz_as_quatro_promocoes_ativas_primeiro(cliente):
    itens = _itens(_vitrine(cliente.get("/").text))
    assert set(itens[:4]) == set(PROMOCOES_ATIVAS)  # o carrossel de destaques vem primeiro
    assert 4 < len(itens) <= 12
    assert len(itens) == len(set(itens))


def test_vitrine_mostra_valores_do_crafter_ht_100(cliente):
    v = _vitrine(cliente.get("/").text)
    bloco = v[v.index('data-produto="90"'):]
    bloco = bloco[:bloco.index("</article>")]
    assert "Crafter HT-100" in bloco
    assert "R$ 2.399,00" in bloco and "-18%" in bloco and "R$ 1.967,18" in bloco


def test_vitrine_valores_das_promocoes_vem_da_ferramenta(cliente):
    v = _vitrine(cliente.get("/").text)
    for p in listar_promocoes().dados["promocoes"]:
        bloco = v[v.index(f'data-produto="{p["produto_id"]}"'):]
        bloco = bloco[:bloco.index("</article>")]
        assert f"-{p['percentual']}%" in bloco
        assert apresentacao.brl(p["final_centavos"]) in bloco and apresentacao.brl(p["original_centavos"]) in bloco


def test_vitrine_sem_promocao_inativa(cliente):
    html = cliente.get("/").text
    v = _vitrine(html)
    assert 95 not in _itens(v)  # o produto da promoção 4 (inativa)
    assert "-12%" not in html and "R$ 1.935,12" not in html


def test_vitrine_item_sem_promocao_mostra_condicao_pix_da_ferramenta(cliente):
    v = _vitrine(cliente.get("/").text)
    simples = next(i for i in _itens(v) if i not in PROMOCOES_ATIVAS)
    pix = calcular_condicoes(produto_id=simples, forma="pix").dados
    bloco = v[v.index(f'data-produto="{simples}"'):]
    bloco = bloco[:bloco.index("</article>")]
    assert apresentacao.brl(pix["final_centavos"]) in bloco and f"{pix['pix_percentual']}% de desconto" in bloco


def test_categoria_sem_produto_vendavel_sai_da_selecao_e_sem_em_breve(cliente):
    """6d: ausência no catálogo não comprova lançamento, então categoria vazia não aparece nem como 'em breve'."""
    html = cliente.get("/").text
    vazias = [c for c in navegacao.listar_categorias() if buscar_produtos(categoria=c, limite=1).estado != "ok"]
    assert len(vazias) == 3
    for nome in vazias:
        assert nome not in html
    assert "Em breve" not in html and "em breve" not in html
    assert "/catalogo?categoria=Viol" in html  # as com produto continuam com link


def test_toda_categoria_tem_ilustracao_propria():
    ids = apresentacao.IDS_ILUSTRACAO
    for nome in navegacao.listar_categorias():
        assert apresentacao.ilustracao(nome) != apresentacao.ILUSTRACAO_PADRAO, nome
        assert apresentacao.ilustracao(nome) in ids
    assert apresentacao.ilustracao("Categoria que nao existe") == apresentacao.ILUSTRACAO_PADRAO


def test_faixa_aberta_agora(cliente):  # a fixture global fixa sábado, 10h
    html = cliente.get("/").text
    assert "Aberta agora" in html and "Fechada" not in html.split("</header>")[0]
    sabado = next(r for r in fato("horario.funcionamento").valor if 5 in r["dias"])
    assert f"hoje até {apresentacao.hora_br(sabado['fecha'])}" in html


def test_faixa_fechada_mostra_quando_abre(cliente, monkeypatch):
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-10-31T14:00:00")  # sábado depois do fechamento
    topo = cliente.get("/").text.split("</header>")[0]
    assert "Fechada" in topo and "Aberta agora" not in topo
    segunda = next(r for r in fato("horario.funcionamento").valor if 0 in r["dias"])
    assert f"abre segunda-feira às {apresentacao.hora_br(segunda['abre'])}" in topo


def test_faixa_fechada_no_domingo(cliente, monkeypatch):
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-11-01T10:00:00")
    topo = cliente.get("/").text.split("</header>")[0]
    assert "Fechada" in topo and "abre amanhã" in topo


def test_site_nao_diz_que_a_loja_e_ficticia(cliente):
    """6c: o aviso de loja fictícia sai do site e fica só no README."""
    for caminho in ("/", "/catalogo", "/politicas", "/fale-conosco", "/perguntas-frequentes"):
        assert "fictícia" not in cliente.get(caminho).text, caminho


def test_home_nao_tem_como_funciona_nem_faixa_da_lia_nem_botao_da_lia_no_header(cliente):
    html = cliente.get("/").text
    assert "Como funciona comprar aqui" not in html and 'id="como-funciona"' not in html
    assert "Pergunte para a Lia" not in html and "lia-chamada" not in html
    assert "data-abrir-chat" not in html.split("</header>")[0]


def test_lia_flutuante_comeca_fechada_com_sugestoes(cliente):
    html = cliente.get("/").text
    painel = html[html.index('id="chat"'):html.index('id="chat-alternar"')]
    assert re.search(r'id="chat"[^>]* hidden>', html)  # nunca abre sozinha
    assert "assistente virtual" in painel and "chat-fechar" not in html
    assert len(re.findall(r"<button type=\"button\" data-pergunta=", painel)) == 3
    assert "Lia &middot; conversar" in html


def test_faixa_sem_endereco_rodape_tem_endereco_completo_e_fale_conosco_tem_horario_sem_mapa_externo(cliente):
    html = cliente.get("/").text
    faixa = html[html.index('class="contorno faixa-contato"'):html.index("<footer")]
    e = fato("empresa.endereco").valor
    assert e["logradouro"] not in faixa and e["cep"] in html[html.index("<footer"):]
    assert 'href="/fale-conosco"' in faixa and "<iframe" not in html
    pagina = cliente.get("/fale-conosco").text
    assert pagina.count(e["logradouro"]) == 1
    assert "<table" in pagina and "<iframe" not in pagina


def test_pagina_sem_recurso_externo_sem_travessao_e_sem_emoji(cliente):
    for caminho in ("/", "/catalogo", "/produto/90", "/politicas", "/rastreio", "/fale-conosco", "/perguntas-frequentes", "/privacidade"):
        html = cliente.get(caminho).text
        if caminho not in ("/politicas", "/privacidade"):  # ali o texto é a transcrição fiel do manual, que traz travessão
            assert "—" not in html and "–" not in html, caminho
        # única exceção: o host do WhatsApp (wa.me); qualquer outro recurso externo segue proibido
        assert not re.search(r'(?:src|href)="https?://(?!wa\.me/)', html), caminho
        assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", html), caminho


def test_estaticos_da_identidade_sao_servidos(cliente):
    for caminho in ("/static/ilustracoes.svg", "/static/marca.svg", "/static/site.css", "/static/vitrine.js",
                    "/static/fontes/ZillaSlab-700-latin.woff2", "/static/fontes/PublicSans-var-latin.woff2"):
        assert cliente.get(caminho).status_code == 200, caminho


def test_fontes_sao_no_maximo_quatro_e_cada_familia_tem_licenca():
    fontes = list((WEB / "static" / "fontes").glob("*.woff2"))
    assert 0 < len(fontes) <= 4
    for familia, licenca in (("ZillaSlab", "OFL-ZillaSlab.txt"), ("PublicSans", "OFL-PublicSans.txt")):
        assert any(f.name.startswith(familia) for f in fontes)
        assert "SIL OPEN FONT LICENSE" in (WEB / "static" / "fontes" / licenca).read_text(encoding="utf-8").upper()


def test_nenhum_recurso_externo_no_css_e_js():
    for arq in list(WEB.rglob("*.css")) + [p for p in WEB.rglob("*.js") if "htmx" not in p.name]:
        texto = arq.read_text(encoding="utf-8").replace("http://www.w3.org/2000/svg", "")  # namespace, não é requisição
        assert not re.search(r"https?://", texto), arq.name


PROIBIDOS = [re.compile(p, re.I) for p in (
    r"\(?\d{2}\)?\s?\d{4,5}-\d{4}", r"\b\d{5}-\d{3}\b", r"R\$\s?\d", r"\b\d{1,2}:\d{2}\b",
    r"Emp[óo]rio da M[úu]sica", r"Campo Grande", r"Rua 14", r"@\w+\.com", "—")]


def test_fato_de_loja_fora_de_templates_css_js_svg_e_manifest():
    """Cobre também os arquivos que o teste de literais original não lista (js novos, svg, manifest)."""
    sufixos = {".html", ".css", ".js", ".svg", ".webmanifest", ".json"}
    arquivos = [p for p in WEB.rglob("*") if p.is_file() and p.suffix in sufixos and "htmx" not in p.name]
    assert any(p.name == "vitrine.js" for p in arquivos) and any(p.suffix == ".svg" for p in arquivos)
    achados = [(p.name, rx.pattern) for p in arquivos for rx in PROIBIDOS if rx.search(p.read_text(encoding="utf-8"))]
    assert achados == []


# ---- contraste AA dos pares de cor usados para texto --------------------------------------------------

def _tokens() -> dict[str, str]:
    css = (WEB / "static" / "site.css").read_text(encoding="utf-8")
    return dict(re.findall(r"--([a-z-]+):\s*(#[0-9A-Fa-f]{6})", css))


def _luz(hexa: str) -> float:
    canais = [int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_luz(a), _luz(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


PARES_TEXTO = [  # (texto, fundo): tokens da identidade Palco e madeira
    ("tinta", "creme"), ("tinta", "creme-claro"), ("tinta", "creme-escuro"), ("madeira", "creme"), ("madeira", "creme-claro"),
    ("cinza-texto", "creme"), ("cinza-texto", "creme-claro"), ("cinza-texto", "creme-escuro"), ("alerta", "creme"), ("alerta", "creme-claro"),
    ("creme-claro", "palco"), ("creme-claro", "palco-claro"), ("creme-escuro", "palco"), ("ipe", "palco"), ("ipe", "palco-claro"),
    ("palco", "ipe"), ("palco", "ipe-escuro"), ("mata", "creme"), ("mata", "creme-claro"), ("mata", "mata-claro"),
    ("tinta", "mata-claro"), ("tinta", "ipe"), ("creme", "palco"), ("creme-claro", "madeira"),
]


@pytest.mark.parametrize("texto,fundo", PARES_TEXTO)
def test_contraste_aa_dos_pares_de_texto(texto, fundo):
    t = _tokens()
    assert contraste(t[texto], t[fundo]) >= 4.5, (texto, fundo, contraste(t[texto], t[fundo]))
