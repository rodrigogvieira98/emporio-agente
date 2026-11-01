"""listar_promocoes: só is_active=1, nunca por calendário."""
from __future__ import annotations

from emporio.ferramentas.promocoes import listar_promocoes


def test_ok_lista_as_quatro_ativas_com_original_percentual_e_final():
    r = listar_promocoes()
    assert r.estado == "ok" and r.dados["total"] == 4
    por_produto = {i["produto_id"]: i for i in r.dados["promocoes"]}
    assert set(por_produto) == {127, 121, 90, 94}
    crafter = por_produto[90]
    assert (crafter["original_centavos"], crafter["percentual"], crafter["final_centavos"]) == (239900, 18, 196718)
    assert crafter["situacao_venda"] == "disponivel" and r.fontes[0].tipo == "banco"


def test_nunca_lista_inativa_nem_deduz_por_nome_de_campanha():
    nomes = {i["descricao"] for i in listar_promocoes().dados["promocoes"]}
    assert "Black Friday" not in nomes and "Promoção de Páscoa" not in nomes


def test_termo_filtra_por_campanha_ou_produto():
    assert listar_promocoes("Oferta Especial").dados["promocoes"][0]["produto_id"] == 127
    assert listar_promocoes("crafter").dados["total"] == 1


def test_vazio_quando_a_promocao_nao_esta_ativa():
    r = listar_promocoes("Black Friday")
    assert r.estado == "vazio" and r.motivo == "promocao_nao_ativa" and r.dados["promocoes"] == []


def test_vazio_quando_nenhuma_esta_ativa(sql):
    sql.execute("UPDATE promocoes SET ativa = 0")
    sql.commit()
    assert listar_promocoes().estado == "vazio"


def test_duas_ativas_no_mesmo_produto_nao_inventam_preco_final(sql):
    sql.execute("INSERT INTO promocoes VALUES (100, 90, 5, 'Duplicada', 1)")
    sql.commit()
    itens = [i for i in listar_promocoes().dados["promocoes"] if i["produto_id"] == 90]
    assert len(itens) == 2 and all(i["conflito"] and i["final_centavos"] is None for i in itens)


def test_falha_entrada_invalida_e_erro_interno(monkeypatch, tmp_path):
    assert listar_promocoes("   ").motivo == "entrada_invalida"
    assert listar_promocoes(termo=5).estado == "falha"
    monkeypatch.setenv("EMPORIO_DB", str(tmp_path / "nada" / "x.db"))
    assert listar_promocoes().motivo == "erro_interno"


def test_nunca_negado_nem_ambiguo():
    assert listar_promocoes().estado not in ("negado", "ambiguo")
