"""Estados de buscar_produtos e ver_produto.

Estados que a ferramenta não produz por desenho (negado, e ambiguo na busca) são
conferidos como ausentes.
"""
from __future__ import annotations

from emporio.ferramentas.envelope import Resultado
from emporio.ferramentas.produtos import buscar_produtos, ver_produto


def test_buscar_ok_ordenado_por_preco_e_limitado():
    r = buscar_produtos(categoria="violao", limite=50)
    assert isinstance(r, Resultado) and r.estado == "ok"
    precos = [i["preco_centavos"] for i in r.dados["itens"]]
    assert len(precos) == 5 and precos == sorted(precos)
    assert r.dados["total_encontrado"] > 5
    assert all(i["situacao_venda"] == "disponivel" for i in r.dados["itens"])
    assert r.fontes and r.id_consulta


def test_buscar_normaliza_acento_e_caixa():
    a = buscar_produtos(categoria="VIOLÕES", termo="TAKAMINE")
    b = buscar_produtos(categoria="violoes", termo="takamine")
    assert a.estado == b.estado == "ok"
    assert [i["id"] for i in a.dados["itens"]] == [i["id"] for i in b.dados["itens"]]


def test_buscar_vazio_categoria_inexistente_e_categoria_sem_produtos():
    r = buscar_produtos(categoria="acessorios")
    assert r.estado == "vazio" and r.motivo == "categoria_inexistente"
    r2 = buscar_produtos(categoria="Instrumentos de Sopro (Metais)")
    assert r2.estado == "vazio" and r2.dados["total_encontrado"] == 0
    assert buscar_produtos(termo="zzzinexistente").estado == "vazio"


def test_buscar_falha_faixa_incoerente_e_entrada_invalida():
    assert buscar_produtos(preco_min=5000, preco_max=1000).motivo == "faixa_incoerente"
    assert buscar_produtos(preco_min=5000, preco_max=1000).estado == "falha"
    assert buscar_produtos(preco_min=-1).estado == "falha"
    assert buscar_produtos(limite=0).motivo == "entrada_invalida"
    assert buscar_produtos(preco_max=10.5).motivo == "entrada_invalida"  # float nunca vira dinheiro
    assert buscar_produtos(categoria=123).motivo == "entrada_invalida"
    assert buscar_produtos(inexistente=1).motivo == "entrada_invalida"


def test_buscar_so_vende_ativo_com_estoque_e_pode_incluir_indisponiveis():
    padrao = {i["id"] for i in buscar_produtos(categoria="violoes", limite=5, preco_max=80000).dados["itens"]}
    assert 96 not in padrao  # estoque zero
    esgotado = buscar_produtos(termo="GF-3D", incluir_indisponiveis=True).dados["itens"][0]
    assert (esgotado["id"], esgotado["situacao_venda"]) == (96, "esgotado")
    assert buscar_produtos(termo="GF-3D").estado == "vazio"
    sj = buscar_produtos(termo="Shelby SN-7C", incluir_indisponiveis=True).dados["itens"]
    assert sj[0]["situacao_venda"] == "descontinuado"
    em_breve = buscar_produtos(termo="KA-ABP-CTG", incluir_indisponiveis=True).dados["itens"]
    assert em_breve[0]["situacao_venda"] == "em_breve"


def test_buscar_mostra_promocao_ativa():
    item = buscar_produtos(termo="Crafter HT-100").dados["itens"][0]
    assert item["promocao"]["percentual"] == 18
    sem = buscar_produtos(termo="Takamine GD20").dados["itens"][0]
    assert sem["promocao"] is None  # a promocao 4 esta inativa


def test_buscar_nunca_negado_nem_ambiguo():
    for r in (buscar_produtos(categoria="violoes"), buscar_produtos(categoria="x"), buscar_produtos(limite=0)):
        assert r.estado not in ("negado", "ambiguo")


def test_ver_produto_ok_com_nome_exato_ou_tokens():
    r = ver_produto("Takamine GD20")
    assert r.estado == "ok" and r.dados["id"] == 95
    exato = ver_produto("takamine gd20 dreadnought natural")
    assert exato.estado == "ok" and exato.dados["id"] == 95
    assert ver_produto(95).dados["nome"].startswith("Takamine GD20")


def test_ver_produto_ambiguo_takamine_com_quatro_opcoes():
    r = ver_produto("Takamine")
    assert r.estado == "ambiguo" and len(r.dados["opcoes"]) == 4
    assert {o["id"] for o in r.dados["opcoes"]} == {95, 100, 105, 115}


def test_ver_produto_ambiguo_limita_cinco_opcoes():
    r = ver_produto("Yamaha")
    assert r.estado == "ambiguo" and len(r.dados["opcoes"]) == 5 and r.dados["total_opcoes"] > 5


def test_ver_produto_vazio_e_falha():
    assert ver_produto("Gibson Flying V").estado == "vazio"
    assert ver_produto(99999).estado == "vazio"
    assert ver_produto("   ").estado == "falha"
    assert ver_produto(None).motivo == "entrada_invalida"
    assert ver_produto("a", "b").estado == "falha"


def test_falha_interna_vira_falha_sem_subir(monkeypatch, tmp_path):
    monkeypatch.setenv("EMPORIO_DB", str(tmp_path / "nao_existe" / "x.db"))
    r = ver_produto("Takamine GD20")
    assert r.estado == "falha" and r.motivo == "erro_interno"
