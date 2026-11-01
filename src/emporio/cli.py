"""Conversa pelo terminal: python -m emporio.cli --origem demo"""
from __future__ import annotations

import argparse
import sys
import uuid

from . import config
from .agente.estado import ORIGENS
from .agente.laco import Agente


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="emporio.cli", description="Conversa com a Lia, assistente da loja.")
    ap.add_argument("--origem", required=True, choices=ORIGENS, help="rotulo gravado no trace")
    ap.add_argument("--conversa", default=None, help="id da conversa (padrao: novo)")
    args = ap.parse_args(argv)

    for fluxo in (sys.stdout, sys.stdin):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")
    if not config.caminho_banco().exists():
        print(f"Banco nao encontrado em {config.caminho_banco()}. Rode: python -m emporio.dados.carga", file=sys.stderr)
        return 1

    conversa = args.conversa or f"cli-{uuid.uuid4().hex[:8]}"
    agente = Agente()
    interativo = sys.stdin.isatty()
    if interativo:
        print("Lia, assistente virtual. Digite sua mensagem (vazio ou Ctrl+C para sair).")
    while True:
        try:
            linha = input("Voce: " if interativo else "")
        except (EOFError, KeyboardInterrupt):
            break
        if not linha.strip():
            if interativo:
                break
            continue
        if not interativo:
            print(f"Voce: {linha}")
        resposta = agente.responder(conversa, linha, args.origem)
        print(f"Lia: {resposta.texto}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
