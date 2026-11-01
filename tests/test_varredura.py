"""Varredura: nenhum fato de loja pode viver em arquivo .py. Eles ficam no YAML e no banco."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Iterator

import yaml

SRC = Path(__file__).resolve().parents[1] / "src" / "emporio"
YAML = SRC / "politicas" / "manual_v2_1.yaml"

PADROES_PROIBIDOS = {
    "telefone": re.compile(r"\(?\d{2}\)?\s?\d{4,5}-\d{4}"),
    "cep": re.compile(r"\b\d{5}-\d{3}\b"),
    "cnpj": re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"),
    "dinheiro_literal": re.compile(r"R\$\s?\d"),
    "horario": re.compile(r"\b\d{1,2}:\d{2}\b"),
    "email": re.compile(r"[\w.]+@[\w]+\.[a-z]{2,}"),
    "nome_da_loja": re.compile(r"Emp[óo]rio da M[úu]sica|emporiodamusica", re.I),
    "cidade_e_rua": re.compile(r"Campo Grande|Rua 14|Jadlog|Correios|SEDEX", re.I),
    "porcentagem_de_regra": re.compile(r"\b\d+\s?% de desconto"),
}


def _valores(no: Any) -> Iterator[Any]:
    if isinstance(no, dict):
        for v in no.values():
            yield from _valores(v)
    elif isinstance(no, list):
        for v in no:
            yield from _valores(v)
    else:
        yield no


def _fatos_do_yaml() -> tuple[set[str], set[int]]:
    """Textos e números que o manual define, para procurar nos .py."""
    dados = yaml.safe_load(YAML.read_text(encoding="utf-8"))
    textos: set[str] = set()
    numeros: set[int] = set()
    for secao in dados["secoes"]:
        for cond in secao.get("condicoes") or []:
            for v in _valores(cond["valor"]):
                if isinstance(v, str) and (" " in v or any(c.isdigit() for c in v)) and len(v) >= 8:
                    textos.add(v)
                elif isinstance(v, int) and not isinstance(v, bool) and v >= 1000:
                    numeros.add(v)
    return textos, numeros


def _arquivos() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py"))


def achar_violacoes(fonte: str, textos: set[str], numeros: set[int]) -> list[str]:
    achados = [nome for nome, p in PADROES_PROIBIDOS.items() if p.search(fonte)]
    achados += [f"texto do manual: {t!r}" for t in textos if t in fonte]
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.Constant) and isinstance(no.value, int) and not isinstance(no.value, bool) \
                and no.value in numeros:
            achados.append(f"numero do manual: {no.value}")
    return achados


def test_nenhum_fato_de_loja_em_arquivos_py():
    textos, numeros = _fatos_do_yaml()
    assert len(textos) >= 8 and {3500, 50000, 10000, 200000} <= numeros  # a varredura sabe o que procurar
    violacoes = {}
    for arquivo in _arquivos():
        achados = achar_violacoes(arquivo.read_text(encoding="utf-8"), textos, numeros)
        if achados:
            violacoes[str(arquivo.relative_to(SRC))] = achados
    assert violacoes == {}


def test_a_varredura_realmente_pega_violacao():
    textos, numeros = _fatos_do_yaml()
    exemplos = [
        'TELEFONE = "(67) 3341-4444"', 'FRETE = 3500', 'TEXTO = "Frete grátis acima de R$ 500,00"',
        'LOJA = "Empório da Música"', 'ENDERECO = "Rua 14 de Maio, 3200"', 'ABRE = "09:00"',
        'def f():\n    return "contato@emporiodamusica.com.br"', 'LIMITE = 50000',
    ]
    for codigo in exemplos:
        assert achar_violacoes(codigo, textos, numeros), codigo


def test_o_yaml_tem_os_fatos_que_o_codigo_usa():
    """Cada chave que o código consulta existe no manual."""
    chaves = {c["chave"] for s in yaml.safe_load(YAML.read_text(encoding="utf-8"))["secoes"]
              for c in (s.get("condicoes") or [])}
    usadas: set[str] = set()
    for arquivo in _arquivos():
        usadas |= set(re.findall(r'(?:valor|fato)\("([a-z_]+\.[a-z0-9_.]+)"\)', arquivo.read_text(encoding="utf-8")))
    assert usadas and usadas <= chaves, usadas - chaves
