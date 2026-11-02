"""Perguntas frequentes, políticas e privacidade, montadas a partir do manual (`fato()` e `consultar_politica`).

O texto aqui é só a moldura das frases; todo valor (prazo, percentual, preço, horário) vem do manual. Onde o manual
tem ambiguidade registrada, a resposta diz o que vale e oferece contato (`DUVIDA`), sem escolher um lado em silêncio.
"""
from __future__ import annotations

import re
from typing import Any

from .. import dinheiro
from ..ferramentas.politica import consultar_politica
from ..politicas.manual import carregar_manual, fato
from . import apresentacao

DUVIDA = "Se tiver dúvida no seu caso, fale com a gente."


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


def _lista(itens: list[str]) -> str:
    """"a, b e c", em português."""
    itens = [str(i) for i in itens]
    if len(itens) < 2:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def _nome_da_modalidade(nome: str) -> str:
    return re.sub(r"\s*\(\.[a-z]+\)", "", nome)  # tira o nome interno do serviço da transportadora, entre parênteses


def _pagamento() -> str:
    partes = [f"Aceitamos {apresentacao.formas_de_pagamento()}."]
    pix = _v("pagamento.pix_desconto_percentual")
    if pix:
        partes.append(f"No PIX você tem {pix}% de desconto sobre o preço de tabela, mas o desconto não soma com preço promocional.")
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
        detalhes.append(f"{rotulo}, parcela mínima de {dinheiro.formatar(f['parcela_minima_centavos'])}")
    texto = f"Sim, no cartão de crédito em até {maximo}x sem juros." if maximo else "Sim, no cartão de crédito."
    if detalhes:
        texto += " O valor mínimo da parcela depende do número de vezes: " + "; ".join(detalhes) + "."
    return texto + " " + DUVIDA


def _pix() -> str:
    pix = _v("pagamento.pix_desconto_percentual")
    return (f"O PIX tem {pix}% de desconto sobre o preço de tabela. Em produto que já está em promoção, "
            "vale o preço promocional e o desconto do PIX não se soma.") if pix else ""


def _frete() -> str:
    cidade = _v("frete.cidade_base", "")
    grande = _lista(_v("frete.grande_porte_cotacao_individual") or [])
    return (f"Em {cidade}, o frete é grátis a partir de {_brl('frete.gratis_acima_centavos')}; abaixo disso, a taxa é de "
            f"{_brl('frete.taxa_abaixo_centavos')}. "
            "Para as outras cidades, ao finalizar o pedido você vê o frete estimado pelo CEP de destino, pelo peso e pelas "
            "dimensões. Essa estimativa é uma simulação e não a tarifa de uma transportadora."
            + (f" Instrumentos de grande porte ({grande}) têm cotação individual." if grande else ""))


def _prazo() -> str:
    cidade = _v("frete.cidade_base", "")
    texto = f"Em {cidade}, entregamos em {_faixa('frete.prazo_dias_uteis')} dias úteis."
    mods = [f"{_nome_da_modalidade(m['nome'])}, de {m['prazo_dias_uteis']['min']} a {m['prazo_dias_uteis']['max']} dias úteis"
            for m in _v("frete.outras_cidades_modalidades") or []]
    if mods:
        texto += " Para as outras cidades, o prazo depende da modalidade: " + "; ".join(mods) + "."
    return texto


def _avaria() -> str:
    mods = _v("frete.outras_cidades_modalidades") or []
    seguro = " Todos os envios para outras cidades têm seguro contra extravio e danos no transporte." if mods and all(
        m.get("seguro") for m in mods) else ""
    recusar = "recuse o recebimento e " if _v("frete.avaria_recusar_recebimento") else ""
    return (f"Se o produto chegar danificado, {recusar}fale com a gente na hora.{seguro} "
            "Quanto antes você avisar, mais rápido resolvemos.")


def _rastreio() -> str:
    return ("Use Rastrear pedido, no topo do site, com o número do pedido e os 4 últimos dígitos do telefone. "
            "Se o pedido foi feito aqui no site, o número começa com PED-: informe só o número, sem o telefone. "
            "Ele abre no mesmo navegador em que o pedido foi feito.")


def _codigo_rastreio() -> str:
    envio = " e ".join(_v("rastreamento.enviado_por") or [])
    consulta = _lista([_nome_da_modalidade(c) for c in _v("rastreamento.consulta_em") or []])
    return (f"Quando o pedido é despachado, enviamos o código de rastreamento por {envio}."
            + (f" Com o código, você acompanha a entrega no site dos {consulta}." if consulta else ""))


def _troca() -> str:
    a = _v("regra.arrependimento") or {}
    p = _v("regra.preferencia") or {}
    return (f"Compras online podem ser devolvidas em até {a.get('prazo_dias')} dias {a.get('tipo_dias')} após o recebimento, "
            f"com o produto na embalagem original. Também trocamos por preferência (cor, modelo ou tamanho) em até "
            f"{p.get('prazo_dias')} dias, conforme a disponibilidade do produto que você quer. {DUVIDA}")


def _devolucao() -> str:
    a = _v("regra.arrependimento") or {}
    frete = " O frete da devolução é por nossa conta." if _v("devolucao.arrependimento_frete_por_conta_da_loja") else ""
    return (f"Fale com a gente em até {a.get('prazo_dias')} dias {a.get('tipo_dias')} após receber o produto; você não precisa "
            f"explicar o motivo. O instrumento deve estar sem sinais de uso e com embalagem original, acessórios e manuais.{frete}")


def _reembolso() -> str:
    dias = _v("devolucao.arrependimento_reembolso_dias_uteis_max")
    a = _v("regra.arrependimento") or {}
    return (f"O dinheiro volta na mesma forma de pagamento que você usou, em até {dias} dias úteis. "
            f"Isso vale para devolução feita em até {a.get('prazo_dias')} dias {a.get('tipo_dias')} após o recebimento, "
            "dentro das condições da devolução. " + DUVIDA)


def _defeito() -> str:
    d = _v("regra.defeito") or {}
    return (f"Trocamos o produto com defeito de fabricação em até {d.get('prazo_dias')} dias {d.get('tipo_dias')} após a compra. "
            "Depois desse prazo, a garantia é com o fabricante, e podemos ajudar a falar com ele se você pedir. "
            "Dano por mau uso, queda ou umidade excessiva não é coberto. " + DUVIDA)


def _garantia() -> str:
    g = _v("regra.garantia_legal") or {}
    fab = _v("garantia.fabricante_prazo_meses") or {}
    return (f"Todos os produtos têm garantia legal de {g.get('prazo_dias')} dias contra defeito de fabricação, contados do recebimento. "
            f"Além dela, muitos fabricantes dão garantia própria, de {fab.get('min')} meses a {int(fab.get('max', 0)) // 12} anos; "
            "o certificado vem junto do produto.")


def _horario() -> str:
    return ("Atendemos " + "; ".join(h[0].lower() + h[1:] for h in apresentacao.loja()["horario"])
            + ". Em datas especiais o horário pode ser estendido, e feriados podem mudar o atendimento.")


def _acessorios() -> str:
    nao = _lista(_v("escopo.acessorios_nao_vendidos") or [])
    mais = _v("empresa.catalogo_instrumentos_mais_de")
    return ("Não, trabalhamos só com instrumentos musicais" + (f": não vendemos {nao}." if nao else ".")
            + (f" Nosso catálogo tem mais de {mais} instrumentos." if mais else ""))


def _privacidade() -> str:
    nao_compartilha = " Não compartilhamos seus dados com terceiros para marketing." if _v("privacidade.compartilha_para_marketing") is False else ""
    exclusao = " Você pode pedir a exclusão dos seus dados quando quiser, pelo WhatsApp ou por e-mail." if _v(
        "privacidade.exclusao_a_pedido_do_cliente") else ""
    return ("Usamos seus dados só para processar e entregar pedidos, avisar sobre o andamento, enviar promoções se você autorizar "
            "e cumprir obrigações legais." + nao_compartilha + exclusao)


TROCAS = "Trocas, devoluções e garantia"
# (tema, pergunta, função, é das principais da homepage)
FAQ = (
    ("Pagamento", "Quais formas de pagamento vocês aceitam?", _pagamento, True),
    ("Pagamento", "Posso parcelar a compra?", _parcelamento, False),
    ("Pagamento", "Como funciona o desconto do PIX?", _pix, False),
    ("Entrega e frete", "Como é o frete?", _frete, True),
    ("Entrega e frete", "Qual o prazo de entrega?", _prazo, False),
    ("Entrega e frete", "E se o produto chegar danificado?", _avaria, False),
    ("Pedido e rastreio", "Como acompanho meu pedido?", _rastreio, True),
    ("Pedido e rastreio", "Como recebo o código de rastreamento?", _codigo_rastreio, False),
    (TROCAS, "Como funcionam as trocas?", _troca, True),
    (TROCAS, "Como faço uma devolução?", _devolucao, False),
    (TROCAS, "Como recebo o reembolso?", _reembolso, False),
    (TROCAS, "E se o instrumento chegar com defeito?", _defeito, False),
    (TROCAS, "Qual é a garantia?", _garantia, False),
    ("Sobre a loja", "Qual o horário de atendimento?", _horario, False),
    ("Sobre a loja", "Vocês vendem acessórios, como cordas e cabos?", _acessorios, False),
    ("Sobre a loja", "O que vocês fazem com os meus dados?", _privacidade, False),
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


def nota_do_tema(ancora: str) -> str:
    """Nota escrita pelo site (não é texto do manual) sob um tema das políticas."""
    if ancora != "entrega":
        return ""
    cidade = _v("frete.cidade_base", "")
    return (f"Frete grátis e taxa fixa valem somente em {cidade}. As demais cidades seguem o frete estimado "
            "(simulação) da finalização do pedido, calculado pelo CEP, peso e dimensões, sem ser a tarifa de uma transportadora.")


# Linhas do manual que são instrução para a equipe, não regra para o cliente. Saem só da exibição; o manual não muda.
LINHAS_INTERNAS = ("Comunicação:",)


def _sem_instrucao_interna(texto: str) -> str:
    return "\n".join(l for l in texto.splitlines() if not l.strip().startswith(LINHAS_INTERNAS))


def politicas() -> list[dict[str, Any]]:
    r = consultar_politica(temas=sorted(carregar_manual().temas_conhecidos()))
    if r.estado != "ok":
        return []
    por_id = {s["id"]: s for s in r.dados["secoes"] if s["publico"]}
    saida = []
    for ancora, titulo, ids in TEMAS_POLITICAS:
        secoes = [{**por_id[i], "texto": _sem_instrucao_interna(por_id[i]["texto"])}
                  for i in ids if i in por_id and por_id[i]["texto"]]
        if secoes:
            saida.append({"ancora": ancora, "titulo": titulo, "secoes": secoes, "nota": nota_do_tema(ancora)})
    return saida


def privacidade_manual() -> str:
    """Texto da seção de privacidade e proteção de dados, como o manual traz."""
    r = consultar_politica(temas=["privacidade"])
    if r.estado != "ok":
        return ""
    return "\n".join(s["texto"] for s in r.dados["secoes"] if s["publico"] and s["texto"])
