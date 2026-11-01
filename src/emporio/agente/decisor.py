"""Contrato do decisor. RegrasDecisor é o controle; um LLM entra depois sem mudar o laço."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .estado import Acao, Estado


@runtime_checkable
class Decisor(Protocol):
    def decidir(self, estado: Estado, mensagem: str) -> Acao:
        """Devolve a próxima ação. O laço valida esquema, dados e permissão antes de executar."""
        ...
