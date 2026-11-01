"""Perguntar se é pessoa ou com quem fala é pergunta sobre a Lia, não pedido de atendente."""
import pytest

from emporio.agente.fabrica import criar_agente


@pytest.mark.parametrize("frase", ["com quem eu estou falando?", "isso aqui é uma pessoa?", "aqui é um robô?"])
def test_pergunta_de_identidade_responde_sem_chamado(frase, sql):
    r = criar_agente(None).responder("id", frase, "eval")
    assert "Lia" in r.texto and "assistente virtual" in r.texto
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 0


def test_pedido_explicito_de_pessoa_segue_abrindo_atendente(sql):
    r = criar_agente(None).responder("id2", "quero falar com uma pessoa", "eval")
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 1
