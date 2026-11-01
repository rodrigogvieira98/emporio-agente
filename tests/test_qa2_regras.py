"""QA 2 da Lia, etapa A."""
from __future__ import annotations

from emporio.agente.fabrica import criar_agente


class _Dubla:
    chamadas: list = []

    def conversar(self, *a, **k):  # pragma: no cover - não deve ser chamado
        raise AssertionError("sem chamada")


def test_redacao_desligada_por_padrao(monkeypatch):
    monkeypatch.delenv("EMPORIO_REDACAO", raising=False)
    monkeypatch.setenv("EMPORIO_DECISOR", "regras")
    assert criar_agente("falso:1b", _Dubla()).redator is None
    monkeypatch.setenv("EMPORIO_REDACAO", "1")
    assert criar_agente("falso:1b", _Dubla()).redator is not None
    monkeypatch.setenv("EMPORIO_REDACAO", "0")
    assert criar_agente("falso:1b", _Dubla()).redator is None
