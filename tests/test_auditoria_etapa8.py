"""Auditoria da etapa 8 (itens 1 a 15, 17 e 18 de "Auditoria: corrigir"): cada item tem teste que falhava antes."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emporio.web.app import COOKIE, criar_app

WEB = Path(__file__).resolve().parents[1] / "src" / "emporio" / "web"
PRODUTO = "81"  # Yamaha C40 Nylon Natural, R$ 599,90, sem promoção


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    with TestClient(criar_app()) as c:
        yield c


def novo(app) -> TestClient:
    """Outro navegador contra o mesmo app (mesmo IP, outra sessão)."""
    return TestClient(app)


def texto(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def final_do_telefone(sql, pedido: int) -> str:
    t = sql.execute("SELECT c.telefone FROM pedidos p JOIN clientes c ON c.id = p.cliente_id WHERE p.id = ?",
                    (pedido,)).fetchone()[0]
    return re.sub(r"\D", "", t)[-4:]


# ---- 1. cookie só em GET e conferência de Origin --------------------------------------------------------------

def test_post_de_outra_origem_sem_cookie_nao_emite_cookie(cliente):
    r = cliente.post("/carrinho/adicionar", data={"produto_id": PRODUTO, "quantidade": "1"},
                     headers={"Origin": "http://atacante.test"}, follow_redirects=False)
    assert r.status_code == 403 and "set-cookie" not in r.headers


def test_post_de_outra_origem_com_cookie_forjado_nao_emite_cookie(cliente):
    cliente.cookies.set(COOKIE, "forjado")
    r = cliente.post("/fale-conosco", data={"site": "x"}, headers={"Origin": "null"}, follow_redirects=False)
    assert r.status_code == 403 and "set-cookie" not in r.headers


def test_post_de_outro_site_nao_troca_a_sessao_do_visitante(cliente):
    cliente.get("/")
    antes = cliente.cookies.get(COOKIE)
    cliente.post("/fale-conosco", data={"site": "x"}, headers={"Origin": "http://atacante.test"})
    assert cliente.cookies.get(COOKIE) == antes


def test_get_sem_cookie_continua_emitindo_cookie(cliente):
    assert COOKIE in cliente.get("/").headers.get("set-cookie", "")


@pytest.mark.parametrize("origem", ["http://atacante.test", "null", "http://testserver.atacante.test"])
def test_post_com_origin_externo_e_recusado_e_nada_muda(cliente, origem):
    cliente.get("/")
    r = cliente.post("/carrinho/adicionar", data={"produto_id": PRODUTO, "quantidade": "1"},
                     headers={"Origin": origem}, follow_redirects=False)
    assert r.status_code == 403
    assert "Seu carrinho está vazio" in cliente.get("/carrinho").text


def test_post_com_origin_proprio_ou_sem_origin_passa(cliente):
    cliente.get("/")
    r = cliente.post("/carrinho/adicionar", data={"produto_id": PRODUTO, "quantidade": "1"},
                     headers={"Origin": "http://testserver"}, follow_redirects=False)
    assert r.status_code == 303
    r = cliente.post("/carrinho/adicionar", data={"produto_id": PRODUTO, "quantidade": "1"}, follow_redirects=False)
    assert r.status_code == 303


# ---- 2 e 4. falhas de rastreio por pedido e por IP, com janela, e bloqueio com mensagem própria -------------------

def test_falhas_do_mesmo_pedido_bloqueiam_ate_com_outra_sessao_e_o_final_certo(cliente, sql):
    for _ in range(5):  # cada tentativa de uma sessão nova: o limite por conversa não pega
        novo(cliente.app).post("/rastreio", data={"pedido": "8", "final_telefone": "0000"})
    r = novo(cliente.app).post("/rastreio", data={"pedido": "8", "final_telefone": final_do_telefone(sql, 8)})
    assert r.status_code == 429 and "Pedido 8" not in r.text


def test_falhas_do_mesmo_ip_em_pedidos_diferentes_bloqueiam(cliente, sql):
    for n in range(1, 11):
        novo(cliente.app).post("/rastreio", data={"pedido": str(n), "final_telefone": "0000"})
    r = novo(cliente.app).post("/rastreio", data={"pedido": "8", "final_telefone": final_do_telefone(sql, 8)})
    assert r.status_code == 429


def test_bloqueio_libera_depois_da_janela_mesmo_na_mesma_sessao(cliente, sql):
    agora = [1_000_000.0]
    cliente.app.state.limite_rastreio.relogio = lambda: agora[0]
    for _ in range(3):
        cliente.post("/rastreio", data={"pedido": "8", "final_telefone": "0000"})
    assert cliente.post("/rastreio", data={"pedido": "8", "final_telefone": "0000"}).status_code in (403, 429)
    agora[0] += 16 * 60
    r = cliente.post("/rastreio", data={"pedido": "8", "final_telefone": final_do_telefone(sql, 8)})
    assert r.status_code == 200 and "Pedido 8" in r.text


def test_mensagem_de_bloqueio_diz_quando_libera_oferece_atendimento_e_nao_revela_o_pedido(cliente, sql):
    def bloquear(pedido: str) -> str:
        app = criar_app()
        for _ in range(5):
            novo(app).post("/rastreio", data={"pedido": pedido, "final_telefone": "0000"})
        r = novo(app).post("/rastreio", data={"pedido": pedido, "final_telefone": "0000"})
        assert r.status_code == 429
        t = texto(r.text)
        assert "liberada de novo às" in t and 'href="/fale-conosco"' in r.text
        return re.search(r"Por segurança.*?Fale conosco", t).group(0)
    assert bloquear("8") == bloquear("99999")  # pedido que existe e que não existe: mesma mensagem


# ---- 3. páginas de erro em português ------------------------------------------------------------------------------

@pytest.mark.parametrize("pedir,status,titulo", [
    (lambda c: c.get("/nao-existe"), 404, "Página não encontrada"),
    (lambda c: c.post("/catalogo"), 405, "Método não permitido"),
])
def test_paginas_de_erro_404_e_405_em_portugues(cliente, pedir, status, titulo):
    r = pedir(cliente)
    assert r.status_code == status and titulo in r.text and 'lang="pt-BR"' in r.text
    assert "Not Found" not in r.text and "Method Not Allowed" not in r.text and "\"detail\"" not in r.text


def test_pagina_de_erro_422_em_portugues(cliente):
    cliente.app.add_api_route("/_t422", lambda x: {"x": x}, methods=["GET"])  # x sem tipo vira query obrigatória
    r = cliente.get("/_t422")
    assert r.status_code == 422 and "Não entendemos esse pedido" in r.text and "field required" not in r.text
    assert "Field required" not in r.text and "\"loc\"" not in r.text


def test_pagina_de_erro_500_em_portugues_sem_rastro(monkeypatch):
    from emporio.web import app as app_mod

    def quebra():
        raise RuntimeError("segredo interno")
    monkeypatch.setattr(app_mod.home, "destaques", quebra)
    with TestClient(criar_app(), raise_server_exceptions=False) as c:
        r = c.get("/")
    assert r.status_code == 500 and "Algo deu errado" in r.text
    assert "segredo interno" not in r.text and "Internal Server Error" not in r.text and "Traceback" not in r.text


# ---- 5. Fale Conosco: gravar, redirecionar e não duplicar ao recarregar -------------------------------------------

def _mensagens(sql) -> int:
    try:
        return sql.execute("SELECT COUNT(*) FROM mensagens_contato").fetchone()[0]
    except Exception:  # noqa: BLE001 - tabela ainda não existe
        return 0


def test_fale_conosco_redireciona_apos_gravar_e_recarregar_nao_duplica(cliente, sql):
    cliente.get("/fale-conosco")
    dados = {"assunto": "Dúvida", "mensagem": "Quero saber sobre a garantia.", "contato_retorno": "a@b.com"}
    r = cliente.post("/fale-conosco", data=dados, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/fale-conosco?enviado=")
    destino = r.headers["location"]
    for _ in range(3):  # recarregar a página de confirmação
        g = cliente.get(destino)
        assert g.status_code == 200 and "Mensagem registrada" in g.text and "FC-" in g.text
    assert _mensagens(sql) == 1


def test_confirmacao_do_fale_conosco_nao_aceita_protocolo_forjado(cliente):
    g = cliente.get("/fale-conosco?enviado=FC-0001")
    assert "Mensagem registrada" not in g.text and "FC-0001" not in g.text


def test_fale_conosco_com_erro_continua_na_pagina_sem_redirecionar(cliente, sql):
    r = cliente.post("/fale-conosco", data={"assunto": "", "mensagem": "curta", "contato_retorno": "x"},
                     follow_redirects=False)
    assert r.status_code == 422 and _mensagens(sql) == 0


# ---- 6. entradas numéricas: só [0-9], com limite, sem erro 500 ----------------------------------------------------

RUINS = ["9" * 30, "²", "١٢٣", "9" * 5000, "-1", "1e3", "0x10"]


@pytest.mark.parametrize("v", RUINS)
def test_carrinho_recusa_numero_ruim_sem_500(cliente, v):
    cliente.get("/")
    for rota, dados in (("/carrinho/adicionar", {"produto_id": v, "quantidade": "1"}),
                        ("/carrinho/adicionar", {"produto_id": PRODUTO, "quantidade": v}),
                        ("/carrinho/alterar", {"produto_id": v, "quantidade": "1"}),
                        ("/carrinho/alterar", {"produto_id": PRODUTO, "quantidade": v}),
                        ("/carrinho/remover", {"produto_id": v})):
        r = cliente.post(rota, data=dados, follow_redirects=False)
        assert r.status_code == 422, (rota, dados.keys(), r.status_code)
    assert "Seu carrinho está vazio" in cliente.get("/carrinho").text


@pytest.mark.parametrize("v", RUINS)
def test_rotas_com_numero_na_url_nao_dao_500(cliente, v):
    cliente.get("/")
    assert cliente.get(f"/produto/{v}").status_code in (404, 422)
    assert cliente.get("/catalogo", params={"pagina": v}).status_code == 422
    assert cliente.get(f"/pedido/PED-{v}").status_code == 404
    r = cliente.post("/rastreio", data={"pedido": v, "final_telefone": "1234"})
    assert r.status_code == 422 and "número do pedido" in r.text
    for campo in ("preco_min", "preco_max"):
        assert cliente.get("/catalogo", params={campo: v}).status_code in (200, 422)
    assert cliente.get("/checkout", params={"cep": v, "parcelas": v, "forma": v}).status_code == 200


def test_numero_valido_continua_funcionando(cliente):
    cliente.get("/")
    assert cliente.get(f"/produto/{PRODUTO}").status_code == 200
    assert cliente.get("/catalogo", params={"pagina": "2"}).status_code == 200
    r = cliente.post("/carrinho/adicionar", data={"produto_id": PRODUTO, "quantidade": "2"}, follow_redirects=False)
    assert r.status_code == 303


# ---- 7. filtro de preço ---------------------------------------------------------------------------------------------

def _total(html: str) -> str:
    return re.search(r'data-total="(\d+)"', html).group(1)


@pytest.mark.parametrize("digitado,equivalente", [("2.000", "2000"), ("1.000,00", "1000"), ("R$ 2.000,50", "2000.50"),
                                                  ("2000,5", "2000.50"), ("1.500", "1500")])
def test_filtro_de_preco_entende_milhar_e_virgula(cliente, digitado, equivalente):
    a = cliente.get("/catalogo", params={"preco_min": digitado})
    b = cliente.get("/catalogo", params={"preco_min": equivalente})
    assert a.status_code == 200 and "Use apenas números" not in a.text
    assert _total(a.text) == _total(b.text)


def test_filtro_de_preco_com_milhar_nao_vira_centavos(cliente):
    sem = _total(cliente.get("/catalogo").text)
    assert _total(cliente.get("/catalogo", params={"preco_min": "2.000"}).text) != sem


def test_filtro_de_preco_negativo_tem_texto_proprio(cliente):
    r = cliente.get("/catalogo", params={"preco_min": "-5"})
    assert "O preço não pode ser negativo." in r.text and "Use apenas números" not in r.text


def test_filtro_de_preco_com_letras_segue_com_o_texto_de_numeros(cliente):
    assert "Use apenas números nos campos de preço." in cliente.get("/catalogo", params={"preco_max": "abc"}).text


# ---- 8. políticas: tabelas reais e nada de instrução interna --------------------------------------------------------

def test_politicas_mostram_tabelas_reais(cliente):
    h = cliente.get("/politicas").text
    assert h.count("<table") >= 2 and "Forma | Condições" not in h and " | " not in texto(h).split("Pagamento", 1)[-1][:400]
    pag = re.search(r'<section class="politica" id="pagamento".*?</section>', h, re.S).group(0)
    assert "<th" in pag and "<td>PIX" in pag and "Compensação em até 3 dias úteis" in pag
    ent = re.search(r'<section class="politica" id="entrega".*?</section>', h, re.S).group(0)
    assert "<td>SEDEX (Correios)" in ent and "<td>Jadlog (.package)" in ent


def test_politicas_listas_com_marcadores_viram_listas(cliente):
    h = cliente.get("/politicas").text
    assert "<ul" in re.search(r'<section class="politica" id="trocas".*?</section>', h, re.S).group(0)
    assert "•" not in h


def test_politicas_nao_publicam_instrucao_interna_da_equipe(cliente):
    t = texto(cliente.get("/politicas").text)
    assert "devem sempre ser apresentados" not in t and "Comunicação:" not in t
    assert "Cumulatividade" in t and "rain check" in t  # o que é regra para o cliente continua


def test_texto_do_manual_segue_intacto():
    from emporio.ferramentas.politica import consultar_politica
    secoes = {s["id"]: s["texto"] for s in consultar_politica(temas=["promocoes"]).dados["secoes"]}
    assert "devem sempre ser apresentados junto ao preço original" in secoes["6.2"]


# ---- 9. "Imagem ilustrativa" ------------------------------------------------------------------------------------------

def test_produto_com_foto_avisa_imagem_ilustrativa(cliente):
    h = cliente.get(f"/produto/{PRODUTO}").text
    assert "<img" in re.search(r'class="produto-arte".*?</div>', h, re.S).group(0)
    assert "Imagem ilustrativa" in re.search(r'class="produto-arte".*?</figure>|class="produto-arte".*?</div>\s*<div', h, re.S).group(0)


# ---- 10 e 15. perguntas frequentes ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("caminho", ["/perguntas-frequentes", "/"])
def test_faq_sem_ponto_em_aberto(cliente, caminho):
    assert "ponto em aberto" not in cliente.get(caminho).text
    assert "ponto em aberto" not in cliente.get("/perguntas-frequentes").text


def test_faq_orienta_o_pedido_feito_no_site(cliente):
    t = texto(cliente.get("/perguntas-frequentes").text)
    resposta = re.search(r"Como acompanho meu pedido\? (.*?) (Trocas e garantia|Qual o|Como faço)", t).group(1)
    assert "PED-" in resposta and "no site" in resposta and "sem o telefone" in resposta


# ---- 11. filtro só com categorias que têm produto --------------------------------------------------------------------------

def test_filtro_do_catalogo_lista_so_categorias_com_produto(cliente):
    h = cliente.get("/catalogo").text
    opcoes = re.findall(r'<option value="([^"]*)"', re.search(r'<select name="categoria">.*?</select>', h, re.S).group(0))
    assert "Violões" in opcoes and "Instrumentos de Sopro (Madeiras)" not in opcoes and "Cordas Orquestrais" not in opcoes
    for nome in opcoes:
        if nome:
            assert cliente.get("/catalogo", params={"categoria": nome}).text.count('class="card"') > 0, nome


# ---- 12. busca sem resultado ---------------------------------------------------------------------------------------------------

def test_busca_sem_resultado_repete_o_termo_e_oferece_caminhos(cliente):
    h = cliente.get("/catalogo", params={"termo": "zzzzqq"}).text
    assert "Nenhum produto encontrado para “zzzzqq”" in h
    assert 'href="/catalogo"' in h and "Ver todos os instrumentos" in h and 'href="/fale-conosco"' in h
    assert "categoria=" in re.search(r'class="busca-vazia".*?</div>', h, re.S).group(0)


def test_busca_sem_resultado_escapa_o_termo(cliente):
    h = cliente.get("/catalogo", params={"termo": "<b>zz</b>qq"}).text
    assert "<b>zz</b>" not in h and "&lt;b&gt;" in h


@pytest.mark.parametrize("termo", ["%%%", "___", "!!!", "'", "..."])
def test_busca_so_com_simbolos_pede_letra_em_vez_de_listar_tudo(cliente, termo):
    r = cliente.get("/catalogo", params={"termo": termo})
    assert r.status_code == 200 and "Digite pelo menos uma letra ou um número" in r.text and 'class="card"' not in r.text


# ---- 13. carrinho com subtotal por item e total de produtos ---------------------------------------------------------------------

def test_carrinho_mostra_subtotal_por_item_e_total_dos_produtos(cliente, sql):
    promo = sql.execute("SELECT id FROM produtos WHERE nome LIKE 'Kalani KAL-700T%'").fetchone()[0]
    cliente.get("/")
    cliente.post("/carrinho/adicionar", data={"produto_id": PRODUTO, "quantidade": "2"})
    cliente.post("/carrinho/adicionar", data={"produto_id": str(promo), "quantidade": "1"})
    h = cliente.get("/carrinho").text
    t = texto(h)
    assert "Subtotal: R$ 1.199,80" in t and "Subtotal: R$ 323,10" in t
    assert "Total dos produtos: R$ 1.522,90" in t


# ---- 14. abertura da home -----------------------------------------------------------------------------------------------------------

def test_abertura_da_home_sem_pagamento_a_vista(cliente):
    h = cliente.get("/").text
    assert "condição de pagamento à vista" not in h and "entrega à vista" not in h


# ---- 17. português ---------------------------------------------------------------------------------------------------------------------

def test_rotulos_de_compra_em_portugues(cliente):
    cliente.get("/")
    p = cliente.get(f"/produto/{PRODUTO}").text
    assert "Adicionar ao carrinho" in p and "Conversar com a Lia" in p and "Quero comprar" not in p.replace("data-mensagem=\"Quero comprar", "")
    cliente.post("/carrinho/adicionar", data={"produto_id": PRODUTO, "quantidade": "1"})
    c = cliente.get("/carrinho").text
    assert "Finalizar pedido" in c and "checkout" not in texto(c).lower()


def test_horario_em_forma_unica_e_com_um_so_rotulo(cliente):
    for caminho in ("/", "/fale-conosco", "/offline"):
        h = cliente.get(caminho).text
        assert "Horário de funcionamento" not in h, caminho
        assert "09:00" not in texto(h).replace("abre amanhã às 09:00", "").replace("abre hoje às 09:00", ""), caminho
    assert "Seg. a sex., das 9h às 18h" in cliente.get("/").text
    assert "Sáb., das 9h às 13h" in cliente.get("/").text
    assert "Horário de atendimento" in cliente.get("/").text


def test_site_fala_em_nos_e_nunca_em_eu():
    achados = []
    for p in list(WEB.glob("*.py")) + list((WEB / "templates").glob("*.html")):
        if p.name.startswith("gerar_"):
            continue
        for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"Não conseguib|Não achei|Quer que eu", linha):
                achados.append(f"{p.name}:{n}")
    assert achados == []


@pytest.mark.parametrize("caminho", ["/", "/perguntas-frequentes", "/fale-conosco", "/offline", "/carrinho", "/rastreio",
                                     "/catalogo", "/creditos", "/checkout"])
def test_texto_do_site_diz_do_emporio_e_nao_da_emporio(cliente, caminho):
    assert "da Empório" not in cliente.get(caminho).text


def test_regencia_e_anglicismo_corrigidos_no_texto_do_site(cliente):
    t = texto(cliente.get("/perguntas-frequentes").text) + texto(cliente.get("/politicas").text)
    assert "o checkout" not in t and "no checkout" not in t


# ---- 18. "Para começar" --------------------------------------------------------------------------------------------------------------------

def test_secao_da_grade_chama_menores_precos_por_categoria(cliente):
    h = cliente.get("/").text
    assert "Menores preços por categoria" in h and "Para começar" not in h
