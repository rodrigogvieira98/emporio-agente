"""Incremento 1: compra de demonstração. Valores esperados vêm de calcular_condicoes, nunca de conta feita aqui."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emporio.ferramentas.condicoes import calcular_condicoes
from emporio.ferramentas.pedido_demo import consultar_pedido_demo
from emporio.web.app import criar_app

RAIZ = Path(__file__).resolve().parents[1]
CRAFTER, TAKAMINE, SHELBY, UKULELE_SOPRANO = 90, 95, 89, 117  # promoção ativa, sem promoção, 6x ambíguo, barato
DESCONTINUADO, ESGOTADO = 113, 96
CAMPO_GRANDE = "Campo Grande"


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


def comprar(cliente, produto, quantidade=1):
    return cliente.post("/carrinho/adicionar", data={"produto_id": produto, "quantidade": quantidade})


def final_unit(produto, forma):
    return calcular_condicoes(produto_id=produto, forma=forma).dados["final_centavos"]


def numero_do_pedido(resposta):
    assert resposta.status_code == 303, resposta.text[:300]
    return resposta.headers["location"].rsplit("/", 1)[1]


def contar(sql, tabela):
    return sql.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


def test_promocao_com_pix_nao_soma_desconto(cliente, sql):
    assert comprar(cliente, CRAFTER).status_code == 303
    html = cliente.get("/checkout", params={"forma": "pix", "cidade": CAMPO_GRANDE}).text
    ref = calcular_condicoes(produto_id=CRAFTER, forma="pix").dados
    assert ref["pix_aplicado"] is False and ref["percentual"] == 18
    esperado = ref["final_centavos"]
    assert esperado == 196718  # R$ 1.967,18 do manual: promoção 18%, PIX não soma
    assert "R$ 1.967,18" in html and "promoção -18%" in html
    assert "desconto do PIX" not in html


def test_pix_sem_promocao_aplica_o_desconto_da_ferramenta(cliente):
    comprar(cliente, TAKAMINE)
    html = cliente.get("/checkout", params={"forma": "pix", "cidade": CAMPO_GRANDE}).text
    assert "R$ 2.089,05" in html and "desconto do PIX" in html


def test_total_e_a_soma_das_ferramentas(cliente, sql):
    comprar(cliente, CRAFTER, 2)
    comprar(cliente, TAKAMINE, 1)
    comprar(cliente, UKULELE_SOPRANO, 3)
    esperado_produtos = (2 * final_unit(CRAFTER, "debito") + final_unit(TAKAMINE, "debito")
                         + 3 * final_unit(UKULELE_SOPRANO, "debito"))
    frete = calcular_condicoes(valor=esperado_produtos, forma="debito", cidade=CAMPO_GRANDE)
    assert frete.dados["frete"]["situacao"] == "gratis"
    corpo = {"forma": "debito", "parcelas": "1", "cidade": CAMPO_GRANDE, "total_visto": str(esperado_produtos)}
    numero = numero_do_pedido(cliente.post("/checkout", data=corpo))
    gravado = sql.execute("SELECT * FROM pedidos_demo WHERE numero = ?", (numero,)).fetchone()
    assert gravado["total_centavos"] == esperado_produtos
    itens = sql.execute("SELECT * FROM itens_pedido_demo WHERE pedido_id = ?", (gravado["id"],)).fetchall()
    assert sum(i["subtotal_centavos"] for i in itens) == esperado_produtos
    assert {i["produto_id"]: i["final_unit_centavos"] for i in itens}[CRAFTER] == final_unit(CRAFTER, "debito")


def test_frete_abaixo_do_limite_soma_a_taxa_do_manual(cliente, sql):
    comprar(cliente, UKULELE_SOPRANO)
    base = final_unit(UKULELE_SOPRANO, "debito")
    frete = calcular_condicoes(valor=base, forma="debito", cidade=CAMPO_GRANDE).dados["frete"]
    assert frete["situacao"] == "taxa"
    corpo = {"forma": "debito", "parcelas": "1", "cidade": CAMPO_GRANDE, "total_visto": str(base + frete["taxa_centavos"])}
    numero = numero_do_pedido(cliente.post("/checkout", data=corpo))
    gravado = sql.execute("SELECT * FROM pedidos_demo WHERE numero = ?", (numero,)).fetchone()
    assert gravado["total_centavos"] == base + frete["taxa_centavos"] and gravado["frete_centavos"] == frete["taxa_centavos"]


def test_parcela_com_requer_confirmacao_aparece_marcada_e_nao_finaliza(cliente, sql):
    comprar(cliente, SHELBY)
    ref = calcular_condicoes(produto_id=SHELBY, forma="credito", parcelas=6).dados
    assert ref["permitido"] == "requer_confirmacao"
    params = {"forma": "credito", "parcelas": "6", "cidade": CAMPO_GRANDE}
    html = cliente.get("/checkout", params=params).text
    assert "A confirmar com a equipe" in html and "R$ 91,50" in html
    assert re.search(r'<button[^>]*type="submit"[^>]*disabled', html)
    # forçando o POST sem o botão, o servidor também recusa e nada é gravado
    r = cliente.post("/checkout", data={**params, "total_visto": str(ref["final_centavos"])})
    assert r.status_code == 422 and "A confirmar com a equipe" in r.text
    assert contar(sql, "pedidos_demo") == 0
    # menos parcelas dentro das duas leituras finalizam
    ok = {**params, "parcelas": "3", "total_visto": str(ref["final_centavos"])}
    assert calcular_condicoes(produto_id=SHELBY, forma="credito", parcelas=3).dados["permitido"] == "sim"
    assert cliente.post("/checkout", data=ok).status_code == 303


def test_frete_de_exatamente_o_limite_fica_a_confirmar(cliente, sql, tmp_path, monkeypatch):
    # nenhum item do catálogo soma exatamente o limite do manual; o limite é movido no YAML para o preço de um item
    base = final_unit(UKULELE_SOPRANO, "debito")
    origem = (RAIZ / "src" / "emporio" / "politicas" / "manual_v2_1.yaml").read_text(encoding="utf-8")
    alvo = "chave: frete.gratis_acima_centavos, valor: 50000"
    assert alvo in origem
    copia = tmp_path / "manual_limite.yaml"
    copia.write_text(origem.replace(alvo, f"chave: frete.gratis_acima_centavos, valor: {base}", 1), encoding="utf-8")
    monkeypatch.setenv("EMPORIO_MANUAL", str(copia))
    assert calcular_condicoes(valor=base, forma="debito", cidade=CAMPO_GRANDE).dados["frete"]["situacao"] == "requer_confirmacao"
    comprar(cliente, UKULELE_SOPRANO)
    params = {"forma": "debito", "cidade": CAMPO_GRANDE}
    html = cliente.get("/checkout", params=params).text
    assert "Frete a confirmar com a equipe" in html and "disabled" in html
    r = cliente.post("/checkout", data={**params, "parcelas": "1", "total_visto": str(base)})
    assert r.status_code == 422 and contar(sql, "pedidos_demo") == 0


def test_o_limite_exato_do_manual_na_ferramenta_e_requer_confirmacao():
    frete = calcular_condicoes(valor=50000, forma="debito", cidade=CAMPO_GRANDE).dados["frete"]
    assert frete["situacao"] == "requer_confirmacao" and frete["taxa_centavos"] is None


def test_outra_cidade_mostra_frete_calculado_pela_equipe(cliente):
    comprar(cliente, TAKAMINE)
    html = cliente.get("/checkout", params={"forma": "debito", "cidade": "Dourados"}).text
    assert "Frete calculado pela equipe" in html and "calculado pela equipe" in html


@pytest.mark.parametrize("produto", [DESCONTINUADO, ESGOTADO])
def test_produto_nao_vendavel_e_recusado(cliente, sql, produto):
    r = comprar(cliente, produto)
    assert r.status_code == 422 and "não está disponível" in r.text
    assert contar(sql, "carrinhos") == 0


def test_pagina_do_produto_descontinuado_nao_tem_botao_de_carrinho(cliente):
    html = cliente.get(f"/produto/{DESCONTINUADO}").text
    assert "/carrinho/adicionar" not in html and "Quero comprar" not in html


def test_pagina_do_produto_vendavel_adiciona_ao_carrinho_e_mantem_a_lia(cliente):
    html = cliente.get(f"/produto/{TAKAMINE}").text
    assert 'action="/carrinho/adicionar"' in html and "Quero comprar com a Lia" in html


def test_quantidade_de_1_a_3(cliente, sql):
    assert comprar(cliente, TAKAMINE, 0).status_code == 422
    assert comprar(cliente, TAKAMINE, 4).status_code == 422
    assert contar(sql, "carrinhos") == 0
    assert comprar(cliente, TAKAMINE, 2).status_code == 303
    assert comprar(cliente, TAKAMINE, 2).status_code == 422  # 2 + 2 passa de 3
    assert sql.execute("SELECT quantidade FROM carrinhos").fetchone()[0] == 2


def test_estoque_nao_e_baixado(cliente, sql):
    antes = sql.execute("SELECT estoque FROM produtos WHERE id = ?", (TAKAMINE,)).fetchone()[0]
    comprar(cliente, TAKAMINE, 3)
    corpo = {"forma": "debito", "parcelas": "1", "cidade": CAMPO_GRANDE, "total_visto": str(3 * final_unit(TAKAMINE, "debito"))}
    cliente.post("/checkout", data=corpo)
    assert sql.execute("SELECT estoque FROM produtos WHERE id = ?", (TAKAMINE,)).fetchone()[0] == antes


def test_avisos_de_demonstracao_no_carrinho_no_checkout_e_no_pedido(cliente):
    comprar(cliente, UKULELE_SOPRANO)
    assert "não gera cobrança nem entrega" in cliente.get("/checkout").text
    base = final_unit(UKULELE_SOPRANO, "debito")
    taxa = calcular_condicoes(valor=base, forma="debito", cidade=CAMPO_GRANDE).dados["frete"]["taxa_centavos"]
    corpo = {"forma": "debito", "parcelas": "1", "cidade": CAMPO_GRANDE, "total_visto": str(base + taxa)}
    numero = numero_do_pedido(cliente.post("/checkout", data=corpo))
    pedido = cliente.get(f"/pedido/{numero}")
    assert pedido.status_code == 200 and "Nenhum valor foi cobrado" in pedido.text and numero in pedido.text


def test_sem_campos_de_pagamento_real(cliente):
    comprar(cliente, UKULELE_SOPRANO)
    html = (cliente.get("/checkout").text + cliente.get("/carrinho").text).lower()
    for proibido in ("cpf", "numero do cartao", "número do cartão", "cvv", "cep", 'name="cartao"', "endereço completo"):
        assert f'name="{proibido}"' not in html
    nomes = set(re.findall(r'<(?:input|select)[^>]*name="([^"]+)"', cliente.get("/checkout").text))
    assert nomes <= {"termo", "total_visto", "forma", "parcelas", "cidade", "mensagem"}


def test_rastreio_reconhece_demo_e_nao_mistura_com_os_dados(cliente, sql):
    comprar(cliente, UKULELE_SOPRANO)
    base = final_unit(UKULELE_SOPRANO, "debito")
    taxa = calcular_condicoes(valor=base, forma="debito", cidade=CAMPO_GRANDE).dados["frete"]["taxa_centavos"]
    numero = numero_do_pedido(cliente.post(
        "/checkout", data={"forma": "debito", "parcelas": "1", "cidade": CAMPO_GRANDE, "total_visto": str(base + taxa)}))
    assert numero == "PED-0001"
    r = cliente.post("/rastreio", data={"pedido": numero, "final_telefone": ""})
    assert r.status_code == 200 and numero in r.text and "Nenhum valor foi cobrado" in r.text
    assert "Código de rastreio" not in r.text
    # outro navegador não vê o pedido; é o mesmo negado de um número inexistente
    with TestClient(criar_app(), follow_redirects=False) as outro:
        negado = outro.post("/rastreio", data={"pedido": numero, "final_telefone": ""})
        inexistente = outro.post("/rastreio", data={"pedido": "PED-0099", "final_telefone": ""})
    assert negado.status_code == inexistente.status_code == 403


def test_pedido_numerico_dos_dados_continua_igual(cliente):
    r = cliente.post("/rastreio", data={"pedido": "8", "final_telefone": "7821"})
    assert r.status_code == 200 and "BRJL5544332BR" in r.text


def test_nada_e_gravado_em_pedidos(cliente, sql):
    antes = (contar(sql, "pedidos"), contar(sql, "itens_pedido"))
    comprar(cliente, TAKAMINE)
    base = final_unit(TAKAMINE, "debito")
    cliente.post("/checkout", data={"forma": "debito", "parcelas": "1", "cidade": CAMPO_GRANDE, "total_visto": str(base)})
    assert contar(sql, "pedidos_demo") == 1
    assert (contar(sql, "pedidos"), contar(sql, "itens_pedido")) == antes


def test_total_adulterado_no_navegador_nao_finaliza(cliente, sql):
    comprar(cliente, TAKAMINE)
    r = cliente.post("/checkout", data={"forma": "debito", "parcelas": "1", "cidade": CAMPO_GRANDE, "total_visto": "1"})
    assert r.status_code == 409 and contar(sql, "pedidos_demo") == 0


def test_numeros_sequenciais_e_carrinho_esvaziado(cliente, sql):
    for esperado in ("PED-0001", "PED-0002"):
        comprar(cliente, TAKAMINE)
        base = final_unit(TAKAMINE, "debito")
        corpo = {"forma": "debito", "parcelas": "1", "cidade": CAMPO_GRANDE, "total_visto": str(base)}
        assert numero_do_pedido(cliente.post("/checkout", data=corpo)) == esperado
        assert contar(sql, "carrinhos") == 0


def test_carrinho_e_por_sessao(cliente, sql):
    comprar(cliente, TAKAMINE)
    with TestClient(criar_app(), follow_redirects=False) as outro:
        assert "Seu carrinho está vazio" in outro.get("/carrinho").text
    assert "Seu carrinho está vazio" not in cliente.get("/carrinho").text


def test_preco_nao_fica_gravado_no_carrinho(sql, cliente):
    comprar(cliente, CRAFTER)
    colunas = {l["name"] for l in sql.execute("PRAGMA table_info(carrinhos)").fetchall()}
    assert not any("preco" in c or "centavos" in c for c in colunas)


def test_ferramenta_pedido_demo_cinco_estados(cliente, sql):
    # vazio não existe: número que não é dele é negado; entrada ruim é falha
    assert consultar_pedido_demo(numero="abc", conversa_id="web-x").estado == "falha"
    assert consultar_pedido_demo(numero="PED-0001", conversa_id="").estado == "falha"
    assert consultar_pedido_demo(numero="PED-0001", conversa_id="web-x").estado == "negado"
    comprar(cliente, TAKAMINE)
    base = final_unit(TAKAMINE, "debito")
    cliente.post("/checkout", data={"forma": "debito", "parcelas": "1", "cidade": CAMPO_GRANDE, "total_visto": str(base)})
    sessao = sql.execute("SELECT sessao FROM pedidos_demo").fetchone()[0]
    r = consultar_pedido_demo(numero="ped-0001", conversa_id=sessao)
    assert r.estado == "ok" and r.dados["demonstracao"] is True and r.dados["total_gravado_centavos"] == base
    assert consultar_pedido_demo(numero="PED-0001", conversa_id="web-outra").estado == "negado"


def test_sw_nao_guarda_carrinho_nem_checkout():
    sw = (RAIZ / "src" / "emporio" / "web" / "sw.js").read_text(encoding="utf-8")
    # HTML vai sempre à rede e POST nunca passa pelo cache: carrinho, checkout e pedido não têm caminho para o cache
    assert 'pedido.method !== "GET"' in sw and "cache.put" in sw
    assert sw.count("cache.put") == 1 and "ehEstatico(url)" in sw


def test_cabecalho_mostra_a_contagem_do_carrinho(cliente):
    assert 'class="contagem-carrinho"' not in cliente.get("/").text
    comprar(cliente, TAKAMINE, 2)
    assert 'class="contagem-carrinho"' in cliente.get("/").text


# --- Lia reconhece PED- ------------------------------------------------------------------

def _pedido_demo_da_sessao(cliente):
    comprar(cliente, TAKAMINE)
    base = final_unit(TAKAMINE, "debito")
    return numero_do_pedido(cliente.post(
        "/checkout", data={"forma": "debito", "parcelas": "1", "cidade": CAMPO_GRANDE, "total_visto": str(base)}))


def test_lia_responde_pedido_demo_como_demonstracao(cliente, sql):
    from emporio.agente.laco import Agente
    numero = _pedido_demo_da_sessao(cliente)
    sessao = sql.execute("SELECT sessao FROM pedidos_demo").fetchone()[0]
    r = Agente().responder(sessao, f"cadê o meu pedido {numero}?", "eval")
    assert "Nenhum valor foi cobrado" in r.texto and numero in r.texto and "R$ 2.199,00" in r.texto
    ferramentas = [a.get("ferramenta") for a in r.acoes]
    assert "consultar_pedido_demo" in ferramentas and "consultar_pedido" not in ferramentas
    assert "telefone" not in r.texto.lower()


def test_lia_nega_pedido_demo_de_outra_conversa(cliente, sql):
    from emporio.agente.laco import Agente
    numero = _pedido_demo_da_sessao(cliente)
    r = Agente().responder("web-outra-conversa", f"status do pedido {numero.lower()}", "eval")
    assert "Não encontrei esse pedido nesta conversa" in r.texto and "R$" not in r.texto


def test_pedido_dos_dados_segue_pedindo_o_telefone():
    from emporio.agente.laco import Agente
    r = Agente().responder("c-dados", "quero saber do pedido 8", "eval")
    assert "últimos" in r.texto or "telefone" in r.texto
