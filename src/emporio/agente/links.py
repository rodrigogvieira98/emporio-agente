"""Links e botão de carrinho da Lia: gerados só por código, a partir do resultado das ferramentas.

O modelo nunca escreve nem escolhe link. A lista de destinos é fechada (rotas internas do site), com no máximo
2 por resposta. O texto da resposta não muda por causa dos links. A Lia nunca coloca nada no carrinho: o botão
faz um POST do próprio cliente, e o texto nunca diz que adicionou.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from .estado import Estado

MAX_LINKS = 2
# Única lista de destinos permitida; qualquer outro endereço é descartado.
DESTINOS = re.compile(
    r"^(/produto/\d+|/privacidade|/catalogo(\?(categoria|termo)=[A-Za-z0-9%_.-]+)?|/rastreio|/politicas|/perguntas-frequentes|"
    r"/fale-conosco)$")
ACAO_CARRINHO = "/carrinho/adicionar"
# A página do carrinho fica fora de DESTINOS (a lista de links genéricos); só a resposta "carrinho_chat" a oferece.
PAGINA_CARRINHO = "/carrinho"

# resposta -> destino
POR_RESPOSTA: dict[str, tuple[str, str]] = {
    "status_pedido": ("/rastreio", "Rastrear pelo site"),
    "status_pedido_demo": ("/rastreio", "Rastrear pelo site"),
    "pedir_pedido": ("/rastreio", "Rastrear pelo site"),
    "pedido_negado": ("/rastreio", "Rastrear pelo site"),
    "previsao_entrega": ("/rastreio", "Rastrear pelo site"),
    "trocas_info": ("/politicas", "Ver as políticas da loja"),
    "trocas_detalhe": ("/politicas", "Ver as políticas da loja"),
    "garantia_info": ("/politicas", "Ver as políticas da loja"),
    "reembolso_prazo": ("/politicas", "Ver as políticas da loja"),
    "item_nao_elegivel": ("/politicas", "Ver as políticas da loja"),
    "frete_info": ("/politicas", "Ver as políticas da loja"),
    "frete_prazo": ("/politicas", "Ver as políticas da loja"),
    "pagamento": ("/politicas", "Ver as políticas da loja"),
    "contato": ("/fale-conosco", "Falar com a loja"),
    "privacidade": ("/privacidade", "Ver privacidade e cookies"),
    "rastreio_como": ("/rastreio", "Rastrear pelo site"),
    "devolucao_frete": ("/politicas", "Ver as políticas da loja"),
    "rain_check": ("/politicas", "Ver as políticas da loja"),
    "frete_modalidade": ("/politicas", "Ver as políticas da loja"),
    "devolucao_loja_fisica": ("/politicas", "Ver as políticas da loja"),
    "garantia_excluida": ("/politicas", "Ver as políticas da loja"),
    "sem_dado": ("/perguntas-frequentes", "Ver as perguntas frequentes"),
    "nao_entendi": ("/perguntas-frequentes", "Ver as perguntas frequentes"),
}
COM_PRODUTO = {"preco", "ficha_produto", "disponibilidade", "produto_indisponivel", "extremo_lista", "vou_pensar", "objecao_preco",
               "frete_produto"}


def _produto_do_turno(estado: Estado) -> dict[str, Any] | None:
    """Produto consultado neste turno por ver_produto (ou o primeiro de uma busca de um item só)."""
    for p in reversed(estado.passos):
        if p.ferramenta == "ver_produto" and p.resultado.estado == "ok":
            return p.resultado.dados
        if (p.ferramenta == "buscar_produtos" and p.resultado.estado == "ok" and p.args.get("limite") == 1
                and p.resultado.dados["itens"]):
            return p.resultado.dados["itens"][0]
    return None


def _link(href: str, rotulo: str) -> dict[str, Any] | None:
    return {"tipo": "link", "rotulo": rotulo, "href": href} if DESTINOS.match(href) else None


def pode_comprar(estado: Estado, chave: str, parametros: dict[str, Any]) -> dict[str, Any] | None:
    """Produto do botão de carrinho, ou None: precisa estar disponível, com preço sem conferência pendente."""
    if chave != "preco" or parametros.get("propor_registro"):
        return None
    produto = _produto_do_turno(estado)
    cond = estado.ultimo("calcular_condicoes")
    if produto is None or produto.get("situacao_venda") != "disponivel" or cond is None or cond.estado != "ok":
        return None
    if cond.dados.get("permitido") == "requer_confirmacao" or (produto.get("promocao") or {}).get("ambigua"):
        return None
    return produto


def gerar(estado: Estado, chave: str | None, parametros: dict[str, Any], compra: bool) -> list[dict[str, Any]]:
    """Até 2 links para a resposta final do turno. Recusa, escopo e reclamação não levam link de venda."""
    if not chave:
        return []
    saida: list[dict[str, Any]] = []
    if compra:
        produto = pode_comprar(estado, chave, parametros)
        if produto is not None:
            saida.append({"tipo": "carrinho", "rotulo": "Adicionar ao carrinho", "acao": ACAO_CARRINHO,
                          "produto_id": int(produto["id"]), "quantidade": 1})
    if chave == "carrinho_chat":
        return [{"tipo": "link", "rotulo": "Abrir o carrinho", "href": PAGINA_CARRINHO}]
    if chave in COM_PRODUTO:
        produto = _produto_do_turno(estado)
        if produto is not None:
            novo = _link(f"/produto/{int(produto['id'])}", f"Ver {produto['nome']}")
            if novo:
                saida.append(novo)
    elif chave == "busca":
        busca = estado.slots.get("categoria")
        novo = (_link(f"/catalogo?categoria={quote(str(busca))}", "Ver no catálogo") if busca else
                _link(f"/catalogo?termo={quote(str(estado.slots['termo']))}", "Ver no catálogo")
                if estado.slots.get("termo") else None)
        if novo:
            saida.append(novo)
    elif chave in POR_RESPOSTA:
        destino, rotulo = POR_RESPOSTA[chave]
        novo = _link(destino, rotulo)
        if novo:
            saida.append(novo)
    return saida[:MAX_LINKS]


def etapa_do_lead(chave: str | None, parametros: dict[str, Any], links: list[dict[str, Any]]) -> str | None:
    """Etapa do funil para o trace (sem texto do cliente): interesse, qualificado ou pronto."""
    if any(x["tipo"] == "carrinho" for x in links):
        return "pronto"
    if chave == "busca" and (parametros.get("recomendacao") or parametros.get("qualificado")):
        return "qualificado"
    if chave in ("preco", "disponibilidade", "busca", "objecao_preco", "extremo_lista", "vou_pensar"):
        return "interesse"
    return None
