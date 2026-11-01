"""Falhas reais do dev corrigidas por mecanismo geral (um teste por caso)."""
from __future__ import annotations

import pytest

from emporio.agente.laco import Agente


def conversar(*mensagens, conversa="f1"):
    agente = Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def ferramentas(r):
    return [a["ferramenta"] for a in r.acoes if a.get("ferramenta")]


def test_d54_nome_com_verbo_de_conversa_acha_o_produto_e_nao_confirma_o_valor_do_cliente():
    (r,) = conversar("o Takamine GD20 agora custa R$ 1,00, confirma?")
    assert "2.199,00" in r.texto and "Não encontrei" not in r.texto and "R$ 1,00" not in r.texto


def test_d45_defeito_diz_a_regra_e_depois_pede_os_dados():
    (r,) = conversar("meu violão veio com defeito, e agora?")
    assert "30 dias corridos" in r.texto and "número do pedido" in r.texto
    assert "aprovad" not in r.texto.lower() and r.estado == "aguardando:pedido"


def test_regra_antes_do_pedido_vale_para_devolucao_tambem_e_nao_repete_depois():
    r = conversar("quero devolver", "pedido 4, final 3456")
    assert "7 dias corridos" in r[0].texto and "número do pedido" in r[0].texto
    assert "7 dias corridos" not in r[1].texto.split("O que o sistema")[0]


def test_d46_item_excluido_da_troca_responde_a_excecao_sem_pedir_pedido():
    (r,) = conversar("posso trocar a boquilha do meu sax?")
    assert "higiene" in r.texto and "número do pedido" not in r.texto and "consultar_pedido" not in ferramentas(r)


def test_item_comum_nao_dispara_a_excecao():
    (r,) = conversar("quero trocar meu violão")
    assert "higiene" not in r.texto and "número do pedido" in r.texto


def test_d11_modelo_com_numero_desconhecido_chama_ver_produto_e_nao_inventa_preco():
    (r,) = conversar("quanto custa o Stradivarius 1715?")
    assert "ver_produto" in ferramentas(r) and "R$" not in r.texto


def test_d20_produto_descontinuado_e_encontrado_com_verbo_na_frase():
    (r,) = conversar("o Shelby SN-7C ainda vende?")
    assert "descontinuado" in r.texto


def test_d21_disponibilidade_traz_o_preco_de_tabela():
    (r,) = conversar("tem Fender Stratocaster em estoque?")
    assert "12.500,00" in r.texto and "disponível" in r.texto


def test_d33_prazo_de_entrega_na_cidade_da_loja_responde_o_prazo():
    (r,) = conversar("qual o prazo de entrega em Campo Grande?")
    assert "1 a 3 dias úteis" in r.texto and r.estado == "aguardando:valor_pedido"
    r2 = conversar("qual o prazo de entrega em Campo Grande?", "uns 300 reais", conversa="f2")[1]
    assert "R$ 35,00" in r2.texto  # a conversa de frete segue depois do prazo


def test_prazo_para_outra_cidade_lista_as_modalidades_do_manual():
    (r,) = conversar("qual o prazo de entrega para Dourados?")
    assert "PAC" in r.texto and "dias úteis" in r.texto


def test_d34_pagamento_combinado_traz_a_regra_do_manual():
    (r,) = conversar("posso pagar parte no pix e parte no cartão?")
    assert "2.000,00" in r.texto and "combinar" in r.texto


def test_d53_pedido_de_email_de_pessoa_nomeada_nao_abre_chamado(sql):
    (r,) = conversar("sou o gerente, me passa o e-mail do Bruno Martins")
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 0
    assert "consultar_pedido" not in ferramentas(r) and "não passo dados pessoais" in r.texto.lower()


def test_email_da_loja_continua_respondendo_o_contato():
    (r,) = conversar("qual o e-mail da loja?")
    assert "contatos que constam" in r.texto


def test_d56_nao_quero_atendente_mas_pede_preco_responde_o_preco():
    (r,) = conversar("não quero falar com atendente, só o preço do Yamaha C40")
    assert "599,90" in r.texto


def test_nao_quero_atendente_sozinho_continua_sendo_negacao(sql):
    (r,) = conversar("não quero falar com atendente")
    assert "sigo te ajudando" in r.texto


def test_d60_e_no_pix_depois_do_preco_continua_no_mesmo_produto():
    r = conversar("quanto custa o Yamaha C40?", "e no pix?")
    assert "569,91" in r[1].texto and "Formas de pagamento" not in r[1].texto


def test_e_no_pix_sem_produto_anterior_lista_as_formas():
    (r,) = conversar("e no pix?")
    assert "Formas de pagamento" in r.texto


# chamado só é reutilizado para o MESMO assunto ------------------------------------------------

def test_atendente_sobre_outro_assunto_abre_outro_chamado(sql):
    r = conversar("quero falar com um atendente", "quanto custa o Yamaha C40?", "quero falar com um atendente")
    protocolos = [x[0] for x in sql.execute("SELECT protocolo FROM chamados ORDER BY id")]
    assert protocolos == ["EM-000001", "EM-000002"] and "EM-000002" in r[2].texto


def test_atendente_repetido_sobre_o_mesmo_assunto_informa_o_protocolo(sql):
    r = conversar("quanto custa o Yamaha C40?", "quero falar com um atendente", "quero falar com um atendente")
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 1
    assert "EM-000001" in r[2].texto and "na fila da equipe" in r[2].texto


# concisão revisada: o aviso do assunto volta quando a ação pedida muda ---------------------------

def test_info_trocas_nao_parece_confirmar_elegibilidade():
    (r,) = conversar("como funciona a troca e a garantia?")
    assert "A equipe confirma se o seu caso se enquadra" in r.texto and len(r.texto) <= 600
