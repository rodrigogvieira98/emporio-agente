"""Compara duas rodadas caso a caso. Mesmo placar pode esconder um caso que melhorou e outro que piorou.

Uso: python eval/comparar.py eval/resultados/dev_a.json eval/resultados/dev_b.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def carregar(caminho: str) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def main() -> int:
    a, b = carregar(sys.argv[1]), carregar(sys.argv[2])
    for rodada in (a, b):
        r = rodada["resumo"]
        print(r["rotulo"], r.get("versao", "sem identificação de versão"))
        print("  conclusão", r["conclusao"], "| fatos errados", r["fatos_criticos_errados"], "| tempo", r["tempo_total_s"], "s")
        print("  redação", {k: v for k, v in r.get("contagens", {}).items() if "redacao" in k})

    casos_b = {c["id"]: c for c in b["casos"]}
    melhorou, piorou, texto_mudou = [], [], 0
    for ca in a["casos"]:
        cb = casos_b.get(ca["id"])
        if cb is None:
            print("caso ausente na segunda rodada:", ca["id"])
            continue
        if ca["ok"] != cb["ok"]:
            (melhorou if cb["ok"] else piorou).append(ca["id"])
        if ca.get("resposta") != cb.get("resposta"):
            texto_mudou += 1
    print(f"melhorou ({len(melhorou)}):", melhorou)
    print(f"piorou ({len(piorou)}):", piorou)
    print(f"resposta final diferente em {texto_mudou} de {len(a['casos'])} casos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
