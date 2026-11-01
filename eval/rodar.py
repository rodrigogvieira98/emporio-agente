"""Roda os casos pré-registrados e relata contagens.

Uso: python eval/rodar.py --conjunto dev --rotulo controle
O holdout exige --holdout-congelado e confere o hash do pré-registro.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FATOS = {"preco", "promocao", "cruzado", "pedido", "seguranca"}
NAO_ENTENDI = "resposta_nao_entendi"


def norm(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in base if not unicodedata.combining(c))


def hash_holdout(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def conferir_holdout(caminho: Path) -> None:
    pre = (RAIZ / "eval" / "PREREGISTRO.md").read_text(encoding="utf-8")
    esperado = re.search(r"holdout\.jsonl`: ([0-9a-f]{64})", pre).group(1)
    if hash_holdout(caminho) != esperado:
        sys.exit("Hash do holdout difere do pré-registro.")


def avaliar(caso: dict, respostas: list, chamados: int) -> dict:
    final = norm(respostas[-1].texto)
    todas = [a for r in respostas for a in r.acoes]
    usadas = {a.get("ferramenta") for a in todas if a.get("ferramenta")}
    faltou = [c for c in caso.get("contem", []) if norm(c) not in final]
    proibido = [c for c in caso.get("nao_contem", []) if norm(c) in final]
    falta_ferr = [f for f in caso.get("ferramentas", []) if f not in usadas]
    ferr_proib = [f for f in caso.get("proibe_ferramentas", []) if f in usadas]
    esperado_chamado = caso.get("chamado")
    chamado_ok = esperado_chamado is None or esperado_chamado == (chamados > 0)
    return {
        "id": caso["id"],
        "cat": caso["cat"],
        "ok": not (faltou or proibido or falta_ferr or ferr_proib) and chamado_ok,
        "fato_ok": not (faltou or proibido),
        "acao_ok": not (falta_ferr or ferr_proib),
        "chamado_ok": chamado_ok,
        "chamado_perdido": esperado_chamado is True and chamados == 0,
        "chamado_indevido": esperado_chamado is False and chamados > 0,
        "nao_entendeu": any(a.get("resposta") == "nao_entendi" for a in todas),
        "faltou": faltou,
        "proibido": proibido,
        "falta_ferramenta": falta_ferr,
        "ferramenta_proibida": ferr_proib,
        "caracteres": len(respostas[-1].texto),
        "resposta": respostas[-1].texto,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--conjunto", choices=("dev", "holdout"), required=True)
    p.add_argument("--rotulo", required=True)
    p.add_argument("--holdout-congelado", action="store_true")
    a = p.parse_args()
    caminho = RAIZ / "eval" / f"casos_{a.conjunto}.jsonl"
    if a.conjunto == "holdout":
        if not a.holdout_congelado:
            sys.exit("Holdout roda uma vez, no sistema congelado: use --holdout-congelado.")
        conferir_holdout(caminho)
    casos = [json.loads(l) for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]

    from emporio.agente.laco import Agente
    from emporio.dados import carga

    tmp = Path(tempfile.mkdtemp(prefix="emporio-eval-"))
    modelo = tmp / "modelo.db"
    carga.carregar(RAIZ / "data" / "raw", modelo)
    resultados = []
    for caso in casos:
        db = tmp / f"{caso['id']}.db"
        shutil.copy(modelo, db)
        os.environ["EMPORIO_DB"] = str(db)
        os.environ["EMPORIO_TRACE"] = str(tmp / "trace.jsonl")
        os.environ["EMPORIO_DATA_REFERENCIA"] = caso.get("data_ref", "2026-03-25T10:00:00")
        agente = Agente()
        inicio = time.perf_counter()
        try:
            respostas = [agente.responder(caso["id"], m, "eval") for m in caso["turnos"]]
            import sqlite3

            with sqlite3.connect(db) as c:
                chamados = c.execute("SELECT COUNT(*) FROM chamados").fetchone()[0]
            r = avaliar(caso, respostas, chamados)
        except Exception as exc:  # falha técnica vira contagem, não aborta a rodada
            r = {"id": caso["id"], "cat": caso["cat"], "ok": False, "fato_ok": False, "acao_ok": False,
                 "chamado_ok": False, "chamado_perdido": False, "chamado_indevido": False,
                 "nao_entendeu": False, "excecao": repr(exc)[:200], "caracteres": 0}
        r["segundos"] = round(time.perf_counter() - inicio, 3)
        resultados.append(r)

    n = len(resultados)
    fatos = [r for r in resultados if r["cat"] in FATOS]
    espera_chamado = [c["id"] for c in casos if c.get("chamado") is True]
    resumo = {
        "rotulo": a.rotulo,
        "conjunto": a.conjunto,
        "casos": n,
        "conclusao": f"{sum(r['ok'] for r in resultados)}/{n}",
        "fatos_criticos_errados": f"{sum(not r['fato_ok'] for r in fatos)}/{len(fatos)}",
        "escolha_de_acoes": f"{sum(r['acao_ok'] for r in resultados)}/{n}",
        "bloqueios_indevidos": f"{sum(r['nao_entendeu'] for r in resultados)}/{n}",
        "chamados_perdidos": f"{sum(r['chamado_perdido'] for r in resultados)}/{len(espera_chamado)}",
        "chamados_indevidos": sum(r["chamado_indevido"] for r in resultados),
        "falhas_tecnicas": sum("excecao" in r for r in resultados),
        "caracteres_mediana": sorted(r["caracteres"] for r in resultados)[n // 2],
        "por_categoria": dict(sorted(Counter(r["cat"] for r in resultados if r["ok"]).items())),
        "total_categoria": dict(sorted(Counter(r["cat"] for r in resultados).items())),
    }
    pasta = RAIZ / "eval" / "resultados"
    pasta.mkdir(exist_ok=True)
    saida = pasta / f"{a.conjunto}_{a.rotulo}.json"
    saida.write_text(json.dumps({"resumo": resumo, "casos": resultados}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=1))
    for r in resultados:
        if not r["ok"]:
            print("FALHOU", r["id"], {k: r[k] for k in ("faltou", "proibido", "falta_ferramenta", "ferramenta_proibida", "excecao") if r.get(k)},
                  "chamado" if not r["chamado_ok"] else "", "|", r.get("resposta", "")[:150].replace("\n", " "))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
