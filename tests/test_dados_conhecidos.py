"""Reafirma a evidência dos dados originais, sem corrigir nada."""
from __future__ import annotations

import re

from emporio.dados.carga import carregar
from emporio.dinheiro import dividir
from emporio.ferramentas.produtos import buscar_produtos
from emporio.politicas import manual


def test_catalogo_e_categorias(sql):
    assert sql.execute("SELECT COUNT(*) FROM produtos").fetchone()[0] == 65
    vazias = {r["id"] for r in sql.execute(
        "SELECT c.id FROM categorias c LEFT JOIN produtos p ON p.categoria_id = c.id WHERE p.id IS NULL")}
    assert vazias == {6, 7, 8}


def test_status_e_estoque(sql):
    nao_ativos = {r["id"] for r in sql.execute("SELECT id FROM produtos WHERE status != 'active'")}
    assert nao_ativos == {113, 130, 136}
    ativo_zerado = {r["id"] for r in sql.execute("SELECT id FROM produtos WHERE status = 'active' AND estoque = 0")}
    assert ativo_zerado == {96}


def test_promocoes(sql):
    assert sql.execute("SELECT COUNT(*) FROM promocoes").fetchone()[0] == 25
    ativas = {r["produto_id"] for r in sql.execute("SELECT produto_id FROM promocoes WHERE ativa = 1")}
    assert ativas == {127, 121, 90, 94}
    p4 = sql.execute("SELECT produto_id, ativa FROM promocoes WHERE id = 4").fetchone()
    assert (p4["produto_id"], p4["ativa"]) == (95, 0)


def _soma_itens(sql, pedido):
    return sql.execute(
        "SELECT SUM(p.preco_centavos * i.quantidade) FROM itens_pedido i JOIN produtos p ON p.id = i.produto_id "
        "WHERE i.pedido_id = ?", (pedido,)).fetchone()[0]


def test_totais_divergentes_ficam_como_gravados(sql):
    pedidos = [r["id"] for r in sql.execute("SELECT id FROM pedidos")]
    divergentes = {p for p in pedidos if _soma_itens(sql, p) != sql.execute(
        "SELECT total_centavos FROM pedidos WHERE id = ?", (p,)).fetchone()[0]}
    assert divergentes == {3, 20}
    gravado = {r["id"]: r["total_centavos"] for r in sql.execute("SELECT id, total_centavos FROM pedidos")}
    assert (gravado[3], _soma_itens(sql, 3)) == (345000, 349800)
    assert (gravado[20], _soma_itens(sql, 20)) == (140000, 148800)


def test_pix_sem_cinco_por_cento(sql):
    pix = {r["id"] for r in sql.execute("SELECT id FROM pedidos WHERE forma_pagamento = 'pix'")}
    sem_desconto = {p for p in pix if _soma_itens(sql, p) == sql.execute(
        "SELECT total_centavos FROM pedidos WHERE id = ?", (p,)).fetchone()[0]}
    assert sem_desconto == {1, 5, 10, 13, 17}


def test_parcela_abaixo_do_minimo_da_faixa(sql):
    faixas = manual.valor("pagamento.parcelamento_faixas")
    abaixo = set()
    for r in sql.execute("SELECT id, total_centavos, forma_pagamento FROM pedidos WHERE forma_pagamento LIKE 'credit_%'"):
        n = int(re.search(r"(\d+)x", r["forma_pagamento"]).group(1))
        minimo = next(f["parcela_minima_centavos"] for f in faixas if f["de"] <= n <= f["ate"])
        if dividir(r["total_centavos"], n) < minimo:
            abaixo.add(r["id"])
    assert abaixo == {9, 16, 18}


def test_clientes_com_mesmo_email(sql):
    emails = {r["id"]: r["email"] for r in sql.execute("SELECT id, email FROM clientes WHERE id IN (11, 43)")}
    assert emails[11] == emails[43]
    repetidos = sql.execute("SELECT COUNT(*) FROM (SELECT email FROM clientes GROUP BY email HAVING COUNT(*) > 1)")
    assert repetidos.fetchone()[0] == 1


def test_pedido_8_enviado_com_previsao_antiga(sql):
    p = sql.execute("SELECT status, previsao_entrega FROM pedidos WHERE id = 8").fetchone()
    assert (p["status"], p["previsao_entrega"]) == ("shipped", "2026-02-28")


def test_doze_violoes_vendaveis_ate_mil_reais(sql):
    r = buscar_produtos(categoria="violões", preco_max=100000)
    assert r.estado == "ok" and r.dados["total_encontrado"] == 12
    direto = sql.execute("SELECT COUNT(*) FROM produtos WHERE categoria_id = 5 AND status = 'active' "
                         "AND estoque > 0 AND preco_centavos <= 100000").fetchone()[0]
    assert direto == 12


def test_carga_e_idempotente(tmp_path):
    from pathlib import Path
    raw = Path(__file__).resolve().parents[1] / "data" / "raw"
    destino = tmp_path / "x.db"
    a = carregar(raw, destino)
    b = carregar(raw, destino)
    assert a == b and a["produtos"] == 65
