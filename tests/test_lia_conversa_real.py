"""Ajustes da conversa real do Rodrigo: uma pergunta por resposta, retomar só com dado e oferta de parcelas."""
from __future__ import annotations

from emporio.agente.laco import Agente


def dizer(*mensagens, conversa="c1"):
    agente = Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def test_resposta_que_termina_em_pergunta_nao_traz_convite_de_retomar():
    # devolução com dado do cliente fica pendente; a lista termina em pergunta e o convite espera
    rs = dizer("quero devolver um produto comprado online", "quais os baixos que vocês têm?")
    assert rs[1].texto.rstrip().endswith("?") and "Quer retomar" not in rs[1].texto
    assert rs[1].texto.count("?") == 1


def test_convite_de_retomar_volta_no_proximo_turno_sem_outra_pergunta():
    rs = dizer("quero devolver um produto comprado online", "quais os baixos que vocês têm?", "qual o horário de vocês?")
    assert "Quer retomar" in rs[2].texto


def test_nao_a_pergunta_da_lista_nao_e_aplicado_a_retomada():
    rs = dizer("quero devolver um produto comprado online", "quais os baixos que vocês têm?", "não")
    assert "deixei esse assunto de lado" not in rs[2].texto


def test_sem_dado_do_cliente_nao_ha_convite_de_retomar():
    rs = dizer("quero consultar meu pedido", "qual o horário de vocês?")
    assert "Quer retomar" not in rs[1].texto


def test_preco_oferece_parcelas_e_o_sim_mostra_as_do_produto_em_foco():
    r1, r2 = dizer("quanto custa o Yamaha C40?", "sim")
    assert r1.texto.endswith("Quer ver as parcelas no cartão de crédito?") and r1.estado == "aguardando:parcelamento"
    assert "No crédito em" in r2.texto and "cada parcela" in r2.texto and "Sobre o que você quer falar" not in r2.texto
    assert r2.texto.count("?") == 0


def test_nao_a_oferta_de_parcelas_encerra_e_outra_pergunta_segue_normal():
    r1, r2 = dizer("quanto custa o Yamaha C40?", "não")
    assert "Tudo bem" in r2.texto and "No crédito" not in r2.texto
    s1, s2 = dizer("quanto custa o Yamaha C40?", "qual o horário de vocês?", conversa="c2")
    assert "No crédito" not in s2.texto and "9h" in s2.texto


def test_pedido_de_atendente_depois_do_preco_nao_vira_sim_das_parcelas():
    r = dizer("quanto custa o Yamaha C40?", "quero falar com um atendente")
    assert "No crédito" not in r[1].texto


def test_sequencia_completa_pedido_instrumento_baixos_nao_pix_do_primeiro_sim():
    rs = dizer("quero consultar meu pedido", "quero encontrar um instrumento", "baixos", "não", "pix do primeiro", "sim")
    assert all("Quer retomar" not in r.texto for r in rs)
    assert rs[2].texto.count("?") == 1
    assert "No PIX" in rs[4].texto and rs[4].texto.endswith("Quer ver as parcelas no cartão de crédito?")
    assert "No crédito em" in rs[5].texto and "Sobre o que você quer falar" not in rs[5].texto
