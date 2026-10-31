"""consultar_pedido: identificação simulada, negado unificado e sem dados pessoais."""
from __future__ import annotations

import json

from emporio.ferramentas.pedidos import consultar_pedido

# pedido 4 é do cliente 1, cujo telefone termina em 3456
PEDIDO, FINAL = 4, "3456"


def _sem_id(r):
    d = r.model_dump()
    d.pop("id_consulta")
    return d


def test_ok_traz_status_itens_total_gravado_forma_e_rastreio():
    r = consultar_pedido(PEDIDO, FINAL, "c1")
    assert r.estado == "ok"
    d = r.dados
    assert d["status"] == "delivered" and d["forma_pagamento"] == "boleto"
    assert d["itens"] == [{"nome": "Giannini GF-3D Dreadnought Sunburst", "quantidade": 1}]
    assert d["total_gravado_centavos"] == 79990
    assert d["rastreio"] == "BRQM7890123BR" and d["previsao"] == "2025-12-22"
    assert d["previsao_vencida"] is False  # entregue
    assert r.fontes[0].tipo == "banco"


def test_total_divergente_aparece_como_gravado(sql):
    cliente = sql.execute("SELECT c.telefone FROM pedidos p JOIN clientes c ON c.id = p.cliente_id WHERE p.id = 3").fetchone()
    final = "".join(ch for ch in cliente["telefone"] if ch.isdigit())[-4:]
    r = consultar_pedido(3, final, "c1")
    assert r.dados["total_gravado_centavos"] == 345000  # os itens somam 3498, o gravado vale


def test_pedido_8_enviado_com_previsao_vencida(sql):
    tel = sql.execute("SELECT c.telefone FROM pedidos p JOIN clientes c ON c.id = p.cliente_id WHERE p.id = 8").fetchone()[0]
    r = consultar_pedido(8, "".join(c for c in tel if c.isdigit())[-4:], "c8")
    assert r.dados["status"] == "shipped" and r.dados["previsao"] == "2026-02-28"
    assert r.dados["previsao_vencida"] is True


def test_nota_do_pedido_cancelado(sql):
    tel = sql.execute("SELECT c.telefone FROM pedidos p JOIN clientes c ON c.id = p.cliente_id WHERE p.id = 17").fetchone()[0]
    r = consultar_pedido(17, "".join(c for c in tel if c.isdigit())[-4:], "c17")
    assert r.dados["status"] == "cancelled" and "cancelado pelo cliente" in r.dados["nota"]
    assert r.dados["previsao_vencida"] is False


def test_nunca_devolve_dado_pessoal(sql):
    r = consultar_pedido(PEDIDO, FINAL, "c1")
    bruto = json.dumps(r.model_dump(), ensure_ascii=False)
    cli = sql.execute("SELECT * FROM clientes WHERE id = 1").fetchone()
    for campo in ("nome", "telefone", "email", "cidade"):
        assert cli[campo] not in bruto
    assert FINAL not in bruto
    assert not ({"nome", "telefone", "email", "cidade", "cliente"} & set(r.dados))


def test_negado_unificado_para_inexistente_final_errado_e_limite():
    inexistente = consultar_pedido(9999, FINAL, "a")
    errado = consultar_pedido(PEDIDO, "0000", "b")
    assert inexistente.estado == errado.estado == "negado"
    assert _sem_id(inexistente) == _sem_id(errado)
    for _ in range(2):
        consultar_pedido(PEDIDO, "0000", "c")
    terceiro = consultar_pedido(PEDIDO, "0000", "c")
    bloqueado = consultar_pedido(PEDIDO, FINAL, "c")  # final certo, mas limite estourado
    assert _sem_id(terceiro) == _sem_id(bloqueado) == _sem_id(errado)


def test_limite_e_por_conversa_e_acerto_nao_conta():
    for _ in range(2):
        consultar_pedido(PEDIDO, "0000", "x")
    assert consultar_pedido(PEDIDO, FINAL, "x").estado == "ok"
    assert consultar_pedido(PEDIDO, FINAL, "x").estado == "ok"
    consultar_pedido(PEDIDO, "0000", "x")
    assert consultar_pedido(PEDIDO, FINAL, "x").estado == "negado"  # 3 erros acumulados
    assert consultar_pedido(PEDIDO, FINAL, "outra").estado == "ok"


def test_final_digitado_nao_fica_gravado(sql):
    consultar_pedido(PEDIDO, "0000", "c1")
    consultar_pedido(PEDIDO, FINAL, "c1")
    colunas = [r[1] for r in sql.execute("PRAGMA table_info(tentativas_pedido)")]
    assert "final_telefone" not in colunas
    despejo = json.dumps([tuple(r) for r in sql.execute("SELECT * FROM tentativas_pedido")])
    assert FINAL not in despejo and "0000" not in despejo


def test_falha_entrada_invalida_nao_conta_tentativa(sql):
    for final in ("12", "abcd", "12345", ""):
        r = consultar_pedido(PEDIDO, final, "c1")
        assert r.estado == "falha" and r.motivo == "entrada_invalida"
    assert consultar_pedido("4", FINAL, "c1").estado == "falha"
    assert consultar_pedido(PEDIDO, FINAL, " ").estado == "falha"
    assert sql.execute("SELECT COUNT(*) FROM tentativas_pedido").fetchone()[0] == 0


def test_falha_interna_vira_falha(monkeypatch, tmp_path):
    monkeypatch.setenv("EMPORIO_DB", str(tmp_path / "nada" / "x.db"))
    r = consultar_pedido(PEDIDO, FINAL, "c1")
    assert r.estado == "falha" and r.motivo == "erro_interno"
