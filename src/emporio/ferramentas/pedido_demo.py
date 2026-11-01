"""consultar_pedido_demo: pedido da compra de demonstração (incremento 1), à parte dos pedidos dos dados.

A identificação é a sessão do navegador: quem fez o pedido de demonstração é quem o consulta. Número
inexistente e número de outra sessão voltam no mesmo `negado`, como em consultar_pedido.
"""
from __future__ import annotations

import re

from pydantic import field_validator

from .. import dinheiro
from ..dados import banco
from .envelope import EntradaBase, Fonte, Resultado, ferramenta, resultado

PREFIXO = "PED-"
PADRAO_NUMERO = re.compile(r"PED-(\d{1,9})", re.I)
AVISO_DEMO = "Pedido registrado. Nenhum valor foi cobrado."
MOTIVO_NEGADO = "nao_foi_possivel_validar"


def formatar_numero(identificador: int) -> str:
    return f"{PREFIXO}{identificador:04d}"


def rotulos_frete(situacao: str | None, frete_centavos: int | None) -> dict[str, str]:
    """Linha do frete e rótulo do total, os mesmos no checkout, na confirmação e na Lia."""
    if situacao is None:
        return {"linha": "Frete: Informe o CEP", "total": "Total dos produtos"}
    if situacao == "gratis":
        return {"linha": "Frete: Grátis", "total": "Total"}
    if situacao == "taxa" and frete_centavos is not None:
        return {"linha": f"Frete: {dinheiro.formatar(frete_centavos)}", "total": "Total"}
    if situacao == "estimado" and frete_centavos is not None:
        return {"linha": f"Frete estimado (simulação): {dinheiro.formatar(frete_centavos)}", "total": "Total estimado"}
    return {"linha": "Frete: Cotação com a equipe", "total": "Total dos produtos"}


def achar_numero(texto: str) -> str | None:
    """Número normalizado (PED-0001) se o texto citar um pedido de demonstração; senão None."""
    m = PADRAO_NUMERO.search(texto or "")
    return formatar_numero(int(m.group(1))) if m else None


class EntradaPedidoDemo(EntradaBase):
    numero: str
    conversa_id: str

    @field_validator("numero")
    @classmethod
    def _numero(cls, v: str) -> str:
        if not PADRAO_NUMERO.fullmatch(v.strip()):
            raise ValueError("numero de demonstracao invalido")
        return v

    @field_validator("conversa_id")
    @classmethod
    def _conversa(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("conversa vazia")
        return v


@ferramenta(EntradaPedidoDemo)
def consultar_pedido_demo(e: EntradaPedidoDemo) -> Resultado:
    numero = achar_numero(e.numero)
    conn = banco.conectar()
    try:
        banco.garantir_tabelas_demo(conn)
        pedido = conn.execute("SELECT * FROM pedidos_demo WHERE numero = ?", (numero,)).fetchone()
        if pedido is None or pedido["sessao"] != e.conversa_id:
            return resultado("negado", motivo=MOTIVO_NEGADO)
        itens = conn.execute("SELECT * FROM itens_pedido_demo WHERE pedido_id = ? ORDER BY id",
                             (pedido["id"],)).fetchall()
        rotulos = rotulos_frete(pedido["frete_situacao"], pedido["frete_centavos"])
        dados = {
            "demonstracao": True,
            "numero": pedido["numero"],
            "itens": [{"produto_id": i["produto_id"], "nome": i["nome"], "quantidade": i["quantidade"],
                       "original_unit_centavos": i["original_unit_centavos"],
                       "final_unit_centavos": i["final_unit_centavos"], "percentual": i["percentual"],
                       "pix_aplicado": bool(i["pix_aplicado"]), "subtotal_centavos": i["subtotal_centavos"]}
                      for i in itens],
            "forma": pedido["forma"], "parcelas": pedido["parcelas"], "parcela_centavos": pedido["parcela_centavos"],
            "frete_situacao": pedido["frete_situacao"], "frete_centavos": pedido["frete_centavos"],
            "total_gravado_centavos": pedido["total_centavos"],
            "frete_linha": rotulos["linha"], "total_rotulo": rotulos["total"],
            "aviso": pedido["aviso"], "criado_em": pedido["criado_em"],
        }
        return resultado("ok", dados, [Fonte(tipo="banco", referencia=f"pedidos_demo/{pedido['id']}")])
    finally:
        conn.close()
