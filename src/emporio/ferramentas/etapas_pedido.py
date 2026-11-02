"""Etapas do pedido no padrão de mercado: uma só função para o rastreio, a confirmação do pedido e a Lia.

Etapas: Pedido recebido, Pagamento confirmado, Em separação, Enviado, Entregue; Cancelado como desvio.
Nada é chamado fora do processo: o horário do pedido do site vem da gravação e o relógio é `config.agora()`.
Não inventa evento: dados do CSV não trazem data por etapa, então só aparecem a data do pedido, o código de
rastreio, a previsão de entrega e a observação do pedido cancelado.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .. import config
from ..politicas.manual import fato

STATUS_SITE = "PED-"  # pedido feito no site (número PED-...): a etapa vem da forma de pagamento e do horário
ANALISE_MINUTOS = 5  # aprovação simulada do cartão de crédito

FEITA, ATUAL, PENDENTE = "feita", "atual", "pendente"
ROTULO_ESTADO = {FEITA: "concluída", ATUAL: "etapa atual", PENDENTE: "a seguir"}

RECEBIDO, PAGAMENTO, SEPARACAO, ENVIADO, ENTREGUE, CANCELADO = (
    "Pedido recebido", "Pagamento confirmado", "Em separação", "Enviado", "Entregue", "Cancelado")
EM_ANALISE, AGUARDANDO = "Pagamento em análise", "Aguardando pagamento"
_DEPOIS = (SEPARACAO, ENVIADO, ENTREGUE)  # etapas depois do pagamento; a atual de cada status do CSV é um índice
_ATUAL_CSV = {"confirmed": 0, "shipped": 1, "delivered": 2}


@dataclass(frozen=True)
class Etapa:
    rotulo: str
    estado: str  # feita | atual | pendente
    detalhe: str = ""

    @property
    def estado_texto(self) -> str:
        return ROTULO_ESTADO[self.estado]


def _data_br(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _instante(criado_em: str | None) -> datetime | None:
    if not criado_em:
        return None
    try:
        dt = datetime.fromisoformat(criado_em)
    except ValueError:
        return None
    return dt.replace(tzinfo=config.fuso()) if dt.tzinfo is None else dt


def _quando(data_pedido: str | None, instante: datetime | None) -> str:
    if instante is not None:
        h = instante.astimezone(config.fuso())
        minutos = "" if h.minute == 0 else f"{h.minute:02d}"
        return f"Em {h.strftime('%d/%m/%Y')} às {h.hour}h{minutos}"
    return f"Em {_data_br(data_pedido)}" if data_pedido else ""


def _compensacao() -> str:
    f = fato("pagamento.boleto_compensacao_dias_uteis_max")
    return f"Compensação em até {f.valor} dias úteis" if f and f.valor else ""


def etapas_do_pedido(status: str | None, *, forma: str | None = None, criado_em: str | None = None,
                     agora: datetime | None = None, data_pedido: str | None = None, rastreio: str | None = None,
                     previsao: str | None = None, nota: str | None = None) -> list[Etapa]:
    """Etapas para o status do CSV (pending, confirmed, shipped, delivered, cancelled) ou "PED-" (pedido do site).

    Pedido do site: `forma` (pix, debito, credito, boleto) e `criado_em` (horário gravado) decidem a etapa; o
    crédito sai de "Pagamento em análise" `ANALISE_MINUTOS` depois do pedido, pelo relógio `agora` (padrão
    `config.agora()`). O site não simula envio nem entrega.
    """
    instante = _instante(criado_em)
    recebido = Etapa(RECEBIDO, FEITA, _quando(data_pedido or (criado_em or "")[:10] or None, instante))
    if status == "cancelled":
        return [recebido, Etapa(CANCELADO, ATUAL, nota or "")]
    if status == STATUS_SITE:
        return _etapas_do_site(recebido, forma, instante, agora)
    if status == "pending":  # CSV: recebido, ainda sem pagamento
        return [recebido, Etapa(AGUARDANDO, ATUAL), *(Etapa(r, PENDENTE) for r in _DEPOIS)]
    if status not in _ATUAL_CSV:  # status desconhecido: só o que é certo, o pedido recebido
        return [Etapa(RECEBIDO, ATUAL, recebido.detalhe)]
    return [recebido, Etapa(PAGAMENTO, FEITA), *_depois_do_pagamento(_ATUAL_CSV[status], status, rastreio, previsao)]


def etapas_do_site(dados: dict) -> list[Etapa]:
    """Etapas de um pedido do site a partir dos dados de `consultar_pedido_demo`."""
    return etapas_do_pedido(STATUS_SITE, forma=dados.get("forma"), criado_em=dados.get("criado_em"))


def _depois_do_pagamento(atual: int, status: str, rastreio: str | None, previsao: str | None) -> list[Etapa]:
    etapas = []
    for i, rotulo in enumerate(_DEPOIS):
        estado = FEITA if i < atual else ATUAL if i == atual else PENDENTE
        detalhe = ""
        if rotulo == ENVIADO and rastreio and estado != PENDENTE:
            detalhe = f"Código de rastreio: {rastreio}"
        elif rotulo == ENTREGUE and status != "delivered" and previsao:
            detalhe = f"Previsão: {_data_br(previsao)}"
        etapas.append(Etapa(rotulo, estado, detalhe))
    return etapas


def _etapas_do_site(recebido: Etapa, forma: str | None, instante: datetime | None,
                    agora: datetime | None) -> list[Etapa]:
    a_seguir = lambda *rotulos: [Etapa(r, PENDENTE) for r in rotulos]  # noqa: E731
    if forma == "boleto":  # não há pagamento: não avança sozinho
        return [recebido, Etapa(AGUARDANDO, ATUAL, _compensacao()), *a_seguir(*_DEPOIS)]
    if forma == "credito":
        decorrido = (agora or config.agora()) - instante if instante is not None else None
        if decorrido is None or decorrido < timedelta(minutes=ANALISE_MINUTOS):
            return [recebido, Etapa(EM_ANALISE, ATUAL, f"Aprovação em até {ANALISE_MINUTOS} minutos"),
                    *a_seguir(*_DEPOIS)]
    # PIX e débito confirmam na hora; o crédito, depois da análise simulada
    return [recebido, Etapa(PAGAMENTO, FEITA), Etapa(SEPARACAO, ATUAL), *a_seguir(ENVIADO, ENTREGUE)]


def etapa_atual(etapas: list[Etapa]) -> Etapa:
    return next(e for e in etapas if e.estado == ATUAL)


# Frase da Lia para cada etapa atual, em primeira pessoa; não repete código de rastreio, previsão nem observação,
# que a resposta já traz.
_FRASE_LIA = {
    AGUARDANDO: "Pelo que eu vejo, ele está aguardando a confirmação do pagamento para seguir.",
    EM_ANALISE: "Pelo que eu vejo, o pagamento está em análise.",
    SEPARACAO: "Pelo que eu vejo, o pagamento já foi confirmado e o pedido está em separação.",
    ENVIADO: "Pelo que eu vejo, ele já saiu e está a caminho de você.",
    ENTREGUE: "Pelo que eu vejo, ele já chegou ao destino.",
}


def frase_lia(etapas: list[Etapa]) -> str:
    """Etapa atual dita pela Lia, a mesma que o rastreio mostra. Vazia onde a resposta já diz tudo (cancelado)."""
    atual = etapa_atual(etapas)
    frase = _FRASE_LIA.get(atual.rotulo, "")
    if frase and atual.rotulo in (AGUARDANDO, EM_ANALISE, SEPARACAO) and atual.detalhe:
        frase = f"{frase} {atual.detalhe}."
    return frase
