"""Gera as conversas de exemplo em exemplos/*.md rodando o agente de verdade.

Uso: python exemplos/gerar_conversas.py
Usa a mesma montagem do site (criar_agente). Com EMPORIO_MODELO definido, o modelo redige;
sem ele, só as regras respondem. Banco novo e data de referência fixa, para a conversa ser reproduzível.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

CONVERSAS = [
    ("01_catalogo", "Catálogo com filtro de preço", [
        "Oi! Quais opções de violões disponíveis custando até R$1000?",
        "E ukulele até 200 reais, tem?",
    ]),
    ("02_loja_e_escopo", "Informações da loja e pergunta fora do escopo", [
        "Qual o endereço da loja?",
        "E que horas vocês abrem no sábado?",
        "Vocês vendem cordas também?",
    ]),
    ("03_preco_e_pagamento", "Preço, nome ambíguo, promoção e parcelamento", [
        "Quanto custa um Takamine?",
        "Quanto custa o Takamine GD20?",
        "E o Crafter HT-100 no pix?",
        "Parcela o Shelby SN-100 em 6x?",
    ]),
    ("04_devolucao", "Devolução por arrependimento, com consulta ao pedido e regra da política", [
        "Me arrependi da minha compra, posso devolver meu pedido?",
        "pedido 4, final 3456",
        "Comprei pelo site, recebi anteontem, nem abri",
        "sim",
    ]),
    ("05_reclamacao", "Cliente irritado, reclamação registrada e atendimento humano", [
        "quero abrir reclamação",
        "o violão chegou riscado e ninguém me responde, que absurdo",
        "quero falar com um atendente",
    ]),
]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="emporio-exemplos-"))
    os.environ["EMPORIO_DB"] = str(tmp / "emporio.db")
    os.environ["EMPORIO_TRACE"] = str(tmp / "trace.jsonl")
    os.environ.setdefault("EMPORIO_DATA_REFERENCIA", "2026-03-25T10:00:00")
    os.environ.setdefault("EMPORIO_DECISOR", "regras")

    from emporio.agente.fabrica import criar_agente
    from emporio.dados import carga

    carga.carregar(RAIZ / "data" / "raw", Path(os.environ["EMPORIO_DB"]))
    agente = criar_agente()
    modelo = os.environ.get("EMPORIO_MODELO") or "nenhum (só regras)"
    for nome, titulo, turnos in CONVERSAS:
        linhas = [f"# {titulo}", "",
                  f"Gerada por `exemplos/gerar_conversas.py`. Data de referência {os.environ['EMPORIO_DATA_REFERENCIA']},"
                  f" decisor `{os.environ['EMPORIO_DECISOR']}`, modelo de redação: {modelo}.", ""]
        for msg in turnos:
            r = agente.responder(f"exemplo-{nome}", msg, "demo")
            ferramentas = [a["ferramenta"] for a in r.acoes if a.get("ferramenta")]
            linhas += [f"**Cliente:** {msg}", "", f"**Lia:** {r.texto}".replace("\n", "  \n"), ""]
            if ferramentas:
                linhas += [f"<sub>Ferramentas: {', '.join(dict.fromkeys(ferramentas))}</sub>", ""]
        (RAIZ / "exemplos" / f"{nome}.md").write_text("\n".join(linhas), encoding="utf-8")
        print("gerada", nome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
