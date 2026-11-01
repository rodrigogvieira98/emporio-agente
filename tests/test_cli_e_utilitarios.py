"""CLI, dinheiro, texto e expediente."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from decimal import Decimal

import pytest

from emporio import config
from emporio.agente import expediente
from emporio.dinheiro import aplicar_desconto, arredondar, dividir, formatar, para_centavos
from emporio.texto import normalizar, radical, tokens


def test_cli_roda_a_devolucao_do_pedido_4(tmp_path):
    entrada = "\n".join(["quero devolver um violão", "pedido 4 final 3456",
                         "online, recebi dia 15/12/2025, na caixa, sem uso", "sim"]) + "\n"
    saida = subprocess.run([sys.executable, "-m", "emporio.cli", "--origem", "demo", "--conversa", "cli-teste"],
                           input=entrada, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert saida.returncode == 0, saida.stderr
    assert "Registrei o seu chamado. Protocolo: EM-000001" in saida.stdout
    assert "O que consta no seu pedido" in saida.stdout and "Lia:" in saida.stdout
    assert '"origem": "demo"' in config.caminho_trace().read_text(encoding="utf-8")


def test_cli_exige_origem_e_valida_valores():
    for args in ([], ["--origem", "producao"]):
        r = subprocess.run([sys.executable, "-m", "emporio.cli", *args], capture_output=True, text=True, input="")
        assert r.returncode == 2


def test_cli_avisa_quando_o_banco_nao_existe(tmp_path, monkeypatch):
    import os
    env = {**os.environ, "EMPORIO_DB": str(tmp_path / "nao_existe.db")}
    r = subprocess.run([sys.executable, "-m", "emporio.cli", "--origem", "demo"], capture_output=True, text=True,
                       input="oi\n", env=env)
    assert r.returncode == 1 and "emporio.dados.carga" in r.stderr


def test_dinheiro_nunca_usa_float_e_arredonda_meio_para_cima():
    assert para_centavos("599.9") == 59990 and para_centavos(Decimal("0.005")) == 1
    with pytest.raises(TypeError):
        para_centavos(599.9)
    assert aplicar_desconto(239900, 18) == 196718 and aplicar_desconto(30, 5) == 29
    assert dividir(54900, 6) == 9150 and dividir(100, 3) == 33 and dividir(101, 2) == 51
    assert arredondar(Decimal("2.5")) == 3
    assert formatar(196718) == "R$ 1.967,18" and formatar(5) == "R$ 0,05" and formatar(123456789) == "R$ 1.234.567,89"


def test_texto_normaliza_acento_caixa_e_plural():
    assert normalizar("  VIOLÕES  Clássicos ") == "violoes classicos"
    assert tokens("Shelby SN-100") == ["shelby", "sn", "100"]
    assert radical("violoes") == "violao" and radical("guitarras") == "guitarra" and radical("sax") == "sax"


FUNCIONAMENTO = [{"dias": [0, 1, 2, 3, 4], "abre": "09:00", "fecha": "18:00"},
                 {"dias": [5], "abre": "09:00", "fecha": "13:00"}, {"dias": [6], "fechado": True}]


@pytest.mark.parametrize("quando,aberto,retorno", [
    ("2026-10-30T09:00:00", True, None),                       # sexta, na abertura
    ("2026-10-30T18:00:00", False, ("sábado", "amanhã", "09:00")),  # sexta, no fechamento
    ("2026-10-31T13:00:00", False, ("segunda-feira", "segunda-feira", "09:00")),
    ("2026-11-01T11:00:00", False, ("segunda-feira", "amanhã", "09:00")),
    ("2026-11-02T08:00:00", False, ("segunda-feira", "hoje", "09:00")),
])
def test_expediente(quando, aberto, retorno):
    r = expediente.situacao(FUNCIONAMENTO, datetime.fromisoformat(quando))
    assert r["aberto"] is aberto
    if retorno:
        assert (r["retorno"]["dia"], r["retorno"]["quando"], r["retorno"]["hora"]) == retorno


def test_descrever_dias():
    assert expediente.descrever_dias([0, 1, 2, 3, 4]) == "segunda a sexta-feira"
    assert expediente.descrever_dias([5]) == "sábado"


def test_data_de_referencia(monkeypatch):
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-02-28")
    assert config.hoje().isoformat() == "2026-02-28"
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-02-28T22:30:00")
    assert config.agora().hour == 22 and config.agora().utcoffset().total_seconds() == -4 * 3600
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "ontem")
    with pytest.raises(ValueError):
        config.agora()
