"""Converte resultados de ferramenta em Fato, para auditar o que a resposta usou."""
from __future__ import annotations

from typing import Any

from ..ferramentas.envelope import Fato, Resultado


def fatos_do_resultado(ferramenta: str, args: dict[str, Any], r: Resultado) -> list[Fato]:
    if r.estado != "ok" or not r.fontes:
        return []
    fonte = r.fontes[0]
    d = r.dados
    saida: list[Fato] = []

    def add(tipo: str, id_: str | int, atributo: str, valor: Any, condicao: str | None = None, f=fonte) -> None:
        if valor is not None:
            saida.append(Fato(entidade_tipo=tipo, entidade_id=id_, atributo=atributo, valor=valor, condicao=condicao,
                              fonte=f))

    if ferramenta == "buscar_produtos":
        for i in d["itens"]:
            add("produto", i["id"], "preco_centavos", i["preco_centavos"])
            add("produto", i["id"], "situacao_venda", i["situacao_venda"])
    elif ferramenta == "ver_produto":
        add("produto", d["id"], "preco_centavos", d["preco_centavos"])
        add("produto", d["id"], "situacao_venda", d["situacao_venda"])
    elif ferramenta == "calcular_condicoes":
        ent = d.get("produto_id", "valor_avulso")
        cond = f"forma={d['forma']}, parcelas={d['parcelas']}"
        for atributo in ("original_centavos", "percentual", "final_centavos", "parcela_centavos", "permitido"):
            add("condicao", ent, atributo, d.get(atributo), cond)
        if "frete" in d:
            add("condicao", ent, "frete", d["frete"]["situacao"], cond)
    elif ferramenta == "consultar_pedido":
        for atributo, chave in (("status", "status"), ("total_gravado_centavos", "total_gravado_centavos"),
                                ("previsao", "previsao"), ("rastreio", "rastreio")):
            add("pedido", d["pedido_id"], atributo, d.get(chave))
    elif ferramenta == "consultar_politica":
        for s, f in zip(d["secoes"], r.fontes):
            for c in s["condicoes"]:
                add("politica", s["id"], c["chave"], c["valor"], c.get("unidade"), f)
    elif ferramenta == "listar_promocoes":
        for i in d["promocoes"]:
            add("produto", i["produto_id"], "promocao_percentual", i["percentual"])
            add("produto", i["produto_id"], "preco_final_centavos", i["final_centavos"], "promocao ativa")
    elif ferramenta == "registrar_encaminhamento":
        add("chamado", d["protocolo"], "status", d["status"])
        add("chamado", d["protocolo"], "tipo", d["tipo"])
    return saida
