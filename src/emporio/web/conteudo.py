"""Perguntas frequentes, políticas e privacidade, montadas a partir do manual (`fato()` e `consultar_politica`).

O texto aqui é só a moldura das frases; todo valor (prazo, percentual, preço, horário) vem do manual. Onde o manual
tem ambiguidade registrada, a resposta diz que a nossa equipe confirma, sem escolher um lado em silêncio.
"""
from __future__ import annotations

from typing import Any

from .. import dinheiro
from ..ferramentas.politica import consultar_politica
from ..politicas.manual import carregar_manual, fato
from . import apresentacao

CONFIRMAR = "Esse caso precisa de confirmação da nossa equipe."


def _v(chave: str, padrao: Any = None) -> Any:
    f = fato(chave)
    return f.valor if f else padrao


def _brl(chave: str) -> str:
    c = _v(chave)
    return dinheiro.formatar(int(c)) if c is not None else ""


def _faixa(chave: str) -> str:
    v = _v(chave)
    if isinstance(v, dict):
        return f"{v['min']} a {v['max']}" if v["min"] != v["max"] else str(v["min"])
    return str(v) if v is not None else ""


def _pagamento() -> str:
    partes = [f"Aceitamos {apresentacao.formas_de_pagamento()}."]
    pix = _v("pagamento.pix_desconto_percentual")
    if pix:
        partes.append(f"No PIX há {pix}% de desconto sobre o preço de tabela; o desconto do PIX não soma com preço promocional.")
    dias = _v("pagamento.boleto_compensacao_dias_uteis_max")
    if dias:
        partes.append(f"O boleto compensa em até {dias} dias úteis.")
    return " ".join(partes)


def _parcelamento() -> str:
    maximo = _v("pagamento.credito_parcelas_max")
    faixas = _v("pagamento.parcelamento_faixas") or []
    detalhes = []
    for f in faixas:
        de, ate = f["de"], f["ate"]
        rotulo = f"em até {ate}x" if de == 1 else f"de {de} a {ate}x"
        detalhes.append(f"{rotulo}, parcela de pelo menos {dinheiro.formatar(f['parcela_minima_centavos'])}")
    texto = f"No cartão de crédito, em até {maximo}x sem juros." if maximo else ""
    if detalhes:
        texto += " Valor mínimo da parcela: " + "; ".join(detalhes) + "."
    return texto + " Se a parcela ficar perto do mínimo, a nossa equipe confirma o parcelamento."


def _pix() -> str:
    pix = _v("pagamento.pix_desconto_percentual")
    return (f"O PIX tem {pix}% de desconto sobre o preço de tabela. Em produto que já está em promoção, "
            "vale o preço promocional e o desconto do PIX não se soma.") if pix else ""


def _frete() -> str:
    cidade = _v("frete.cidade_base", "")
    return (f"Em {cidade}: frete grátis acima de {_brl('frete.gratis_acima_centavos')} e taxa de "
            f"{_brl('frete.taxa_abaixo_centavos')} abaixo disso. Para pedido de exatamente "
            f"{_brl('frete.gratis_acima_centavos')}, {CONFIRMAR[0].lower()}{CONFIRMAR[1:]} "
            "Para outras cidades, o frete é calculado pelo CEP de destino, peso e dimensões, "
            "e instrumentos de grande porte podem ter cotação individual.")


def _prazo() -> str:
    cidade = _v("frete.cidade_base", "")
    texto = f"Em {cidade}: {_faixa('frete.prazo_dias_uteis')} dias úteis."
    for m in _v("frete.outras_cidades_modalidades") or []:
        d = m["prazo_dias_uteis"]
        texto += f" {m['nome']}: {d['min']} a {d['max']} dias úteis."
    return texto


def _rastreio() -> str:
    envio = " e ".join(_v("rastreamento.enviado_por") or [])
    return (f"Quando o pedido é despachado, o código de rastreamento chega por {envio}. "
            "Você também pode consultar o andamento em Rastrear pedido, com o número do pedido e os 4 últimos "
            "dígitos do telefone.")


def _troca() -> str:
    a = _v("regra.arrependimento") or {}
    p = _v("regra.preferencia") or {}
    return (f"Compra online: devolução em até {a.get('prazo_dias')} dias {a.get('tipo_dias')} após o recebimento, "
            f"com o produto na embalagem original. Troca por preferência: em até {p.get('prazo_dias')} dias, "
            f"conforme a disponibilidade do produto desejado; {CONFIRMAR[0].lower()}{CONFIRMAR[1:]}")


def _devolucao() -> str:
    a = _v("regra.arrependimento") or {}
    dias = _v("devolucao.arrependimento_reembolso_dias_uteis_max")
    frete = "O frete da devolução por arrependimento é por conta da loja. " if _v(
        "devolucao.arrependimento_frete_por_conta_da_loja") else ""
    return (f"Você pode devolver em até {a.get('prazo_dias')} dias {a.get('tipo_dias')} após receber, sem precisar "
            f"explicar o motivo, com o produto sem sinais de uso e com acessórios e manuais. {frete}"
            f"O reembolso volta pela mesma forma de pagamento em até {dias} dias úteis.")


def _defeito() -> str:
    d = _v("regra.defeito") or {}
    return (f"Defeito de fabricação: troca em até {d.get('prazo_dias')} dias {d.get('tipo_dias')} após a compra. "
            "Depois desse prazo, a garantia é acionada com o fabricante, e podemos intermediar se você pedir. "
            f"Como se combinam esse prazo e a garantia legal, {CONFIRMAR[0].lower()}{CONFIRMAR[1:]}")


def _garantia() -> str:
    g = _v("regra.garantia_legal") or {}
    fab = _v("garantia.fabricante_prazo_meses") or {}
    return (f"Garantia legal de {g.get('prazo_dias')} dias contra defeito de fabricação, contada do recebimento. "
            f"Muitos fabricantes dão garantia própria, de {fab.get('min')} meses a {int(fab.get('max', 0)) // 12} anos; "
            "o certificado acompanha o produto.")


def _horario() -> str:
    return "; ".join(apresentacao.loja()["horario"]) + ". Em datas especiais o horário pode ser estendido, e feriados podem alterar o atendimento."


# (tema, pergunta, função, é das principais da homepage)
FAQ = (
    ("Pagamento", "Quais formas de pagamento vocês aceitam?", _pagamento, True),
    ("Pagamento", "Posso parcelar a compra?", _parcelamento, False),
    ("Pagamento", "Como funciona o desconto do PIX?", _pix, False),
    ("Entrega", "Como é o frete?", _frete, True),
    ("Entrega", "Qual o prazo de entrega?", _prazo, False),
    ("Entrega", "Como acompanho meu pedido?", _rastreio, True),
    ("Trocas e garantia", "Como funcionam as trocas?", _troca, True),
    ("Trocas e garantia", "Como faço uma devolução?", _devolucao, False),
    ("Trocas e garantia", "E se o instrumento chegar com defeito?", _defeito, False),
    ("Trocas e garantia", "Qual é a garantia?", _garantia, False),
    ("Loja", "Qual o horário de atendimento?", _horario, False),
)


def perguntas(somente_principais: bool = False) -> list[dict[str, str]]:
    return [{"tema": t, "pergunta": q, "resposta": f()} for t, q, f, p in FAQ if p or not somente_principais]


def faq_agrupada() -> list[dict[str, Any]]:
    grupos: dict[str, list[dict[str, str]]] = {}
    for item in perguntas():
        grupos.setdefault(item["tema"], []).append(item)
    return [{"tema": t, "itens": i} for t, i in grupos.items()]


# ---- políticas: um tema por âncora --------------------------------------------------------------

TEMAS_POLITICAS = (
    ("pagamento", "Pagamento", ("3", "3.1")),
    ("entrega", "Frete e entrega", ("5", "5.1", "5.2", "5.3")),
    ("trocas", "Trocas e devoluções", ("4", "4.1", "4.2", "4.3", "4.4")),
    ("promocoes", "Promoções", ("6.1", "6.2")),
    ("garantia", "Garantia", ("8", "8.1", "8.2", "8.3")),
)


def politicas() -> list[dict[str, Any]]:
    r = consultar_politica(temas=sorted(carregar_manual().temas_conhecidos()))
    if r.estado != "ok":
        return []
    por_id = {s["id"]: s for s in r.dados["secoes"] if s["publico"]}
    saida = []
    for ancora, titulo, ids in TEMAS_POLITICAS:
        secoes = [por_id[i] for i in ids if i in por_id and por_id[i]["texto"]]
        if secoes:
            saida.append({"ancora": ancora, "titulo": titulo, "secoes": secoes})
    return saida


def privacidade_manual() -> str:
    """Texto da seção de privacidade e proteção de dados, como o manual traz."""
    r = consultar_politica(temas=["privacidade"])
    if r.estado != "ok":
        return ""
    return "\n".join(s["texto"] for s in r.dados["secoes"] if s["publico"] and s["texto"])
