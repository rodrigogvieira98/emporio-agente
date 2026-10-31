"""Fixtures: banco recriado dos CSV originais, isolado por teste."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from emporio import config
from emporio.dados import carga

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def banco_modelo(tmp_path_factory) -> Path:
    destino = tmp_path_factory.mktemp("modelo") / "emporio.db"
    carga.carregar(RAIZ / "data" / "raw", destino)
    return destino


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch, banco_modelo):
    """Cada teste ganha uma cópia do banco, trace próprio e data de referência fixa."""
    destino = tmp_path / "emporio.db"
    shutil.copy(banco_modelo, destino)
    monkeypatch.setenv("EMPORIO_DB", str(destino))
    monkeypatch.setenv("EMPORIO_TRACE", str(tmp_path / "trace.jsonl"))
    # sábado, 10h na loja
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-10-31T10:00:00")
    monkeypatch.delenv("EMPORIO_MANUAL", raising=False)
    return destino


@pytest.fixture
def sql():
    """Conexão direta para preparar ou conferir o banco do teste."""
    conn = sqlite3.connect(config.caminho_banco())
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
