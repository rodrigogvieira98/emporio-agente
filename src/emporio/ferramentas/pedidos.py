"""consultar_pedido: identificação simulada por número do pedido e final do telefone."""
from __future__ import annotations

import hmac
import re
from datetime import date

from pydantic import field_validator

from .. import config
from ..dados import banco
from .envelope import EntradaBase, Fonte, Resultado, ferramenta, resultado

MAX_TENTATIVAS = 3  # limite de segurança do sistema, por conversa
ENCERRADOS = {"delivered", "cancelled"}
MOTIVO_NEGADO = "nao_foi_possivel_validar"


class EntradaPedido(EntradaBase):
    pedido_id: int
    final_telefone: str
    conversa_id: str

    @field_validator("final_telefone")
    @classmethod
    def _quatro_digitos(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}", v):
            raise ValueError("final precisa ter 4 digitos")
        return v

    @field_validator("conversa_id")
    @classmethod
    def _conversa(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("conversa vazia")
        return v


def _negado() -> Resultado:
    # Mesmo resultado para pedido inexistente, final errado e limite estourado.
    return resultado("negado", motivo=MOTIVO_NEGADO)


@ferramenta(EntradaPedido)
def consultar_pedido(e: EntradaPedido) -> Resultado:
    conn = banco.conectar()
    try:
        falhas = conn.execute("SELECT COUNT(*) FROM tentativas_pedido WHERE conversa_id = ? AND sucesso = 0",
                              (e.conversa_id,)).fetchone()[0]
        if falhas >= MAX_TENTATIVAS:
            return _negado()
        pedido = conn.execute(
            "SELECT p.*, c.telefone FROM pedidos p JOIN clientes c ON c.id = p.cliente_id WHERE p.id = ?",
            (e.pedido_id,)).fetchone()
        final_real = re.sub(r"\D", "", pedido["telefone"])[-4:] if pedido else ""
        valido = bool(pedido) and hmac.compare_digest(final_real, e.final_telefone)
        with conn:
            conn.execute("INSERT INTO tentativas_pedido (conversa_id, pedido_id, sucesso, criado_em) VALUES (?,?,?,?)",
                         (e.conversa_id, e.pedido_id, int(valido), config.agora().isoformat()))
        if not valido:
            return _negado()
        itens = conn.execute(
            "SELECT pr.nome AS nome, i.quantidade AS quantidade FROM itens_pedido i "
            "JOIN produtos pr ON pr.id = i.produto_id WHERE i.pedido_id = ? ORDER BY i.id",
            (e.pedido_id,)).fetchall()
        previsao = pedido["previsao_entrega"]
        vencida = bool(previsao) and pedido["status"] not in ENCERRADOS and date.fromisoformat(previsao) < config.hoje()
        dados = {
            "pedido_id": pedido["id"],
            "status": pedido["status"],
            "data_pedido": pedido["data_pedido"],
            "itens": [{"nome": i["nome"], "quantidade": i["quantidade"]} for i in itens],
            "total_gravado_centavos": pedido["total_centavos"],
            "forma_pagamento": pedido["forma_pagamento"],
            "rastreio": pedido["rastreio"],
            "previsao": previsao,
            "previsao_vencida": vencida,
            "nota": pedido["nota"],
        }
        return resultado("ok", dados, [Fonte(tipo="banco", referencia=f"pedidos/{pedido['id']}")])
    finally:
        conn.close()
