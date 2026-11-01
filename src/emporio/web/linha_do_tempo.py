"""Linha do tempo do rastreio: função pura que transforma o status gravado do pedido em etapas.

Não inventa evento: os dados não trazem data por etapa, então só aparecem a data do pedido, o código de rastreio,
a previsão de entrega e a observação do pedido cancelado.
"""
from __future__ import annotations

from dataclasses import dataclass

from .apresentacao import data_br

STATUS_SITE = "PED-"  # pedido feito no site (número PED-...), sem status de fulfillment gravado

FEITA, ATUAL, PENDENTE = "feita", "atual", "pendente"
ROTULO_ESTADO = {FEITA: "concluída", ATUAL: "etapa atual", PENDENTE: "a seguir"}

_RECEBIDO, _PAGAMENTO, _ENVIADO, _ENTREGUE, _CANCELADO = (
    "Pedido recebido", "Pagamento confirmado", "Enviado", "Entregue", "Cancelado")
_FLUXO = (_RECEBIDO, _PAGAMENTO, _ENVIADO, _ENTREGUE)
# índice da etapa atual de cada status no fluxo normal
_ATUAL = {"pending": 0, "confirmed": 1, "shipped": 2, "delivered": 3}


@dataclass(frozen=True)
class Etapa:
    rotulo: str
    estado: str  # feita | atual | pendente
    detalhe: str = ""

    @property
    def estado_texto(self) -> str:
        return ROTULO_ESTADO[self.estado]


def etapas_do_rastreio(status: str | None, *, data_pedido: str | None = None, rastreio: str | None = None,
                       previsao: str | None = None, nota: str | None = None) -> list[Etapa]:
    """Etapas do rastreio para o status gravado (pending, confirmed, shipped, delivered, cancelled) ou "PED-"."""
    recebido_detalhe = f"Em {data_br(data_pedido)}" if data_pedido else ""
    if status == "cancelled":
        return [Etapa(_RECEBIDO, FEITA, recebido_detalhe), Etapa(_CANCELADO, ATUAL, nota or "")]
    if status not in _ATUAL:  # PED- e qualquer status desconhecido: só o que é certo, o pedido recebido
        return [Etapa(_RECEBIDO, ATUAL, recebido_detalhe)]
    atual = _ATUAL[status]
    etapas = []
    for i, rotulo in enumerate(_FLUXO):
        estado = FEITA if i < atual else ATUAL if i == atual else PENDENTE
        detalhe = ""
        if rotulo == _RECEBIDO:
            detalhe = recebido_detalhe
        elif rotulo == _ENVIADO and rastreio and estado != PENDENTE:
            detalhe = f"Código de rastreio: {rastreio}"
        elif rotulo == _ENTREGUE and status != "delivered" and previsao:
            detalhe = f"Previsão: {data_br(previsao)}"
        etapas.append(Etapa(rotulo, estado, detalhe))
    return etapas
