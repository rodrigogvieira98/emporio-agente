"""Checkout da compra de demonstração.

Todo valor vem de `calcular_condicoes`: preço final por unidade (promoção, ou PIX quando não há promoção, sem
somar), parcela do crédito e frete. Aqui só se agrega: unidade vezes quantidade, soma dos itens e soma do frete
numérico. O total gravado é o recalculado no servidor; nada vindo do navegador é confiado.

Forma neutra no total: o desconto da forma de pagamento já entrou item a item. Para o total do pedido (frete e
parcela) a ferramenta é chamada com `debito` ou `credito`, formas que não aplicam desconto, para o PIX não
incidir uma segunda vez sobre o que já foi calculado.
"""
from __future__ import annotations

from typing import Any

from .. import config
from ..dados import banco
from ..ferramentas.condicoes import calcular_condicoes
from ..ferramentas.pedido_demo import AVISO_DEMO, formatar_numero
from ..politicas.manual import fato
from . import carrinho
from . import cep as cep_mod

FORMAS = ("pix", "debito", "credito", "boleto")
FORMA_NEUTRA = "debito"

ROTULO_FRETE = {
    "gratis": "Frete grátis",
    "taxa": "Frete",
    "cotacao_necessaria": "Frete calculado pela equipe",
}


def _regiao_frete(situacao: str) -> str:
    """Região explícita do frete: grátis e taxa valem na cidade-base do manual; cotação é para as demais."""
    base = fato("frete.cidade_base")
    if situacao == "cotacao_necessaria":
        return "Em outras cidades"
    return f"Em {base.valor}" if base else ""


CIDADE_NAO_LOCALIZADA = "Cidade não localizada"


def _destino(cep: str):
    """Localização do CEP e a cidade que o frete e o pedido usam (None se o CEP não vale)."""
    loc = cep_mod.localizar(cep)
    if loc.estado == "ok":
        if cep_mod.eh_cidade_base(loc.cidade, loc.uf):
            return loc, str(fato("frete.cidade_base").valor)
        return loc, f"{loc.cidade}/{loc.uf}"
    if loc.estado == "indisponivel":
        return loc, CIDADE_NAO_LOCALIZADA  # não bloqueia: o frete fica com a equipe
    return loc, None


class CompraRecusada(Exception):
    """O checkout não pode ser finalizado como confirmado; `.pendencias` diz por quê."""

    def __init__(self, pendencias: list[str]):
        super().__init__("; ".join(pendencias))
        self.pendencias = pendencias


def parcelas_max() -> int:
    f = fato("pagamento.credito_parcelas_max")
    return int(f.valor) if f else 1


def normalizar_escolha(forma: str, parcelas: int | str, cep: str) -> tuple[str, int, str]:
    forma = forma if forma in FORMAS else "pix"
    try:
        n = int(parcelas)
    except (TypeError, ValueError):
        n = 1
    n = max(1, min(n, parcelas_max())) if forma == "credito" else 1
    return forma, n, cep_mod.formatar(cep)


def _linha(item: dict[str, Any], forma: str) -> dict[str, Any]:
    r = calcular_condicoes(produto_id=item["produto_id"], forma=forma, parcelas=1)
    base = {"produto_id": item["produto_id"], "quantidade": item["quantidade"], "estado": r.estado, "nome": None,
            "original": None, "final_unit": None, "percentual": None, "pix_aplicado": False, "subtotal": None,
            "a_confirmar": False, "bloqueio": None}
    if r.estado == "ok":
        d = r.dados
        base.update(nome=d["produto_nome"], original=d["original_centavos"], final_unit=d["final_centavos"],
                    percentual=d["percentual"], pix_aplicado=bool(d.get("pix_aplicado")),
                    subtotal=d["final_centavos"] * item["quantidade"])
        if d["situacao_venda"] != "disponivel":
            base["bloqueio"] = "indisponivel"
    elif r.estado == "ambiguo":
        base.update(a_confirmar=True, bloqueio="promocao_em_conferencia")
    else:
        base["bloqueio"] = "falha"
    return base


def calcular(sessao: str, forma: str = "pix", parcelas: int | str = 1, cep: str = "") -> dict[str, Any]:
    forma, n, cep = normalizar_escolha(forma, parcelas, cep)
    loc, cidade = _destino(cep)
    itens = carrinho.listar(sessao)
    saida: dict[str, Any] = {
        "forma": forma, "parcelas": n, "cep": cep, "cidade": cidade or "", "localizacao": loc, "linhas": [], "vazio": not itens, "produtos_total": 0,
        "frete": None, "total": 0, "total_com_frete_definido": False, "parcela": None, "permitido": "sim",
        "pendencias": [], "pode_finalizar": False, "aviso": AVISO_DEMO,
    }
    if not itens:
        return saida
    linhas = [_linha(i, forma) for i in itens]
    saida["linhas"] = linhas
    pend: list[str] = []
    for l in linhas:
        if l["bloqueio"] == "indisponivel":
            pend.append(f"{l['nome']} não está mais disponível. Tire do carrinho para continuar.")
        elif l["bloqueio"] == "promocao_em_conferencia":
            pend.append("Há um item com promoção em conferência. A equipe precisa confirmar o valor.")
        elif l["bloqueio"] == "falha":
            pend.append("Não consegui consultar um dos itens agora. Tente de novo em instantes.")
    if pend:
        saida["pendencias"] = pend
        return saida
    goods = sum(l["subtotal"] for l in linhas)
    # base do frete: promoções valem, o desconto do PIX não (a forma de pagamento nunca muda o frete)
    base_frete = sum((l["original"] if l["pix_aplicado"] else l["final_unit"]) * l["quantidade"] for l in linhas)
    saida["produtos_total"] = goods
    total = goods

    if cidade:
        rf = calcular_condicoes(valor=goods, forma=FORMA_NEUTRA, cidade=cidade, valor_pedido=base_frete)
        if rf.estado != "ok":
            pend.append("Não consegui calcular o frete agora. Tente de novo em instantes.")
        else:
            frete = rf.dados["frete"]
            saida["frete"] = {"situacao": frete["situacao"], "taxa": frete["taxa_centavos"],
                              "rotulo": ROTULO_FRETE.get(frete["situacao"], frete["situacao"]),
                              "regiao": _regiao_frete(frete["situacao"])}
            if frete["taxa_centavos"] is not None:
                total += frete["taxa_centavos"]
                saida["total_com_frete_definido"] = True
    elif loc.estado == "inexistente":
        pend.append("CEP não encontrado. Confira os números ou use o link para descobrir o seu CEP.")
    elif cep:
        pend.append("O CEP precisa ter 8 números. Confira e tente de novo.")
    else:
        pend.append("Informe o CEP de entrega para calcular o frete.")
    saida["total"] = total

    if forma == "credito":
        rc = calcular_condicoes(valor=total, forma="credito", parcelas=n)
        if rc.estado != "ok":
            pend.append("Não consegui calcular o parcelamento agora. Tente de novo em instantes.")
        else:
            saida["parcela"] = rc.dados["parcela_centavos"]
            saida["permitido"] = rc.dados["permitido"]
            if rc.dados["permitido"] == "requer_confirmacao":
                pend.append("Esta parcela precisa ser confirmada com a equipe, então não dá para finalizar como "
                            "confirmada. Escolha menos parcelas ou outra forma de pagamento.")
            elif rc.dados["permitido"] == "nao":
                pend.append("Com esta quantidade de parcelas a parcela fica abaixo do mínimo da loja. "
                            "Escolha menos parcelas.")
    saida["pendencias"] = pend
    saida["pode_finalizar"] = not pend
    return saida


def finalizar(sessao: str, forma: str, parcelas: int | str, cep: str) -> str:
    """Recalcula no servidor, grava o pedido de demonstração e esvazia o carrinho. Devolve DEMO-NNNN."""
    c = calcular(sessao, forma, parcelas, cep)
    if c["vazio"]:
        raise CompraRecusada(["O carrinho está vazio."])
    if not c["pode_finalizar"]:
        raise CompraRecusada(c["pendencias"])
    frete = c["frete"]
    conn = banco.conectar()
    try:
        banco.garantir_tabelas_demo(conn)
        with conn:
            cur = conn.execute(
                "INSERT INTO pedidos_demo (numero, sessao, forma, parcelas, cidade, frete_situacao, frete_centavos, "
                "total_centavos, parcela_centavos, aviso, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("pendente", sessao, c["forma"], c["parcelas"], c["cidade"], frete["situacao"], frete["taxa"],
                 c["total"], c["parcela"], AVISO_DEMO, config.agora().isoformat()))
            pedido_id = cur.lastrowid
            numero = formatar_numero(pedido_id)
            conn.execute("UPDATE pedidos_demo SET numero = ? WHERE id = ?", (numero, pedido_id))
            for l in c["linhas"]:
                conn.execute(
                    "INSERT INTO itens_pedido_demo (pedido_id, produto_id, nome, quantidade, original_unit_centavos, "
                    "final_unit_centavos, percentual, pix_aplicado, subtotal_centavos) VALUES (?,?,?,?,?,?,?,?,?)",
                    (pedido_id, l["produto_id"], l["nome"], l["quantidade"], l["original"], l["final_unit"],
                     l["percentual"], int(l["pix_aplicado"]), l["subtotal"]))
            conn.execute("DELETE FROM carrinhos WHERE sessao = ?", (sessao,))
    finally:
        conn.close()
    return numero
