"""A carga falha com mensagem clara e não deixa banco parcial."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from emporio.dados.carga import CargaErro, carregar

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


@pytest.fixture
def raw_copia(tmp_path):
    destino = tmp_path / "raw"
    shutil.copytree(RAW, destino, ignore=shutil.ignore_patterns("*.pdf"))
    return destino


def _trocar(arquivo: Path, antigo: str, novo: str):
    texto = arquivo.read_text(encoding="utf-8")
    assert antigo in texto
    arquivo.write_text(texto.replace(antigo, novo, 1), encoding="utf-8")


def test_chave_orfa_de_categoria(raw_copia, tmp_path):
    _trocar(raw_copia / "products.csv", "Yamaha C40 Nylon Natural,5,", "Yamaha C40 Nylon Natural,99,")
    with pytest.raises(CargaErro, match="categoria 99 nao existe"):
        carregar(raw_copia, tmp_path / "x.db")
    assert not (tmp_path / "x.db").exists() and not (tmp_path / "x.tmp").exists()


def test_chave_orfa_de_item_de_pedido(raw_copia, tmp_path):
    with (raw_copia / "order_items.csv").open("a", encoding="utf-8") as f:
        f.write("\n99,1,93")
    with pytest.raises(CargaErro, match="pedido 99 nao existe"):
        carregar(raw_copia, tmp_path / "x.db")


def test_preco_invalido(raw_copia, tmp_path):
    _trocar(raw_copia / "products.csv", "81,599.9,", "81,abc,")
    with pytest.raises(CargaErro, match="preco invalido"):
        carregar(raw_copia, tmp_path / "x.db")


def test_preco_zero_ou_negativo(raw_copia, tmp_path):
    _trocar(raw_copia / "products.csv", "81,599.9,", "81,-10,")
    with pytest.raises(CargaErro, match="preco invalido"):
        carregar(raw_copia, tmp_path / "x.db")


def test_json_invalido_em_specs(raw_copia, tmp_path):
    _trocar(raw_copia / "products.csv", '{""top"":""Spruce""', '{""top"":""Spruce""!!')
    with pytest.raises(CargaErro, match="JSON invalido em specs"):
        carregar(raw_copia, tmp_path / "x.db")


def test_arquivo_ausente(raw_copia, tmp_path):
    (raw_copia / "orders.csv").unlink()
    with pytest.raises(CargaErro, match="arquivo ausente"):
        carregar(raw_copia, tmp_path / "x.db")


def test_dinheiro_vira_centavos_inteiros(sql):
    assert sql.execute("SELECT preco_centavos FROM produtos WHERE id = 81").fetchone()[0] == 59990
    assert sql.execute("SELECT total_centavos FROM pedidos WHERE id = 4").fetchone()[0] == 79990
    tipos = {r[0] for r in sql.execute("SELECT DISTINCT typeof(preco_centavos) FROM produtos")}
    assert tipos == {"integer"}
