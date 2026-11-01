"""Etapa 6e: recálculo do checkout, localizador de CEP, faixa Fale conosco, rodapé, página de contato e cache do PWA."""
from __future__ import annotations

import os
import re
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emporio.politicas.manual import fato
from emporio.web import app as app_mod
from emporio.web import cep as cep_mod
from emporio.web.app import criar_app

TAKAMINE = 95  # sem promoção
WEB = Path(__file__).resolve().parents[1] / "src" / "emporio" / "web"
PAGINAS_COM_RODAPE = ("/", "/catalogo", "/produto/90", "/politicas", "/perguntas-frequentes", "/privacidade", "/rastreio",
                      "/carrinho", "/creditos")


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


@pytest.fixture(autouse=True)
def limpar_memoria_cep():
    cep_mod._memoria.clear()
    yield
    cep_mod._memoria.clear()


def externo(monkeypatch, resposta=None, erro=None):
    """Liga a consulta externa com um dublê: nenhum teste acessa a rede."""
    monkeypatch.setenv("EMPORIO_CEP_EXTERNO", "1")
    chamadas = []

    def falso(digitos):
        chamadas.append(digitos)
        if erro is not None:
            raise erro
        return resposta

    monkeypatch.setattr(cep_mod, "_consultar_externo", falso)
    return chamadas


def comprar(cliente, produto=TAKAMINE):
    cliente.post("/carrinho/adicionar", data={"produto_id": produto, "quantidade": 1})


def checkout(cliente, **params):
    return cliente.get("/checkout", params=params).text


def botao_registrar(html):
    return re.search(r"<button[^>]*>\s*Registrar pedido", html).group(0)


def pedidos(sql):
    return sql.execute("SELECT COUNT(*) FROM pedidos_demo").fetchone()[0]


# ---- recálculo por HTMX --------------------------------------------------------------------------

def test_fragmento_htmx_traz_total_visto_resumo_e_botao(cliente):
    comprar(cliente)
    r = cliente.get("/checkout", params={"forma": "pix", "cep": "79002-000"}, headers={"HX-Request": "true"})
    assert r.status_code == 200 and "<html" not in r.text
    assert 'name="total_visto"' in r.text and 'id="checkout-dinamico"' in r.text and "Registrar pedido" in r.text


def test_parcelas_so_aparecem_no_credito(cliente):
    comprar(cliente)
    assert 'name="parcelas"' not in checkout(cliente, forma="pix", cep="79002-000")
    assert 'name="parcelas"' not in checkout(cliente, forma="debito", cep="79002-000")
    assert 'name="parcelas"' in checkout(cliente, forma="credito", parcelas="3", cep="79002-000")
    fragmento = cliente.get("/checkout", params={"forma": "credito", "cep": "79002-000"}, headers={"HX-Request": "true"}).text
    assert 'id="campo-parcelas"' in fragmento and 'name="parcelas"' in fragmento


def test_botao_de_atualizar_fica_dentro_de_noscript(cliente):
    comprar(cliente)
    html = checkout(cliente)
    assert re.search(r"<noscript>\s*<button[^>]*>Atualizar valores</button>\s*</noscript>", html)
    assert 'hx-sync="this:replace"' in html  # a resposta mais recente vence


# ---- CEP: faixa, bordas e CEP da loja (consulta externa desligada) ----------------------------------

@pytest.mark.parametrize("cep,cotacao", [("79000-000", False), ("79129-999", False), ("79130-000", True)])
def test_bordas_da_faixa_de_campo_grande(cliente, cep, cotacao):
    comprar(cliente)
    html = checkout(cliente, forma="debito", cep=cep)
    assert ("Frete calculado pela equipe" in html) is cotacao


def test_cep_da_loja_no_manual_e_campo_grande_sem_consulta(cliente, monkeypatch):
    chamadas = externo(monkeypatch, resposta={"erro": "true"})
    comprar(cliente)
    cep_loja = fato("empresa.endereco").valor["cep"]
    html = checkout(cliente, forma="debito", cep=cep_loja)
    assert "Frete calculado pela equipe" not in html and "disabled" not in botao_registrar(html) and chamadas == []


def test_cep_com_ou_sem_hifen_vale_igual(cliente):
    comprar(cliente)
    assert "Frete calculado pela equipe" not in checkout(cliente, forma="debito", cep="79002000")


@pytest.mark.parametrize("cep", ["", "123", "7900200", "790020000", "abcdefgh", "79002-00x"])
def test_cep_invalido_impede_finalizar(cliente, sql, cep):
    comprar(cliente)
    assert "disabled" in botao_registrar(checkout(cliente, forma="debito", cep=cep))
    r = cliente.post("/checkout", data={"forma": "debito", "parcelas": "1", "cep": cep, "total_visto": "0"})
    assert r.status_code in (409, 422) and pedidos(sql) == 0


# ---- CEP: consulta externa com dublê -------------------------------------------------------------------

RECIFE = {"cep": "50030-230", "logradouro": "Rua da Aurora", "bairro": "Boa Vista", "localidade": "Recife", "uf": "PE"}


def test_recife_vira_cotacao_mostra_endereco_e_grava_so_a_cidade(cliente, sql, monkeypatch):
    externo(monkeypatch, resposta=RECIFE)
    comprar(cliente)
    html = checkout(cliente, forma="debito", cep="50030-230")
    assert "Frete calculado pela equipe" in html
    assert "Rua da Aurora, Boa Vista, Recife/PE" in html  # endereço localizado na tela
    total = re.search(r'name="total_visto" value="(\d+)"', html).group(1)
    r = cliente.post("/checkout", data={"forma": "debito", "parcelas": "1", "cep": "50030-230", "total_visto": total})
    assert r.status_code == 303
    linha = dict(sql.execute("SELECT * FROM pedidos_demo").fetchone())
    assert linha["cidade"] == "Recife/PE" and "50030" not in str(list(linha.values()))
    assert not any("cep" in c["name"] for c in sql.execute("PRAGMA table_info(pedidos_demo)").fetchall())


def test_campo_grande_de_outro_estado_nao_recebe_frete_da_cidade_base(cliente, monkeypatch):
    externo(monkeypatch, resposta={"logradouro": "Rua A", "bairro": "Centro", "localidade": "Campo Grande", "uf": "RN"})
    comprar(cliente)
    html = checkout(cliente, forma="debito", cep="59680-000")
    assert "Frete calculado pela equipe" in html and "Campo Grande/RN" in html


def test_cidade_base_com_uf_da_loja_usa_a_regra_da_cidade_base(cliente, monkeypatch):
    externo(monkeypatch, resposta={"logradouro": "Rua B", "bairro": "Centro", "localidade": "Campo Grande", "uf": "MS"})
    comprar(cliente)
    assert "Frete calculado pela equipe" not in checkout(cliente, forma="debito", cep="79600-000")


def test_cep_inexistente_bloqueia(cliente, sql, monkeypatch):
    externo(monkeypatch, resposta={"erro": "true"})
    comprar(cliente)
    html = checkout(cliente, forma="debito", cep="99999-999")
    assert "CEP não encontrado" in html and "disabled" in botao_registrar(html)
    r = cliente.post("/checkout", data={"forma": "debito", "parcelas": "1", "cep": "99999-999", "total_visto": "0"})
    assert r.status_code in (409, 422) and pedidos(sql) == 0


@pytest.mark.parametrize("falha", [TimeoutError("tempo esgotado"), urllib.error.URLError("sem rede"), ValueError("JSON inválido")])
def test_servico_fora_do_ar_nao_bloqueia(cliente, monkeypatch, falha):
    externo(monkeypatch, erro=falha)
    comprar(cliente)
    fora = checkout(cliente, forma="debito", cep="50030-230")
    assert "Não localizamos o endereço agora" in fora and "Frete calculado pela equipe" in fora
    assert "disabled" not in botao_registrar(fora)
    dentro = checkout(cliente, forma="debito", cep="79002-000")  # contingência pela faixa
    assert "Frete calculado pela equipe" not in dentro and "disabled" not in botao_registrar(dentro)


def test_resposta_json_fora_do_formato_nao_bloqueia(cliente, monkeypatch):
    externo(monkeypatch, resposta=["nao", "e", "dict"])
    comprar(cliente)
    html = checkout(cliente, forma="debito", cep="50030-230")
    assert "Não localizamos o endereço agora" in html and "disabled" not in botao_registrar(html)


def test_consulta_vem_da_memoria_na_segunda_vez(monkeypatch):
    chamadas = externo(monkeypatch, resposta=RECIFE)
    assert cep_mod.localizar("50030-230").cidade == "Recife" and cep_mod.localizar("50030230").uf == "PE"
    assert chamadas == ["50030230"]


def test_cep_externo_desligado_nao_consulta(monkeypatch):
    chamadas = externo(monkeypatch, resposta=RECIFE)
    monkeypatch.setenv("EMPORIO_CEP_EXTERNO", "0")
    assert cep_mod.localizar("50030-230").estado == "indisponivel" and chamadas == []


def test_link_nao_sei_meu_cep_vai_aos_correios_em_nova_aba(cliente):
    comprar(cliente)
    m = re.search(r'<a href="([^"]+)"([^>]*)>Não sei meu CEP</a>', checkout(cliente))
    assert m and m.group(1) == "https://buscacepinter.correios.com.br/app/endereco/index.php"
    assert 'target="_blank"' in m.group(2) and "noopener" in m.group(2)


# ---- cache do PWA ---------------------------------------------------------------------------------------

def test_versao_do_cache_muda_quando_o_conteudo_muda(tmp_path, monkeypatch):
    (tmp_path / "static").mkdir()
    (tmp_path / "sw.js").write_text("// sw", encoding="utf-8")
    css = tmp_path / "static" / "site.css"
    css.write_text("a{}", encoding="utf-8")
    monkeypatch.setattr(app_mod, "AQUI", tmp_path)
    app_mod._HASH_SW.clear()
    v1 = app_mod.versao_sw()
    assert v1 == app_mod.versao_sw() and v1 != "2"
    css.write_text("b{}", encoding="utf-8")  # mesmo tamanho, outro conteúdo
    os.utime(css, ns=(css.stat().st_atime_ns, css.stat().st_mtime_ns + 5_000_000))
    assert app_mod.versao_sw() != v1
    app_mod._HASH_SW.clear()


def test_sw_servido_usa_o_hash_e_lista_o_script_do_checkout(cliente):
    corpo = cliente.get("/sw.js").text
    assert app_mod.versao_sw() in corpo and "/static/checkout.js" in corpo


# ---- faixa, rodapé, endereço e página de contato ------------------------------------------------------------

def _rodape(html):
    return html[html.index('<footer class="rodape">'):html.index("</footer>")]


@pytest.mark.parametrize("caminho", PAGINAS_COM_RODAPE)
def test_faixa_fale_conosco_tem_3_blocos_nas_paginas_com_rodape(cliente, caminho):
    html = cliente.get(caminho).text
    assert html.count('class="bloco-3"') == 3 and html.index('class="contorno faixa-contato"') < html.index('<footer class="rodape">')
    assert 'href="/fale-conosco">Fale conosco</a>' in html and 'href="/rastreio">Rastrear pedido</a>' in html
    assert "Já fez seu pedido e quer saber onde ele está?" in html


def test_faixa_ausente_em_fale_conosco(cliente):
    assert "faixa-contato" not in cliente.get("/fale-conosco").text


@pytest.mark.parametrize("caminho", ["/", "/catalogo", "/perguntas-frequentes", "/rastreio", "/carrinho", "/creditos", "/privacidade"])
def test_telefone_aparece_uma_unica_vez_por_pagina(cliente, caminho):
    assert cliente.get(caminho).text.count(str(fato("contato.telefone_capa").valor)) == 1


def test_telefone_uma_vez_em_fale_conosco(cliente):
    assert cliente.get("/fale-conosco").text.count(str(fato("contato.telefone_capa").valor)) == 1


@pytest.mark.parametrize("caminho", PAGINAS_COM_RODAPE + ("/fale-conosco",))
def test_rodape_sem_telefone_email_whatsapp_nem_endereco(cliente, caminho):
    rodape = _rodape(cliente.get(caminho).text)
    for chave in ("contato.telefone_capa", "contato.email_capa", "contato.whatsapp_secao_7",
                  "contato.telefone_whatsapp_dados_empresa"):
        assert str(fato(chave).valor) not in rodape
    assert fato("empresa.endereco").valor["logradouro"] not in rodape
    assert "Todos os canais" not in rodape and "Atendimento" not in rodape
    assert 'href="/fale-conosco">Fale conosco</a>' in rodape  # na coluna Informações


@pytest.mark.parametrize("caminho", ["/", "/catalogo", "/produto/90", "/perguntas-frequentes", "/privacidade", "/rastreio",
                                     "/carrinho", "/creditos"])
def test_endereco_ausente_fora_de_fale_conosco(cliente, caminho):
    assert fato("empresa.endereco").valor["logradouro"] not in cliente.get(caminho).text


def test_endereco_aparece_uma_vez_em_fale_conosco(cliente):
    html = cliente.get("/fale-conosco").text
    assert html.count(fato("empresa.endereco").valor["logradouro"]) == 1 and "Onde estamos e horários" in html


def test_endereco_continua_na_pagina_offline(cliente):
    assert fato("empresa.endereco").valor["logradouro"] in cliente.get("/offline").text


def test_home_tem_so_a_faixa_e_nao_a_secao_antiga(cliente):
    html = cliente.get("/").text
    assert 'id="visite"' not in html and "Visite a loja" not in html and "Falar com a loja" not in html
    assert html.count('aria-label="Fale conosco"') == 1


def test_cabecalho_sem_fale_conosco(cliente):
    html = cliente.get("/").text
    assert "fale-conosco" not in html[html.index('<header class="topo">'):html.index("</header>")]


def test_pagina_fale_conosco_tem_3_canais_e_duas_colunas(cliente):
    html = cliente.get("/fale-conosco").text
    assert html.count('class="bloco-3"') == 3
    for rotulo in ("WhatsApp", "Telefone", "E-mail"):
        assert f">{rotulo}</h2>" in html
    for velho in ("Conversar", "Ligar", "Escrever", "Deixar uma mensagem"):
        assert velho not in html
    assert "Envie uma mensagem" in html and 'class="fc-colunas"' in html and 'href="/rastreio">Rastrear pedido' in html


def test_envio_do_formulario_mostra_protocolo(cliente):
    r = cliente.post("/fale-conosco", data={"assunto": "Dúvida", "mensagem": "Quero saber mais sobre o prazo.",
                                            "contato_retorno": "cliente@example.com", "site": ""})
    assert r.status_code == 200 and 'class="protocolo"' in r.text


def test_privacidade_diz_do_viacep_e_nao_carrega_script_de_terceiros(cliente):
    texto = cliente.get("/privacidade").text
    assert "ViaCEP" in texto and "endereço completo" in texto and '<script src="https://' not in texto


def test_aviso_do_checkout_fala_de_cep(cliente):
    comprar(cliente)
    html = checkout(cliente)
    assert "Não informe dados de cartão nem CPF" in html and "O CEP serve só para" in html
    assert "Cidade da entrega" not in html and "CEP de entrega" in html


def test_codigo_do_chat_nao_envia_ao_clicar_na_sugestao():
    js = (WEB / "static" / "chat.js").read_text(encoding="utf-8")
    assert 'htmx.trigger(form, "submit")' not in js and "function preencher" in js


def test_resumo_do_checkout_sem_frete_pede_o_cep_e_nao_a_cidade(cliente):
    comprar(cliente)
    html = checkout(cliente)
    assert "informe o CEP" in html and "informe a cidade" not in html
