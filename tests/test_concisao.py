"""Concisão e redundância: o que já foi dito não volta sem pedido, e o cliente que pergunta de novo recebe o fato."""
from __future__ import annotations

import pytest

from emporio.agente.concisao import deduplicar_frases
from emporio.agente.estado import carregar_estado
from emporio.agente.laco import Agente

CONVERSA_LONGA = [
    "oi", "qual o horário de vocês?", "onde fica a loja?", "tem promoção?", "quanto custa o Crafter HT-100?",
    "quais formas de pagamento?", "tem violão até R$ 1000?", "e guitarra, tem?", "oi, tudo bem?",
    "como funciona a garantia?", "quero falar com um atendente",
]


def rodar(mensagens, concisao, conversa="c1", hora=None, monkeypatch=None):
    agente = Agente(concisao=concisao)
    return [agente.responder(conversa, m, "eval") for m in mensagens]


def total(respostas, chave):
    return sum(r.contagens.get(chave, 0) for r in respostas)


def test_conversa_longa_nao_repete_aviso_nem_saudacao(monkeypatch):
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-03-22T10:00:00")  # domingo: há aviso de expediente
    rs = rodar(CONVERSA_LONGA, concisao=True)
    assert total(rs, "avisos_reapresentados") == 0 and total(rs, "fatos_reapresentados") == 0
    assert sum(r.texto.count("Eu sou a Lia") for r in rs) == 1
    assert rs[8].texto.startswith("Em que posso ajudar?")  # segundo oi: sem apresentação de novo
    assert sum("fora do expediente" in r.texto for r in rs) == 1
    assert sum("calendário de feriados" in r.texto for r in rs) == 1
    assert sum("não soma com" in r.texto for r in rs) == 1
    assert sum("preço de tabela." in r.texto and "Os valores são o preço de tabela" in r.texto for r in rs) == 1


def test_o_controle_sem_concisao_repete_e_a_metrica_enxerga(monkeypatch):
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-03-22T10:00:00")
    rs = rodar(CONVERSA_LONGA, concisao=False)
    assert sum(r.texto.count("Eu sou a Lia") for r in rs) == 2
    assert total(rs, "avisos_reapresentados") >= 3
    assert total(rs, "avisos_exibidos") > total(rodar(CONVERSA_LONGA, concisao=True, conversa="c2"), "avisos_exibidos")


def test_ao_perguntar_de_novo_o_cliente_recebe_o_fato_e_o_aviso_do_assunto():
    a, b = rodar(["qual o horário de vocês?", "qual o horário de vocês?"], concisao=True)
    assert "09:00 às 18:00" in b.texto and "calendário de feriados" in b.texto and b.texto.endswith(a.texto)  # repetir a pergunta é sinal de frustração: só ganha a frase de reconhecimento antes do mesmo bloco


def test_fato_pedido_de_novo_aparece_inteiro():
    a, b = rodar(["quanto custa o Crafter HT-100?", "e o preço do Crafter HT-100 mesmo?"], concisao=True)
    for r in (a, b):
        assert "R$ 2.399,00" in r.texto and "R$ 1.967,18" in r.texto


def test_valor_que_mudou_reaparece(monkeypatch):
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-03-22T10:00:00")  # domingo: volta amanhã
    agente = Agente(concisao=True)
    a = agente.responder("c1", "quero falar com um atendente", "eval")
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-03-25T07:00:00")  # quarta cedo: volta hoje
    b = agente.responder("c1", "quero falar com um atendente", "eval")
    assert "amanhã às 09:00" in a.texto and "hoje às 09:00" in b.texto


def test_ja_informados_guarda_entidade_atributo_e_valor_e_persiste():
    rodar(["quanto custa o Crafter HT-100?", "oi"], concisao=True)
    estado = carregar_estado("c1")
    assert estado.ja_saudou is True
    chave = "fato:condicao:90:final_centavos"
    assert estado.ja_informados[chave]["valor"] == "196718"
    assert estado.ja_informados["aviso:pix_nao_soma"]["intencao"] == "preco_produto"


def test_fato_citado_pelo_cliente_nao_conta_como_reapresentado():
    a, b = rodar(["tem promoção?", "quanto custa o Crafter HT-100?"], concisao=True)
    assert "R$ 1.967,18" in b.texto and b.contagens["fatos_reapresentados"] == 0


def test_fato_reapresentado_sem_o_cliente_citar_e_contado_mas_o_bloco_nunca_sai():
    a, b = rodar(["quanto custa o Crafter HT-100?", "tem promoção?"], concisao=True)
    assert "R$ 1.967,18" in b.texto  # bloco necessário à resposta atual nunca sai
    assert b.contagens["fatos_reapresentados"] >= 1


def test_redacao_nao_repete_frase_livre_ja_dita_em_resposta_anterior():
    from emporio.agente.llm_decisor import LlmDecisor
    from emporio.agente.redacao import Redator
    from test_llm import ClienteFalso, proposta

    cliente = ClienteFalso(proposta(ferramenta="consultar_politica", temas=["horario"]), proposta(resposta="horario"))
    redator = Redator("falso:1b", ClienteFalso({"abertura": "Claro, já te explico.", "fechamento": None}))
    agente = Agente(LlmDecisor("falso:1b", cliente), redator, concisao=True)
    a = agente.responder("c1", "qual o horário de vocês?", "eval")
    cliente.saidas[:] = [proposta(ferramenta="consultar_politica", temas=["horario"]), proposta(resposta="horario")]
    b = agente.responder("c1", "qual o horário de vocês?", "eval")
    assert a.texto.startswith("Claro, já te explico.") and not b.texto.startswith("Claro")
    assert "09:00 às 18:00" in b.texto  # o bloco factual segue inteiro


def test_remove_frase_repetida_dentro_do_turno_e_contra_respostas_anteriores():
    anteriores = ["Posso ajudar com mais alguma coisa? Fico à disposição para qualquer dúvida."]
    texto = ("Combinado.\nFico à disposição para qualquer dúvida.\nPosso ajudar em mais alguma coisa?\n"
             "Combinado!\nO total é R$ 10,00 hoje.\nO total é R$ 10,00 hoje.")
    novo, removidas = deduplicar_frases(texto, anteriores)
    assert "Fico à disposição" not in novo and novo.count("Combinado") == 1
    assert novo.count("R$ 10,00") == 2  # frase com número nunca sai
    assert "Posso ajudar em mais alguma coisa?" in novo  # pergunta fica
    assert removidas >= 2


def test_nao_remove_item_de_lista_nem_pedido_de_confirmacao():
    texto = "- Violão A\n- Violão A\nQuer que eu registre? Responda sim ou não."
    novo, _ = deduplicar_frases(texto, ["Quer que eu registre? Responda sim ou não."])
    assert novo.count("- Violão A") == 2 and "Responda sim ou não" in novo


def test_dedupe_so_age_com_concisao_ligada():
    a = Agente(concisao=False)
    a.responder("c1", "oi", "eval")
    assert "Eu sou a Lia" in a.responder("c1", "oi", "eval").texto


@pytest.mark.parametrize("ligada", [True, False])
def test_resposta_de_pedido_do_cliente_sobrevive_a_concisao(ligada):
    textos = [r.texto for r in rodar(["quero devolver", "pedido 4 final 3456", "online, recebi em 15/12/2025, sem uso", "sim"],
                                    concisao=ligada)]
    assert "R$ 799,90" in textos[2] and "Chamado registrado. Protocolo: EM-000001" in textos[3]
