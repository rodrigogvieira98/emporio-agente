"""Limite de falhas do rastreio no site, por pedido, por IP e por sessão, numa janela de tempo.

O limite por conversa da ferramenta `consultar_pedido` não basta no site: cookie novo zera a conversa. Aqui as falhas
também contam pelo número do pedido e pelo IP de quem pediu. Fica em memória do processo (reinício zera) e não olha
cabeçalhos de proxy: o IP é o da conexão. Os números são limites de segurança do sistema, não regra de loja.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Callable

JANELA_SEGUNDOS = 15 * 60
MAX_POR_PEDIDO = 5
MAX_POR_IP = 10
MAX_POR_SESSAO = 3


class LimiteRastreio:
    def __init__(self, relogio: Callable[[], float] = time.time):
        self.relogio = relogio
        self._falhas: dict[tuple[str, str], list[float]] = {}
        self._trava = threading.Lock()

    def _chaves(self, sessao: str, pedido: str, ip: str):
        return (("pedido", pedido.strip().upper(), MAX_POR_PEDIDO), ("ip", ip, MAX_POR_IP),
                ("sessao", sessao, MAX_POR_SESSAO))

    def _recentes(self, chave: tuple[str, str], agora: float) -> list[float]:
        marcas = [t for t in self._falhas.get(chave, []) if agora - t < JANELA_SEGUNDOS]
        if marcas:
            self._falhas[chave] = marcas
        else:
            self._falhas.pop(chave, None)
        return marcas

    def segundos_para_liberar(self, sessao: str, pedido: str, ip: str) -> int | None:
        """None se pode tentar; senão, quantos segundos faltam para a primeira chave bloqueada liberar."""
        agora = self.relogio()
        espera = 0.0
        with self._trava:
            for tipo, valor, maximo in self._chaves(sessao, pedido, ip):
                marcas = self._recentes((tipo, valor), agora)
                if len(marcas) >= maximo:
                    espera = max(espera, marcas[len(marcas) - maximo] + JANELA_SEGUNDOS - agora)
        return math.ceil(espera) if espera > 0 else None

    def registrar_falha(self, sessao: str, pedido: str, ip: str) -> None:
        agora = self.relogio()
        with self._trava:
            for tipo, valor, _ in self._chaves(sessao, pedido, ip):
                self._recentes((tipo, valor), agora)
                self._falhas.setdefault((tipo, valor), []).append(agora)

    def janela_atual(self) -> int:
        """Identificador da janela, para a ferramenta (que conta por conversa, sem prazo) recomeçar a cada janela."""
        return int(self.relogio() // JANELA_SEGUNDOS)
