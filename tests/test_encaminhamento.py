"""registrar_encaminhamento: protocolo, idempotência, PII e transições."""
from __future__ import annotations

from emporio.ferramentas.encaminhamento import (
    iniciar_atendimento,
    marcar_encaminhamento_pendente,
    registrar_encaminhamento,
)


def _registrar(chave="k1", tipo="atendente", resumo="Cliente pediu atendimento humano.", conversa="c1"):
    return registrar_encaminhamento(conversa, tipo, resumo, chave)


def test_ok_gera_protocolo_sequencial_e_estado_registrado():
    a = _registrar("k1")
    b = _registrar("k2")
    assert a.estado == "ok" and a.dados["protocolo"] == "EM-000001" and a.dados["status"] == "registrado"
    assert b.dados["protocolo"] == "EM-000002"


def test_mesma_chave_devolve_mesmo_protocolo_sem_duplicar(sql):
    a = _registrar("k1")
    b = _registrar("k1", resumo="outro texto")
    assert a.dados["protocolo"] == b.dados["protocolo"] and b.dados["repetido"] is True
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 1


def test_prazo_de_24h_so_em_reclamacao():
    rec = _registrar("k1", tipo="reclamacao", resumo="Pedido atrasou")
    outro = _registrar("k2", tipo="atendente")
    assert rec.dados["prazo_retorno_horas_uteis"] == 24
    assert "prazo_retorno_horas_uteis" not in outro.dados


def test_negado_quando_resumo_tem_telefone_ou_email(sql):
    for resumo in ("ligar para (67) 99812-3456", "fale em 67998123456", "mande para ana@exemplo.com", "tel 3341-4444"):
        r = _registrar("kx", resumo=resumo)
        assert r.estado == "negado" and r.motivo == "resumo_com_dado_pessoal"
    assert sql.execute("SELECT COUNT(*) FROM chamados").fetchone()[0] == 0


def test_resumo_com_numero_de_pedido_e_data_passa():
    r = _registrar("k1", resumo="Devolucao do pedido 4, recebido em 15/12/2025, produto na caixa.")
    assert r.estado == "ok"


def test_falha_tipo_invalido_e_campos_vazios():
    assert registrar_encaminhamento("c1", "outro", "x", "k").estado == "falha"
    assert registrar_encaminhamento("c1", "atendente", "  ", "k").motivo == "entrada_invalida"
    assert registrar_encaminhamento("c1", "atendente", "x", "").estado == "falha"


def test_falha_de_gravacao_vira_falha(sql):
    sql.execute("DROP TABLE chamados")
    sql.commit()
    r = _registrar("k1")
    assert r.estado == "falha"


def test_todos_os_tipos_aceitos():
    for i, tipo in enumerate(("reclamacao", "atendente", "duvida_politica", "sem_dado", "falhas")):
        assert _registrar(f"k{i}", tipo=tipo).estado == "ok"


def test_transicao_so_por_funcao_propria_e_em_ordem():
    protocolo = _registrar("k1").dados["protocolo"]
    assert iniciar_atendimento(protocolo).estado == "negado"  # não pula etapa
    assert marcar_encaminhamento_pendente(protocolo).dados["status"] == "encaminhamento_pendente"
    assert marcar_encaminhamento_pendente(protocolo).estado == "negado"
    assert iniciar_atendimento(protocolo).dados["status"] == "atendimento_iniciado"
    assert iniciar_atendimento(protocolo).estado == "negado"
    assert marcar_encaminhamento_pendente("EM-999999").estado == "vazio"


def test_reenvio_depois_da_transicao_nao_volta_ao_estado_inicial():
    protocolo = _registrar("k1").dados["protocolo"]
    marcar_encaminhamento_pendente(protocolo)
    assert _registrar("k1").dados["status"] == "encaminhamento_pendente"
