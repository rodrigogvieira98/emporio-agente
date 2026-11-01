"""calcular_condicoes: valores esperados e estados."""
from __future__ import annotations

from emporio.ferramentas.condicoes import calcular_condicoes


def test_crafter_ht100_pix_com_promocao_sem_somar_pix():
    r = calcular_condicoes(produto_id=90, forma="pix")
    assert r.estado == "ok"
    d = r.dados
    assert (d["original_centavos"], d["percentual"], d["final_centavos"]) == (239900, 18, 196718)
    assert d["pix_aplicado"] is False  # promoção não soma com o PIX


def test_takamine_gd20_sem_promocao_pix_aplica_desconto_do_manual():
    r = calcular_condicoes(produto_id=95, forma="pix")
    d = r.dados
    assert d["percentual"] is None and d["pix_aplicado"] is True
    assert (d["original_centavos"], d["final_centavos"]) == (219900, 208905)
    cartao = calcular_condicoes(produto_id=95, forma="debito").dados
    assert cartao["final_centavos"] == 219900 and cartao["pix_aplicado"] is False


def test_shelby_sn100_em_6x_requer_confirmacao():
    r = calcular_condicoes(produto_id=89, forma="credito", parcelas=6)
    d = r.dados
    assert r.estado == "ok" and d["permitido"] == "requer_confirmacao"
    assert d["parcela_centavos"] == 9150
    assert (d["leitura_tabela"], d["leitura_faixas"]) == (False, True)


def test_credito_ambas_leituras_sim_e_ambas_nao():
    sim = calcular_condicoes(produto_id=93, forma="credito", parcelas=12).dados
    assert sim["permitido"] == "sim"
    nao = calcular_condicoes(valor=5000, forma="credito", parcelas=2).dados  # 25,00 por parcela
    assert nao["permitido"] == "nao" and (nao["leitura_tabela"], nao["leitura_faixas"]) == (False, False)


def test_parcelas_nas_fronteiras_das_faixas():
    # 3x de 50,00 passa na faixa, 4x de 79,99 nao passa
    assert calcular_condicoes(valor=15000, forma="credito", parcelas=3).dados["leitura_faixas"] is True
    assert calcular_condicoes(valor=31996, forma="credito", parcelas=4).dados["leitura_faixas"] is False
    assert calcular_condicoes(valor=32000, forma="credito", parcelas=4).dados["leitura_faixas"] is True


def test_arredondamento_meio_para_cima_ao_centavo():
    assert calcular_condicoes(valor=10, forma="pix").dados["final_centavos"] == 10  # 9,5 -> 10
    assert calcular_condicoes(valor=30, forma="pix").dados["final_centavos"] == 29  # 28,5 -> 29
    assert calcular_condicoes(valor=10, forma="pix").dados["final_centavos"].__class__ is int


def test_frete_campo_grande_gratis_a_partir_de_500_e_taxa_abaixo():
    gratis = calcular_condicoes(valor=50001, forma="boleto", cidade="Campo Grande").dados["frete"]
    assert gratis["situacao"] == "gratis" and gratis["taxa_centavos"] == 0
    taxa = calcular_condicoes(valor=49999, forma="boleto", cidade="campo grande").dados["frete"]
    assert taxa["situacao"] == "taxa" and taxa["taxa_centavos"] == 3500
    exato = calcular_condicoes(valor=50000, forma="boleto", cidade="Campo Grande").dados["frete"]
    assert exato["situacao"] == "gratis" and exato["taxa_centavos"] == 0  # decisão do Rodrigo: R$ 500,00 inclusive
    centavo = calcular_condicoes(valor=49999, forma="boleto", cidade="Campo Grande").dados["frete"]
    assert centavo["situacao"] == "taxa" and centavo["taxa_centavos"] == 3500


def test_frete_outra_cidade_pede_cotacao_e_valor_pedido_manda_na_base():
    outra = calcular_condicoes(valor=90000, forma="boleto", cidade="Dourados").dados["frete"]
    assert outra["situacao"] == "cotacao_necessaria"
    base = calcular_condicoes(valor=10000, forma="boleto", cidade="Campo Grande", valor_pedido=80000).dados["frete"]
    assert base["situacao"] == "gratis"


def test_vazio_para_produto_inexistente():
    r = calcular_condicoes(produto_id=99999, forma="pix")
    assert r.estado == "vazio"


def test_ambiguo_com_duas_promocoes_ativas(sql):
    sql.execute("INSERT INTO promocoes VALUES (100, 90, 5, 'Duplicada', 1)")
    sql.commit()
    r = calcular_condicoes(produto_id=90, forma="pix")
    assert r.estado == "ambiguo" and r.dados["promocoes_ativas"] == [19, 100]


def test_promocao_inativa_nunca_vale_mesmo_com_nome_de_campanha(sql):
    sql.execute("UPDATE promocoes SET ativa = 0 WHERE produto_id = 90")
    sql.commit()
    d = calcular_condicoes(produto_id=90, forma="pix").dados
    assert d["percentual"] is None and d["final_centavos"] == 227905


def test_falhas_de_entrada():
    assert calcular_condicoes(forma="pix").motivo == "entrada_invalida"
    assert calcular_condicoes(produto_id=90, valor=1000, forma="pix").motivo == "entrada_invalida"
    assert calcular_condicoes(produto_id=90, forma="pix", parcelas=3).motivo == "entrada_invalida"
    assert calcular_condicoes(produto_id=90, forma="credito", parcelas=13).motivo == "entrada_invalida"
    assert calcular_condicoes(produto_id=90, forma="cheque").estado == "falha"
    assert calcular_condicoes(valor=100.5, forma="pix").estado == "falha"
    assert calcular_condicoes(valor=0, forma="pix").estado == "falha"


def test_nunca_negado():
    assert calcular_condicoes(valor=100, forma="credito", parcelas=12).estado == "ok"
