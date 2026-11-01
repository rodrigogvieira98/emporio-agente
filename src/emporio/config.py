"""Caminhos, fuso e data de referência. Nada aqui é fato de loja."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FUSO_NOME = "America/Campo_Grande"


def caminho_banco() -> Path:
    return Path(os.environ.get("EMPORIO_DB") or RAIZ / "var" / "emporio.db")


def caminho_trace() -> Path:
    return Path(os.environ.get("EMPORIO_TRACE") or RAIZ / "var" / "trace.jsonl")


def caminho_raw() -> Path:
    return Path(os.environ.get("EMPORIO_RAW") or RAIZ / "data" / "raw")


def caminho_manual() -> Path:
    padrao = Path(__file__).resolve().parent / "politicas" / "manual_v2_1.yaml"
    return Path(os.environ.get("EMPORIO_MANUAL") or padrao)


def fuso():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(FUSO_NOME)
    except Exception:  # sem base tzdata: a loja não usa horário de verão desde 2019
        return timezone(timedelta(hours=-4), FUSO_NOME)


def agora() -> datetime:
    """Instante atual no fuso da loja.

    EMPORIO_DATA_REFERENCIA aceita data (ISO) ou data e hora. Só com data,
    vale esse dia com a hora real do relógio.
    """
    tz = fuso()
    real = datetime.now(tz)
    bruto = os.environ.get("EMPORIO_DATA_REFERENCIA", "").strip()
    if not bruto:
        return real
    try:
        if "T" in bruto or " " in bruto:
            dt = datetime.fromisoformat(bruto)
            return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
        d = date.fromisoformat(bruto)
    except ValueError as erro:
        raise ValueError(f"EMPORIO_DATA_REFERENCIA invalida: {bruto!r}") from erro
    return real.replace(year=d.year, month=d.month, day=d.day)


def hoje() -> date:
    return agora().date()


def caminho_frete_simulado() -> Path:
    padrao = Path(__file__).resolve().parent / "politicas" / "frete_simulado.yaml"
    return Path(os.environ.get("EMPORIO_FRETE_SIMULADO") or padrao)
