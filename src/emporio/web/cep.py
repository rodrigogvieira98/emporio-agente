"""Compatibilidade: a consulta de CEP mora em `emporio.ferramentas.cep` (o agente não importa `web/`).

Este nome aponta para o mesmo módulo, então quem importa daqui enxerga o mesmo estado (memória, dublês).
"""
from __future__ import annotations

import sys

from ..ferramentas import cep as _cep

sys.modules[__name__] = _cep
