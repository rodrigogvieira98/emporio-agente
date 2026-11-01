"""estimar_frete: simulação de frete para fora da cidade-base. Função única, usada pelo site e pela Lia.

É uma hipótese do protótipo, não tarifa de transportadora. As tabelas moram em `politicas/frete_simulado.yaml`; os
prazos vêm do manual. Determinística: o mesmo pedido e o mesmo CEP dão sempre o mesmo valor. Pedido de grande
porte ou com produto sem caixa definida não recebe valor: fica em cotação individual.
"""
from __future__ import annotations

import json
import math
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Any

import yaml

from .. import config
from ..dados import banco
from ..politicas import manual
from ..texto import normalizar
from . import cep as cep_mod
from .condicoes import calcular_condicoes
from .envelope import EntradaBase, Fonte, Resultado, ferramenta, resultado
from .produtos import FONTE_BANCO

MAX_UNIDADES = 99  # limite de sistema para a entrada, não é fato de loja
SITUACOES = ("estimado", "cotacao_individual", "cidade_base")


class EntradaFrete(EntradaBase):
    itens: list[dict[str, int]]  # [{"produto_id": 118, "quantidade": 1}]
    cep: str


@lru_cache(maxsize=8)
def _ler(caminho: str, mtime_ns: int) -> dict[str, Any]:
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)


def tabelas() -> dict[str, Any]:
    """Relê o YAML quando ele muda."""
    caminho = config.caminho_frete_simulado()
    return _ler(str(caminho), caminho.stat().st_mtime_ns)


def _zona(cfg: dict[str, Any], uf: str) -> dict[str, Any] | None:
    return next((z for z in cfg["zonas"] if uf.upper() in z["ufs"]), None)


def _caixa_do_produto(cfg: dict[str, Any], produto: Any, categoria: str) -> tuple[str | None, str | None]:
    """(chave da caixa, motivo sem caixa). Motivo: grande_porte ou sem_caixa."""
    specs = json.loads(produto["specs_json"] or "{}")
    nome = normalizar(produto["nome"])
    for regra in cfg["produtos"]:
        if "categoria" in regra and normalizar(regra["categoria"]) != normalizar(categoria):
            continue
        if "nome_contem" in regra and not any(normalizar(t) in nome for t in regra["nome_contem"]):
            continue
        if "escala_ate_mm" in regra:
            try:
                if float(specs.get("scale", "").removesuffix("mm")) > regra["escala_ate_mm"]:
                    continue
            except ValueError:
                continue
        if "teclas" in regra and str(specs.get("keys", "")) != str(regra["teclas"]):
            continue
        if regra.get("grande_porte"):
            return None, "grande_porte"
        return regra["caixa"], None
    return None, "sem_caixa"


def _peso_taxado_kg(cfg: dict[str, Any], caixa: dict[str, Any]) -> int:
    volume = Decimal(caixa["comprimento"]) * Decimal(caixa["largura"]) * Decimal(caixa["altura"])
    cubado = volume / Decimal(cfg["peso_cubado"]["divisor"])
    return math.ceil(max(Decimal(str(caixa["peso"])), cubado))


def _preco_caixa(cfg: dict[str, Any], zona: dict[str, Any], caixa: dict[str, Any], modalidade: dict[str, Any]) -> int:
    taxado = _peso_taxado_kg(cfg, caixa)
    base = zona["base_centavos"] + zona["por_kg_centavos"] * (taxado - 1)
    valor = (Decimal(base) * Decimal(str(modalidade["multiplicador"]))).quantize(Decimal(1), ROUND_HALF_UP)
    adicional = cfg["adicional_lado_grande"]
    if max(caixa["comprimento"], caixa["largura"], caixa["altura"]) > adicional["acima_de_cm"]:
        valor += adicional["valor_centavos"]
    return int(valor)


def _prazo_do_manual(nome: str) -> dict[str, int] | None:
    for m in manual.valor("frete.outras_cidades_modalidades"):
        if normalizar(m["nome"]).startswith(normalizar(nome)):
            return dict(m["prazo_dias_uteis"])
    return None


def _fontes() -> list[Fonte]:
    cfg = tabelas()
    achado = manual.carregar_manual().condicao("frete.outras_cidades_modalidades")
    fontes = [Fonte(tipo="calculo", referencia="frete_simulado", versao=str(cfg["versao"])), FONTE_BANCO]
    if achado is not None:
        fontes.append(manual.fonte_da_secao(achado[0]))
    return fontes


@ferramenta(EntradaFrete)
def estimar_frete(e: EntradaFrete) -> Resultado:
    if not e.itens:
        return resultado("falha", motivo="entrada_invalida")
    pedido: dict[int, int] = {}
    for item in e.itens:
        if set(item) != {"produto_id", "quantidade"} or item["produto_id"] <= 0 \
                or not 1 <= item["quantidade"] <= MAX_UNIDADES:
            return resultado("falha", motivo="entrada_invalida")
        pedido[item["produto_id"]] = pedido.get(item["produto_id"], 0) + item["quantidade"]
    if sum(pedido.values()) > MAX_UNIDADES:
        return resultado("falha", motivo="entrada_invalida")
    if not cep_mod.formato_valido(e.cep):
        return resultado("falha", motivo="entrada_invalida")

    loc = cep_mod.localizar(e.cep)
    if loc.estado == "inexistente":
        return resultado("vazio", {"cep": loc.cep}, motivo="cep_inexistente")
    if loc.estado != "ok":
        return resultado("falha", {"cep": loc.cep}, motivo="cep_indisponivel")
    destino = {"cep": loc.cep, "cidade": loc.cidade, "uf": loc.uf}
    cfg = tabelas()
    fontes = _fontes()
    zona = _zona(cfg, loc.uf)
    conn = banco.conectar()
    try:
        produtos = {}
        for pid in pedido:
            linha = conn.execute("SELECT p.*, c.nome AS categoria FROM produtos p "
                                 "JOIN categorias c ON c.id = p.categoria_id WHERE p.id = ?", (pid,)).fetchone()
            if linha is None:
                return resultado("vazio", fontes=[FONTE_BANCO], motivo="produto_nao_encontrado")
            produtos[pid] = linha
    finally:
        conn.close()

    if cep_mod.eh_cidade_base(loc.cidade, loc.uf):  # regra da loja, não simulação: promoções valem, PIX não
        valor = 0
        for pid, qtd in pedido.items():
            c = calcular_condicoes(produto_id=pid, forma="boleto")
            if c.estado != "ok":
                return resultado("falha", fontes=fontes, motivo="erro_interno")
            valor += c.dados["final_centavos"] * qtd
        f = calcular_condicoes(valor=valor, forma="boleto", cidade=loc.cidade, uf=loc.uf, valor_pedido=valor)
        if f.estado != "ok":
            return resultado("falha", fontes=fontes, motivo="erro_interno")
        return resultado("ok", {**destino, "situacao": "cidade_base", "simulacao": False, "produtos_centavos": valor,
                                "frete": f.dados["frete"]}, fontes + f.fontes)

    caixas, sem_valor = [], []
    for pid, qtd in pedido.items():
        chave, motivo = _caixa_do_produto(cfg, produtos[pid], produtos[pid]["categoria"])
        if chave is None:
            sem_valor.append({"produto_id": pid, "nome": produtos[pid]["nome"], "motivo": motivo})
        else:
            caixas.append({"produto_id": pid, "nome": produtos[pid]["nome"], "caixa": chave, "quantidade": qtd})
    base = {**destino, "simulacao": True, "aviso": cfg["aviso"]}
    if sem_valor or zona is None:
        return resultado("ok", {**base, "situacao": "cotacao_individual", "itens_sem_valor": sem_valor,
                                "modalidades": []}, fontes)

    modalidades = []
    for m in cfg["modalidades"]:
        total = sum(_preco_caixa(cfg, zona, cfg["caixas"][c["caixa"]], m) * c["quantidade"] for c in caixas)
        modalidades.append({"id": m["id"], "nome": m["nome"], "valor_centavos": total,
                            "prazo_dias_uteis": _prazo_do_manual(m["nome"]), "principal": bool(m.get("principal"))})
    detalhe = [{**c, "peso_taxado_kg": _peso_taxado_kg(cfg, cfg["caixas"][c["caixa"]])} for c in caixas]
    return resultado("ok", {**base, "situacao": "estimado", "zona": zona["id"], "modalidades": modalidades,
                            "caixas": detalhe}, fontes)
