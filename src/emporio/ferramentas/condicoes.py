"""calcular_condicoes: preço final, parcelamento e frete. Os valores das regras vêm do YAML."""
from __future__ import annotations

from typing import Any, Literal

from .. import dinheiro
from ..dados import banco
from ..politicas import manual
from ..texto import normalizar
from .envelope import EntradaBase, Fonte, Resultado, ferramenta, resultado
from .produtos import FONTE_BANCO, promocoes_ativas, situacao_venda


class EntradaCondicoes(EntradaBase):
    produto_id: int | None = None
    valor: int | None = None  # centavos, quando não há produto
    forma: Literal["pix", "debito", "credito", "boleto"]
    parcelas: int = 1
    cidade: str | None = None
    valor_pedido: int | None = None  # centavos, base do frete


def _fonte_manual(chave: str) -> Fonte:
    achado = manual.carregar_manual().condicao(chave)
    if achado is None:
        raise KeyError(f"manual sem a chave {chave}")
    return manual.fonte_da_secao(achado[0])


def _faixa(parcelas: int) -> int:
    for faixa in manual.valor("pagamento.parcelamento_faixas"):
        if faixa["de"] <= parcelas <= faixa["ate"]:
            return faixa["parcela_minima_centavos"]
    raise KeyError("faixa de parcelamento ausente no manual")


def _frete(cidade: str, base: int, fontes: list[Fonte]) -> dict[str, Any]:
    fontes.append(_fonte_manual("frete.gratis_acima_centavos"))
    if normalizar(cidade) != normalizar(manual.valor("frete.cidade_base")):
        return {"situacao": "cotacao_necessaria", "taxa_centavos": None}
    limite = manual.valor("frete.gratis_acima_centavos")
    prazo = manual.valor("frete.prazo_dias_uteis")
    # decisão da loja (01/11/2026) para a ambiguidade frete_exatamente_500: o limite é inclusivo
    if base >= limite:
        return {"situacao": "gratis", "taxa_centavos": 0, "prazo_dias_uteis": prazo}
    return {"situacao": "taxa", "taxa_centavos": manual.valor("frete.taxa_abaixo_centavos"),
            "prazo_dias_uteis": prazo}


@ferramenta(EntradaCondicoes)
def calcular_condicoes(e: EntradaCondicoes) -> Resultado:
    if (e.produto_id is None) == (e.valor is None):
        return resultado("falha", motivo="entrada_invalida")
    if (e.valor is not None and e.valor <= 0) or (e.valor_pedido is not None and e.valor_pedido <= 0):
        return resultado("falha", motivo="entrada_invalida")
    parcelas_max = manual.valor("pagamento.credito_parcelas_max")
    if e.parcelas < 1 or e.parcelas > parcelas_max or (e.parcelas > 1 and e.forma != "credito"):
        return resultado("falha", motivo="entrada_invalida")

    fontes: list[Fonte] = []
    dados: dict[str, Any] = {"forma": e.forma, "parcelas": e.parcelas}
    promo = None
    if e.produto_id is not None:
        conn = banco.conectar()
        try:
            produto = conn.execute("SELECT * FROM produtos WHERE id = ?", (e.produto_id,)).fetchone()
            if produto is None:
                return resultado("vazio", fontes=[FONTE_BANCO], motivo="produto_nao_encontrado")
            ativas = promocoes_ativas(conn, e.produto_id)
        finally:
            conn.close()
        if len(ativas) > 1:
            return resultado("ambiguo", {"produto_id": e.produto_id, "promocoes_ativas": [a["id"] for a in ativas]},
                             [FONTE_BANCO], "promocoes_ativas_em_conflito")
        promo = ativas[0] if ativas else None
        original = produto["preco_centavos"]
        dados.update({"produto_id": produto["id"], "produto_nome": produto["nome"],
                      "situacao_venda": situacao_venda(produto["status"], produto["estoque"])})
        fontes.append(FONTE_BANCO)
    else:
        original = e.valor

    if promo is not None:
        final = dinheiro.aplicar_desconto(original, promo["percentual"])
        dados.update({"percentual": promo["percentual"], "promocao_id": promo["id"], "pix_aplicado": False})
        fontes.append(_fonte_manual("promocoes.pix_sobre_preco_promocional"))
    else:
        dados.update({"percentual": None, "promocao_id": None})
        if e.forma == "pix":
            pix = manual.valor("pagamento.pix_desconto_percentual")
            final = dinheiro.aplicar_desconto(original, pix)
            dados.update({"pix_aplicado": True, "pix_percentual": pix})
            fontes.append(_fonte_manual("pagamento.pix_desconto_percentual"))
        else:
            final = original
            dados["pix_aplicado"] = False
    dados.update({"original_centavos": original, "final_centavos": final})

    permitido = "sim"
    if e.forma == "credito":
        parcela = dinheiro.dividir(final, e.parcelas)
        minimo_tabela = manual.valor("pagamento.credito_parcela_minima_tabela_centavos")
        minimo_faixa = _faixa(e.parcelas)
        # parcela única é pagamento à vista: as duas leituras só pesam ao parcelar
        tabela = e.parcelas == 1 or parcela >= minimo_tabela
        faixas = e.parcelas == 1 or parcela >= minimo_faixa
        permitido = "sim" if tabela and faixas else "nao" if not tabela and not faixas else "requer_confirmacao"
        dados.update({"parcela_centavos": parcela, "leitura_tabela": tabela, "leitura_faixas": faixas,
                      "minimo_tabela_centavos": minimo_tabela, "minimo_faixa_centavos": minimo_faixa})
        fontes += [_fonte_manual("pagamento.credito_parcela_minima_tabela_centavos"),
                   _fonte_manual("pagamento.parcelamento_faixas")]
    dados["permitido"] = permitido

    if e.cidade is not None:
        base = e.valor_pedido if e.valor_pedido is not None else final
        dados["frete"] = _frete(e.cidade, base, fontes)
    return resultado("ok", dados, fontes)
