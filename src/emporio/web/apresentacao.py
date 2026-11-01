"""Apresentação: transforma o que as ferramentas devolveram em dados para os templates.

Nada aqui calcula preço ou aplica regra. Valores de loja são lidos do manual por `fato()`.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from markupsafe import Markup, escape

from .. import dinheiro
from ..politicas.manual import fato

NOMES_DIA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

ROTULO_SITUACAO = {
    "disponivel": "Disponível",
    "esgotado": "Esgotado",
    "descontinuado": "Descontinuado",
    "em_breve": "Em breve",
}
ROTULO_STATUS_PEDIDO = {
    "pending": "Aguardando pagamento",
    "confirmed": "Confirmado",
    "shipped": "Enviado",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}
ROTULO_PAGAMENTO = {"pix": "PIX", "debit": "Débito", "boleto": "Boleto"}
ROTULO_FORMA = {"pix": "PIX", "debito": "Débito", "boleto": "Boleto", "credito": "Cartão de crédito"}


def brl(centavos: int | None) -> str:
    return "" if centavos is None else dinheiro.formatar(int(centavos))


def data_br(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def forma_pagamento(codigo: str | None) -> str:
    if not codigo:
        return ""
    if codigo in ROTULO_PAGAMENTO:
        return ROTULO_PAGAMENTO[codigo]
    if codigo.startswith("credit_"):
        return f"Crédito em {codigo.removeprefix('credit_').removesuffix('x')}x"
    return codigo


def quebras(texto: str | None) -> Markup:
    """Escapa o texto e troca quebras de linha por <br>."""
    return Markup(str(escape(texto or "")).replace("\r\n", "\n").replace("\n", "<br>\n"))


def _faixas_horario(regras: list[dict[str, Any]]) -> list[str]:
    linhas = []
    for r in regras:
        dias = sorted(r["dias"])
        nome = NOMES_DIA[dias[0]] if len(dias) == 1 else f"{NOMES_DIA[dias[0]]} a {NOMES_DIA[dias[-1]]}"
        if r.get("fechado"):
            linhas.append(f"{nome}: fechado")
        else:
            linhas.append(f"{nome}: {r['abre']} às {r['fecha']}")
    return linhas


# Mesmas chaves e origens que o agente mostra em respostas.contato; o manual traz mais de um valor e
# nenhum é escolhido em silêncio.
CONTATOS = (
    ("contato.telefone_whatsapp_dados_empresa", "telefone e WhatsApp nos dados da empresa"),
    ("contato.whatsapp_secao_7", "canal de WhatsApp para atendimento remoto"),
    ("contato.telefone_capa", "telefone na capa do manual"),
    ("contato.email_capa", "grafia da capa do manual"),
    ("contato.email_dados_empresa", "grafia dos dados da empresa"),
)


def contatos() -> list[dict[str, str]]:
    """Cada contato do manual com a origem; valores iguais em chaves diferentes juntam as origens."""
    por_valor: dict[str, list[str]] = {}
    for chave, onde in CONTATOS:
        f = fato(chave)
        if f:
            por_valor.setdefault(str(f.valor), []).append(onde)
    return [{"valor": v, "origem": ", ".join(o)} for v, o in por_valor.items()]


def loja() -> dict[str, Any]:
    """Nome, endereço, contato e horário, todos do manual."""
    info: dict[str, Any] = {"nome": "", "endereco": "", "contatos": [], "horario": []}
    f = fato("empresa.nome_fantasia")
    if f:
        info["nome"] = f.valor
    f = fato("empresa.endereco")
    if f and isinstance(f.valor, dict):
        e = f.valor
        info["endereco"] = (f"{e['logradouro']}, {e['numero']}, {e['bairro']}, {e['cidade']}/{e['uf']}, "
                            f"CEP {e['cep']}")
    info["contatos"] = contatos()
    f = fato("horario.funcionamento")
    if f and isinstance(f.valor, list):
        info["horario"] = _faixas_horario(f.valor)
    return info


def preparar_item(item: dict[str, Any], promos: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Item de busca ou de ver_produto como a ferramenta devolveu, com a promoção ligada ao preço final.

    O preço final vem de listar_promocoes; aqui só se escolhe o que mostrar.
    """
    situacao = item["situacao_venda"]
    promo = item.get("promocao")
    saida: dict[str, Any] = {
        "id": item["id"], "nome": item["nome"], "original": item["preco_centavos"], "situacao": situacao,
        "rotulo": ROTULO_SITUACAO.get(situacao, situacao), "pode_comprar": situacao == "disponivel",
        "percentual": None, "final": None, "descricao_promocao": None, "promocao_em_conferencia": False,
    }
    if promo:
        ref = promos.get(item["id"])
        if promo.get("ambigua") or ref is None or ref.get("conflito") or ref.get("final_centavos") is None:
            saida["promocao_em_conferencia"] = True
        else:
            saida.update(percentual=ref["percentual"], final=ref["final_centavos"],
                         descricao_promocao=ref["descricao"])
    return saida
