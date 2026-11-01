"""Aberto ou fechado e próxima abertura, a partir da condição horario.funcionamento do manual."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def _hora(texto: str) -> time:
    h, m = texto.split(":")
    return time(int(h), int(m))


def _faixa_do_dia(funcionamento: list[dict[str, Any]], dia: int) -> tuple[time, time] | None:
    for f in funcionamento:
        if dia in f["dias"] and not f.get("fechado"):
            return _hora(f["abre"]), _hora(f["fecha"])
    return None


def situacao(funcionamento: list[dict[str, Any]], agora: datetime) -> dict[str, Any]:
    """Devolve {"aberto": bool, "retorno": {"dia": ..., "quando": ..., "hora": "HH:MM"} | None}."""
    faixa = _faixa_do_dia(funcionamento, agora.weekday())
    if faixa and faixa[0] <= agora.time() < faixa[1]:
        return {"aberto": True, "retorno": None}
    for adiante in range(0, 8):
        dia = (agora + timedelta(days=adiante)).weekday()
        f = _faixa_do_dia(funcionamento, dia)
        if not f:
            continue
        if adiante == 0 and agora.time() >= f[0]:
            continue  # hoje já passou do horário de abertura (e do fechamento)
        quando = "hoje" if adiante == 0 else "amanhã" if adiante == 1 else DIAS[dia]
        return {"aberto": False, "retorno": {"dia": DIAS[dia], "quando": quando, "hora": f[0].strftime("%H:%M")}}
    return {"aberto": False, "retorno": None}


def descrever_dias(dias: list[int]) -> str:
    dias = sorted(dias)
    if len(dias) > 2 and dias == list(range(dias[0], dias[-1] + 1)):
        return f"{DIAS[dias[0]].split('-')[0]} a {DIAS[dias[-1]]}"
    return " e ".join(DIAS[d] for d in dias)
