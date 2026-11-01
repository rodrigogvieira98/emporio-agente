"""Conformidade com o manual (SPEC, etapa 10): lacunas da auditoria de 01/11/2026, item a item."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from emporio import config
from emporio.agente.laco import Agente
from emporio.ferramentas.pedidos import consultar_pedido
from emporio.politicas import manual
from emporio.web.app import criar_app


def conversar(*mensagens, conversa="m1", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def hrefs(r):
    return [x["href"] for x in r.links if x["tipo"] == "link"]


# --- 1. parcelamento nunca vira nome de produto -------------------------------------------------------

@pytest.mark.parametrize("mensagem", [
    "Posso parcelar o Tagima Memphis AC-39 em 3x?",
    "Posso parcelar o Tagima Memphis AC-39 em 3 vezes?",
    "o Tagima Memphis AC-39 sai em 10x?",
])
def test_parcelamento_na_mensagem_nao_entra_na_referencia_do_produto(mensagem):
    (r,) = conversar(mensagem)
    assert "Tagima Memphis AC-39" in r.texto and "Não encontrei" not in r.texto
    assert "cada parcela" in r.texto


def test_pode_ser_em_3x_depois_do_tagima_calcula_o_tagima():
    r1, r2 = conversar("quanto custa o Tagima Memphis AC-39?", "pode ser em 3x?")
    assert "Tagima Memphis AC-39" in r2.texto and "3x" in r2.texto and "143,30" in r2.texto
    assert "Bass" not in r2.texto  # nunca o preço de outro produto


def test_e_em_3x_depois_do_yamaha_calcula_o_yamaha():
    _, r2 = conversar("quanto custa o Yamaha C40?", "e em 3x?")
    assert "Yamaha C40" in r2.texto and "3x" in r2.texto


# --- 2. exclusões do manual antes da regra genérica -----------------------------------------------------

def test_queda_e_mau_uso_recebem_a_regra_de_garantia_e_nao_a_de_defeito():
    (r,) = conversar("Meu instrumento caiu e quebrou, a garantia cobre?")
    assert "mau uso" in r.texto and "queda" in r.texto and "não" in r.texto.lower()
    assert "Pela regra da loja" not in r.texto and "pedido" not in r.texto.lower()
    assert r.estado == "concluido"


def test_setup_sob_encomenda_nao_entra_em_troca():
    (r,) = conversar("Fiz um setup sob encomenda, posso trocar?")
    assert "não entra em troca" in r.texto and "setup" in r.texto
    assert "Pela regra da loja" not in r.texto


def test_avaria_no_recebimento_manda_recusar_o_recebimento_e_falar_com_a_loja():
    (r,) = conversar("Meu instrumento chegou amassado, o que faço?")
    assert "recus" in r.texto.lower() and "recebimento" in r.texto and "loja" in r.texto
    assert "30 dias" not in r.texto and "Pela regra da loja" not in r.texto


# --- 3. privacidade ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("mensagem", [
    "Vocês usam meus dados para quê?", "Quero excluir meus dados", "Vocês compartilham meus dados com outras empresas?",
    "Qual a política de privacidade?",
])
def test_privacidade_responde_com_o_manual_e_link(mensagem):
    (r,) = conversar(mensagem)
    assert "Não entendi" not in r.texto and "foge" not in r.texto
    assert "marketing" in r.texto and "exclusão" in r.texto and "entrega de pedidos" in r.texto.replace("Processamento e ", "")
    assert "/privacidade" in hrefs(r)


# --- 4. empresa ---------------------------------------------------------------------------------------------

def test_fundacao_razao_social_e_cnpj_vem_do_manual():
    (a,) = conversar("Desde quando a loja existe?", conversa="e1")
    (b,) = conversar("Qual o CNPJ da loja?", conversa="e2")
    (c,) = conversar("Qual a razão social de vocês?", conversa="e3")
    assert "2008" in a.texto
    assert "12.345.678/0001-90" in b.texto and "Empório da Música Instrumentos Musicais Ltda." in b.texto
    assert "Empório da Música Instrumentos Musicais Ltda." in c.texto


def test_loja_que_venda_pedal_recebe_a_resposta_de_acessorios():
    (r,) = conversar("Me indica uma loja que venda pedal?")
    assert "só com instrumentos" in r.texto and "pedais" in r.texto


# --- 5. arrependimento ---------------------------------------------------------------------------------------

def test_primeira_resposta_de_arrependimento_diz_que_vale_para_compra_online():
    (r,) = conversar("Quero devolver meu pedido, me arrependi")
    assert "compra online" in r.texto and "7 dias" in r.texto


def test_compra_na_loja_fisica_explica_que_a_regra_nao_se_aplica_e_nao_oferece_registro():
    (r,) = conversar("Comprei na loja física e me arrependi, posso devolver?")
    assert "online" in r.texto and "defeito" in r.texto and "preferência" in r.texto
    assert "registrar" not in r.texto.lower() and r.estado == "concluido"


# --- 6. subtemas ----------------------------------------------------------------------------------------------

def test_frete_da_devolucao_e_por_conta_da_loja():
    (r,) = conversar("Quem paga o frete da devolução por arrependimento?")
    assert "por nossa conta" in r.texto and "Para consultar o pedido" not in r.texto


def test_defeito_depois_de_30_dias_aciona_o_fabricante_com_intermediacao():
    (r,) = conversar("Comprei há 40 dias e deu defeito, o que faço?")
    assert "fabricante" in r.texto and "intermediar" in r.texto
    assert "Pela regra da loja" not in r.texto


def test_sem_rain_check():
    (r,) = conversar("Vocês podem segurar o preço da promoção depois que acabar?")
    assert "rain check" in r.texto.lower() or "não seguramos" in r.texto.lower()
    assert "Promoções ativas:" not in r.texto


def test_debito_de_qualquer_bandeira():
    (r,) = conversar("Aceita cartão de débito de qualquer bandeira?")
    assert "bandeiras" in r.texto


def test_prazo_do_pac_e_do_sedex():
    (a,) = conversar("Qual o prazo do PAC?", conversa="p1")
    (b,) = conversar("Vocês entregam com Sedex? Qual o prazo?", conversa="p2")
    assert "PAC" in a.texto and "5 a 12 dias úteis" in a.texto and "Qual é o valor" not in a.texto
    assert "SEDEX" in b.texto and "2 a 5 dias úteis" in b.texto


def test_como_recebo_o_codigo_de_rastreio():
    (r,) = conversar("Como recebo o código de rastreamento?")
    assert "e-mail" in r.texto and "WhatsApp" in r.texto and "Correios" in r.texto
    assert "Para consultar o pedido" not in r.texto


def test_grande_porte_tem_cotacao_individual():
    (r,) = conversar("Quanto fica o frete de uma bateria acústica para Cuiabá?")
    assert "grande porte" in r.texto and "cotação individual" in r.texto


def test_categoria_sem_produto_a_venda_nao_pede_outra_faixa_de_preco():
    (r,) = conversar("vocês têm saxofone?")
    assert "faixa de preço" not in r.texto and "à venda" in r.texto and "Violões" in r.texto


# --- 7. promoção no follow-up ---------------------------------------------------------------------------------

def test_pix_tem_mais_desconto_com_produto_em_promocao_lembra_que_nao_soma():
    _, r2 = conversar("Quanto custa o Taylor 110e?", "Se eu pagar no pix tem mais desconto?")
    assert "5.519,08" in r2.texto and "não soma" in r2.texto
    assert "PIX: 5% de desconto sobre o preço de tabela" not in r2.texto


# --- 8. oferta de parcelas -------------------------------------------------------------------------------------

def test_sim_as_parcelas_mostra_a_maior_quantidade_valida_nas_duas_leituras():
    r1, r2 = conversar("Quanto custa o Yamaha C40?", "sim")
    assert "5x" in r2.texto and "119,98" in r2.texto and "12x" not in r2.texto
    assert "não atende" not in r2.texto


def test_sim_as_parcelas_de_produto_caro_continua_em_12x():
    _, r2 = conversar("Quanto custa o Martin D-28 Dreadnought?", "sim")
    assert "12x" in r2.texto and "958,25" in r2.texto


# --- 9. contatos com uma fonte só ---------------------------------------------------------------------------

def test_lia_e_site_usam_o_mesmo_email_e_os_mesmos_numeros(monkeypatch):
    from emporio.web import apresentacao

    (r,) = conversar("qual o contato da loja?")
    esperado = {manual.fato("contato.email_capa").valor, manual.fato("contato.telefone_capa").valor,
                manual.fato("contato.whatsapp_secao_7").valor}
    assert all(v in r.texto for v in esperado)
    valores = {c["valor"] for c in apresentacao.loja()["contatos"]}
    assert valores <= esperado and manual.fato("contato.email_capa").valor in valores
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    with TestClient(criar_app()) as c:
        for rota in ("/", "/fale-conosco"):
            html = c.get(rota).text
            assert "contato@empóriodamusica" not in html
            assert "contato@emporiodamusica.com.br" in html or rota == "/"


def test_tratamento_das_ambiguidades_de_contato_aponta_para_politicas_e_readme():
    ambiguidades = {a.id: a for a in manual.carregar_manual().ambiguidades}
    for id_ in ("telefone_whatsapp", "email"):
        t = ambiguidades[id_].tratamento
        assert t != "informar_ambos_e_pedir_confirmacao_da_equipe" and "politicas" in t and "readme" in t


# --- 10. data do pedido -----------------------------------------------------------------------------------------

def test_consultar_pedido_devolve_a_data_do_pedido(sql):
    r = consultar_pedido(pedido_id=4, final_telefone="3456", conversa_id="d1")
    esperado = sql.execute("SELECT data_pedido FROM pedidos WHERE id = 4").fetchone()[0]
    assert r.estado == "ok" and r.dados["data_pedido"] == esperado
    assert {"pedido_id", "status", "itens", "total_gravado_centavos", "forma_pagamento", "rastreio", "previsao",
            "previsao_vencida", "nota"} <= set(r.dados)  # nenhum campo saiu


def test_defeito_com_pedido_antigo_usa_a_data_do_pedido_para_o_prazo(sql):
    sql.execute("UPDATE pedidos SET data_pedido = '2026-10-21' WHERE id = 4")
    sql.commit()
    r = conversar("meu violão veio com defeito", "pedido 4, final 3456", conversa="d2")
    assert "21/10/2026" in r[1].texto and "dentro do prazo de 30 dias" in r[1].texto
    sql.execute("UPDATE pedidos SET data_pedido = '2026-08-01' WHERE id = 4")
    sql.commit()
    r = conversar("meu violão veio com defeito", "pedido 4, final 3456", conversa="d3")
    assert "fabricante" in r[1].texto and "01/08/2026" in r[1].texto


# --- 11. fechamento cordial -------------------------------------------------------------------------------------

def test_resposta_informativa_fecha_perguntando_se_precisa_de_mais_alguma_coisa():
    (r,) = conversar("qual o telefone da loja?")
    assert r.texto.rstrip().endswith("Posso ajudar em mais alguma coisa?")


def test_fechamento_nao_vem_quando_o_cliente_encerra_nem_junto_de_outra_pergunta():
    (a,) = conversar("obrigado, tchau", conversa="f1")
    assert "mais alguma coisa" not in a.texto
    (b,) = conversar("quanto custa o Yamaha C40?", conversa="f2")
    assert "mais alguma coisa" not in b.texto and b.texto.count("?") == 1
    r1, r2 = conversar("qual o telefone da loja?", "e as formas de pagamento?", conversa="f3")
    assert "mais alguma coisa" in r1.texto and "mais alguma coisa" not in r2.texto  # no máximo a cada poucos turnos


# --- terminal ------------------------------------------------------------------------------------------------

def test_cli_mostra_o_endereco_dos_links_como_texto():
    import subprocess
    import sys

    r = subprocess.run([sys.executable, '-m', 'emporio.cli', '--origem', 'demo', '--conversa', 'cli-links'],
                       input='quanto custa o Yamaha C40?' + chr(10), capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert r.returncode == 0, r.stderr
    assert '/produto/81' in r.stdout
