"""Apresentação: transforma o que as ferramentas devolveram em dados para os templates.

Nada aqui calcula preço ou aplica regra. Valores de loja são lidos do manual por `fato()`.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from markupsafe import Markup, escape

from .. import config, dinheiro
from ..agente import expediente
from ..politicas.manual import fato
from ..texto import tokens

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
    info: dict[str, Any] = {"nome": "", "endereco": "", "endereco_curto": "", "endereco_resumido": "", "contatos": [], "horario": []}
    f = fato("empresa.nome_fantasia")
    if f:
        info["nome"] = f.valor
    f = fato("empresa.endereco")
    if f and isinstance(f.valor, dict):
        e = f.valor
        info["endereco"] = (f"{e['logradouro']}, {e['numero']}, {e['bairro']}, {e['cidade']}/{e['uf']}, "
                            f"CEP {e['cep']}")
        info["endereco_resumido"] = f"{e['logradouro']}, {e['numero']}, {e['cidade']}/{e['uf']}"
        info["endereco_curto"] = f"{e['logradouro']}, {e['numero']}, {e['bairro']}, {e['cidade']}/{e['uf']}"
    todos = {c["valor"]: c for c in contatos()}
    # a mesma fonte da Lia, da faixa e do /fale-conosco: telefone e e-mail da capa; a ressalva das variantes do
    # manual fica em /politicas e no README, não em toda resposta
    info["contatos"] = [{"valor": str(f.valor)} for chave in ("contato.telefone_capa", "contato.email_capa")
                        if (f := fato(chave)) is not None and str(f.valor) in todos]
    info["contato_nota"] = "O manual traz outros canais; se não conseguir contato, fale com a Lia."
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


# ---- identidade visual: ilustração por categoria -------------------------------------------------

ILUSTRACOES_SVG = Path(__file__).resolve().parent / "static" / "ilustracoes.svg"
ILUSTRACAO_PADRAO = "instrumento"


def _ids_de_ilustracao() -> frozenset[str]:
    try:
        return frozenset(re.findall(r'<symbol id="([a-z0-9-]+)"', ILUSTRACOES_SVG.read_text(encoding="utf-8")))
    except OSError:
        return frozenset()


IDS_ILUSTRACAO = _ids_de_ilustracao()


def ilustracao(categoria: str | None) -> str:
    """Id do símbolo SVG da categoria (o nome da categoria vem do banco); sem desenho próprio, o genérico."""
    ident = "-".join(tokens(categoria or ""))
    return ident if ident in IDS_ILUSTRACAO else ILUSTRACAO_PADRAO


# ---- faixa de expediente --------------------------------------------------------------------------

def _faixa_de_hoje(funcionamento: list[dict[str, Any]], dia: int) -> dict[str, str] | None:
    for r in funcionamento:
        if dia in r["dias"] and not r.get("fechado"):
            return {"abre": r["abre"], "fecha": r["fecha"]}
    return None


def situacao_loja() -> dict[str, Any]:
    """Aberta ou fechada agora, no fuso da loja e com a data de referência, só a partir de horario.funcionamento."""
    f = fato("horario.funcionamento")
    if not f or not isinstance(f.valor, list):
        return {"conhecida": False, "aberto": False, "hoje": None, "retorno": None}
    agora = config.agora()
    sit = expediente.situacao(f.valor, agora)
    hoje = _faixa_de_hoje(f.valor, agora.weekday())
    return {"conhecida": True, "aberto": sit["aberto"], "hoje": hoje, "retorno": sit["retorno"]}


def formas_de_pagamento() -> str:
    """Formas de pagamento em texto corrido, montadas dos fatos do manual."""
    partes = []
    if fato("pagamento.pix_desconto_percentual"):
        partes.append("PIX")
    if fato("pagamento.debito_a_vista"):
        partes.append("cartão de débito")
    f = fato("pagamento.credito_parcelas_max")
    if f:
        sj = fato("pagamento.credito_sem_juros")
        partes.append(f"cartão de crédito em até {f.valor}x" + (" sem juros" if sj and sj.valor else ""))
    if fato("pagamento.boleto_a_vista"):
        partes.append("boleto bancário")
    return ", ".join(partes)


# ---- cores dos tokens do CSS (manifest e meta theme-color usam as mesmas) ---------------------------

CSS_SITE = Path(__file__).resolve().parent / "static" / "site.css"


def cores() -> dict[str, str]:
    """Tokens de cor de :root em site.css, para o manifest e o theme-color não repetirem hexadecimais."""
    try:
        css = CSS_SITE.read_text(encoding="utf-8")
    except OSError:
        return {}
    return {nome.replace("-", "_"): valor for nome, valor in re.findall(r"--([a-z-]+):\s*(#[0-9A-Fa-f]{6})", css)}
