"""Incremento 2: sentimento adapta o tom. Muda só o tom, nunca fatos, permissões nem ferramentas."""
from __future__ import annotations

import json

import pytest

from emporio import config
from emporio.agente import respostas, sentimento
from emporio.agente.estado import Estado
from emporio.agente.laco import Agente

EMPATIA = {f for formas in respostas.RECONHECIMENTOS.values() for f in formas}


def conversar(*mensagens, conversa="s1", agente=None):
    agente = agente or Agente()
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def tem_empatia(texto: str) -> bool:
    return any(f in texto for f in EMPATIA)


def protocolos(sql):
    return [r["protocolo"] for r in sql.execute("SELECT protocolo FROM chamados ORDER BY id")]


# 1. rótulos ----------------------------------------------------------------------------------

@pytest.mark.parametrize("frase,esperado", [
    ("Qual o horário de funcionamento?", "neutro"),
    ("Quanto custa o Crafter HT-100 no pix?", "neutro"),
    ("não estou bravo, só quero saber o preço", "neutro"),  # negação
    ("não é um absurdo, só quero saber o preço do violão", "neutro"),  # negação
    ("estou com pressa!! qual o horário?", "neutro"),  # pontuação sozinha é sinal fraco
    ("QUAL O ENDERECO DA LOJA", "neutro"),  # caixa alta sozinha é sinal fraco
    ("Quero reclamar do atraso do meu pedido", "neutro"),  # reclamar não é, por si, raiva
    ("o processo de compra é pelo site?", "neutro"),  # falso positivo de 'processo'
    ("Ninguém responde, já falei isso", "frustrado"),
    ("de novo essa pergunta, qual o horário?", "frustrado"),
    ("QUANTO CUSTA O CRAFTER??", "frustrado"),  # caixa alta + pontuação repetida
    ("já disse que o pedido é o 4", "frustrado"),
    ("que absurdo, vocês são incompetentes", "irritado"),
    ("PÉSSIMO ATENDIMENTO, NUNCA MAIS COMPRO", "irritado"),
    ("isso é uma palhaçada!!", "irritado"),
    ("vou no procon", "irritado"),
])
def test_rotulos(frase, esperado):
    assert sentimento.detectar(frase, Estado()) == esperado


def test_mesma_pergunta_repetida_e_falhas_seguidas_somam_pontos():
    e = Estado()
    assert sentimento.registrar(e, "qual o horário de funcionamento?") == "neutro"
    assert sentimento.registrar(e, "qual o horário de funcionamento?") == "frustrado"  # repetiu a pergunta
    e2 = Estado(falhas_seguidas=2)
    assert sentimento.detectar("qual o horário de funcionamento?", e2) == "frustrado"


def test_estado_guarda_o_rotulo_por_turno_e_o_trace_nao_guarda_o_texto():
    conversar("oi", "que absurdo, ninguém responde, qual o horário?")
    linhas = [json.loads(x) for x in config.caminho_trace().read_text(encoding="utf-8").splitlines() if x.strip()]
    assert [x["sentimento"] for x in linhas] == ["neutro", "irritado"]
    assert "absurdo" not in config.caminho_trace().read_text(encoding="utf-8")


# 2. efeitos ----------------------------------------------------------------------------------

def test_reconhecimento_nao_altera_fatos():
    neutro = conversar("quanto custa o Crafter HT-100 no pix?", conversa="a")[0]
    frustrado = conversar("já falei, quanto custa o Crafter HT-100 no pix?", conversa="b")[0]
    assert tem_empatia(frustrado.texto) and not tem_empatia(neutro.texto)
    assert frustrado.texto.split("\n", 1)[1].startswith(neutro.texto.split("\n")[0][:30])
    assert sorted((f.entidade_id, f.atributo, str(f.valor)) for f in frustrado.fatos) == \
        sorted((f.entidade_id, f.atributo, str(f.valor)) for f in neutro.fatos)
    for numero in ("R$ 2.399,00", "R$ 1.967,18", "18%"):
        assert numero in neutro.texto and numero in frustrado.texto


def test_sem_desculpa_nem_promessa_de_prazo_no_reconhecimento():
    for formas in respostas.RECONHECIMENTOS.values():
        for f in formas:
            baixo = f.lower()
            assert "desculp" not in baixo and "peço" not in baixo and "horas" not in baixo and "prazo" not in baixo
            assert not any(c.isdigit() for c in f)


def test_neutro_nunca_tem_frase_de_empatia():
    r = conversar("oi", "qual o endereço?", "quanto custa o Crafter HT-100?", "como funciona a troca?",
                  "não estou bravo, só quero saber o preço do Takamine GD20", "quero falar com um atendente")
    assert not any(tem_empatia(x.texto) for x in r)


def test_irritado_reconhece_e_oferece_atendente_com_pergunta_de_sim_ou_nao():
    (r,) = conversar("ridículo, ninguém responde! qual o horário de funcionamento?")
    assert tem_empatia(r.texto) and respostas.OFERTA_HUMANO in r.texto
    assert r.texto.count("?") == 1 and r.estado == "aguardando:confirmacao_registro"
    assert "Nosso horário de funcionamento" in r.texto  # o fato continua na resposta


def test_oferta_so_vira_chamado_com_sim_explicito(sql):
    r = conversar("ridículo, ninguém responde! qual o horário de funcionamento?", "sim")
    assert protocolos(sql) != [] and "EM-" in r[1].texto and len(protocolos(sql)) == 1
    conversar("ridículo, ninguém responde! qual o horário de funcionamento?", conversa="s2")
    assert len(protocolos(sql)) == 1  # a oferta sozinha não registra nada


def test_oferta_recusada_nao_volta_na_conversa(sql):
    r = conversar("ridículo, ninguém responde! qual o horário de funcionamento?", "não",
                  "isso é uma palhaçada!! qual o endereço da loja?", "VOCÊS SÃO INCOMPETENTES!! qual o horário?")
    assert "Quer que um atendente" in r[0].texto and "não registrei nada" in r[1].texto
    assert "Quer que um atendente" not in r[2].texto and "Quer que um atendente" not in r[3].texto
    assert tem_empatia(r[2].texto) or tem_empatia(r[3].texto)  # o tom continua adaptando
    assert protocolos(sql) == []


def test_dois_turnos_seguidos_frustrados_tambem_oferecem():
    r = conversar("de novo, qual o horário de funcionamento?", "ainda sem resposta, qual o endereço da loja?")
    assert respostas.OFERTA_HUMANO not in r[0].texto  # um turno frustrado só reconhece
    assert tem_empatia(r[0].texto)
    assert respostas.OFERTA_HUMANO in r[1].texto


def test_frase_de_reconhecimento_nunca_repete_na_conversa():
    r = conversar("de novo, qual o horário?", "de novo, qual o endereço?", "de novo, onde fica a loja?",
                  "de novo, qual o telefone?", "de novo, qual o horário de sábado?")
    usadas = [f for x in r for f in EMPATIA if f in x.texto]
    assert len(usadas) == len(set(usadas))


def test_pedido_de_atendente_irritado_nao_empilha_oferta_nem_empatia(sql):
    (r,) = conversar("QUE ABSURDO!! quero falar com um atendente")
    assert "Protocolo" in r.texto and respostas.OFERTA_HUMANO not in r.texto and not tem_empatia(r.texto)
    assert len(protocolos(sql)) == 1


def test_reclamacao_nao_ganha_segunda_frase_de_empatia():
    (r,) = conversar("o violão chegou riscado e ninguém me responde, que absurdo")
    assert not tem_empatia(r.texto) and r.texto.count("?") == 1
