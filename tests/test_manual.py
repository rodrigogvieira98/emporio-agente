"""Fonte do manual: fidelidade ao PDF, consultar_politica, fato() e troca do YAML."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

from emporio import config
from emporio.ferramentas.condicoes import calcular_condicoes
from emporio.ferramentas.politica import consultar_politica
from emporio.politicas import manual

RAIZ = Path(__file__).resolve().parents[1]
PDF = RAIZ / "data" / "raw" / "politicas_da_loja.pdf"


def _palavras(texto: str) -> list[str]:
    texto = texto.replace("•", " ").replace("|", " ")
    return re.findall(r"[0-9a-zà-ÿ]+", texto.lower())


def _palavras_do_pdf() -> list[str]:
    paginas = [p.extract_text() for p in PdfReader(PDF).pages]
    saida: list[str] = []
    for texto in paginas:
        corpo = " ".join(texto.split())
        corpo = re.sub(r"Empório da Música Manual de Políticas e Procedimentos", " ", corpo)  # cabeçalho
        corpo = re.sub(r"Página \d+", " ", corpo)  # rodapé
        saida += _palavras(corpo)
    return saida


def test_transcricao_fiel_ao_pdf():
    """Todas as palavras do PDF, na mesma ordem, estão no texto das seções."""
    # cabeçalho de seção ("2. Horário de Funcionamento") vem no título, não no texto
    do_yaml: list[str] = []
    for s in manual.carregar_manual().secoes:
        if s.id != "capa":
            do_yaml += _palavras(f"{s.id}. {s.titulo}")
        do_yaml += _palavras(s.texto)
    do_pdf = _palavras_do_pdf()
    # a capa vem primeiro no PDF e no YAML, e o cabeçalho "Campo Informação" da tabela 1.2 está no texto
    assert do_yaml == do_pdf, _primeira_diferenca(do_yaml, do_pdf)


def _primeira_diferenca(a: list[str], b: list[str]) -> str:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"posicao {i}: yaml={a[max(0, i - 4):i + 4]} pdf={b[max(0, i - 4):i + 4]}"
    return f"tamanhos diferentes: yaml={len(a)} pdf={len(b)}"


def test_versao_e_secoes_do_manual():
    m = manual.carregar_manual()
    assert m.versao == "2.1"
    ids = [s.id for s in m.secoes]
    assert len(ids) == len(set(ids))
    for esperado in ("1", "2", "3", "3.1", "4.1", "4.2", "4.3", "4.4", "5.1", "5.2", "5.3", "6.1", "6.2",
                     "7", "7.1", "7.2", "7.3", "8.1", "8.2", "8.3", "9", "10"):
        assert esperado in ids


def test_procedimento_interno_nao_e_publico():
    m = manual.carregar_manual()
    internos = {s.id for s in m.secoes if not s.publico}
    assert {"7.1", "7.2", "7.3", "capa", "10"} == internos
    assert m.secao("4.1").publico and m.secao("2").publico


def test_onze_ambiguidades_declaradas():
    ids = {a.id for a in manual.carregar_manual().ambiguidades}
    assert ids == {"telefone_whatsapp", "email", "parcela_minima", "excecao_abaixo_50", "frete_exatamente_500",
                   "regiao_metropolitana_sem_lista", "marco_troca_preferencia", "prazo_30_x_90",
                   "total_300_instrumentos", "lojas_parceiras_sem_lista", "feriados_sem_calendario"}
    secoes = {s.id for s in manual.carregar_manual().secoes}
    for a in manual.carregar_manual().ambiguidades:
        assert set(a.secoes) <= secoes


def test_quatro_regras_com_marco_e_dados_necessarios():
    regras = {c: manual.valor(f"regra.{c}") for c in ("arrependimento", "preferencia", "defeito", "garantia_legal")}
    assert (regras["arrependimento"]["prazo_dias"], regras["arrependimento"]["marco_inicial"]) == (7, "recebimento")
    assert regras["arrependimento"]["aplica_a"] == "compra_online"
    assert regras["preferencia"]["marco_inicial"] == "nao_informado"
    assert (regras["defeito"]["prazo_dias"], regras["defeito"]["marco_inicial"]) == (30, "compra")
    assert (regras["garantia_legal"]["prazo_dias"], regras["garantia_legal"]["marco_inicial"]) == (90, "recebimento")
    for r in regras.values():
        assert r["dados_necessarios"]


# consultar_politica ----------------------------------------------------------------

def test_politica_ok_traz_secao_com_hash_versao_texto_condicoes_e_ambiguidades():
    r = consultar_politica(["parcelamento"])
    assert r.estado == "ok"
    s = r.dados["secoes"][0]
    assert s["id"] == "3.1" and s["versao"] == "2.1" and len(s["hash"]) == 64
    assert "parcela mínima" in s["texto"] and s["condicoes"]
    assert {a["id"] for a in s["ambiguidades"]} == {"parcela_minima", "excecao_abaixo_50"}
    assert r.fontes[0].tipo == "manual" and r.fontes[0].versao == "2.1"


def test_politica_varios_temas_e_tema_desconhecido_misturado():
    r = consultar_politica(["horario", "Garantia", "xyz"])
    assert r.estado == "ok" and r.dados["temas_desconhecidos"] == ["xyz"]
    assert {s["id"] for s in r.dados["secoes"]} >= {"2", "8.1", "4.2"}


def test_politica_vazio_para_tema_desconhecido():
    r = consultar_politica(["astrologia"])
    assert r.estado == "vazio" and r.motivo == "tema_desconhecido"


def test_politica_falha_entrada_invalida():
    for ruim in ([], [""], "horario", None, [1]):
        assert consultar_politica(ruim).motivo == "entrada_invalida"


def test_politica_nao_repassa_texto_de_procedimento_interno_mas_mantem_condicoes():
    r = consultar_politica(["reclamacao"])
    s = next(x for x in r.dados["secoes"] if x["id"] == "7.3")
    assert s["publico"] is False and s["texto"] is None
    assert any(c["chave"] == "atendimento.prazo_retorno_reclamacao_horas_uteis" and c["valor"] == 24
               for c in s["condicoes"])


def test_politica_contato_traz_as_duas_ambiguidades_ligadas():
    r = consultar_politica(["contato"])
    achadas = {a["id"] for s in r.dados["secoes"] for a in s["ambiguidades"]}
    assert {"telefone_whatsapp", "email"} <= achadas


def test_politica_nunca_negado_nem_ambiguo():
    assert consultar_politica(["horario"]).estado == "ok"


# fato() ----------------------------------------------------------------------------

def test_fato_serve_resposta_rapida_com_fonte():
    f = manual.fato("pagamento.pix_desconto_percentual")
    assert f.valor == 5 and f.fonte.tipo == "manual" and f.fonte.referencia == "secao 3" and f.fonte.versao == "2.1"
    assert manual.fato("frete.taxa_abaixo_centavos").valor == 3500
    assert manual.fato("chave.que.nao.existe") is None


def test_hash_da_secao_muda_quando_o_conteudo_muda(tmp_path, monkeypatch):
    antes = manual.carregar_manual().secao("3").hash
    copia = _copia_yaml(tmp_path, monkeypatch, "pix_desconto_percentual, valor: 5", "pix_desconto_percentual, valor: 7")
    assert copia.exists()
    depois = manual.carregar_manual().secao("3").hash
    assert antes != depois and manual.carregar_manual().secao("2").hash == manual.carregar_manual().secao("2").hash


# YAML alterado muda a resposta --------------------------------------------------------

def _copia_yaml(tmp_path, monkeypatch, antigo: str, novo: str) -> Path:
    origem = Path(__file__).resolve().parents[1] / "src" / "emporio" / "politicas" / "manual_v2_1.yaml"
    texto = origem.read_text(encoding="utf-8")
    assert antigo in texto
    destino = tmp_path / "manual_alterado.yaml"
    destino.write_text(texto.replace(antigo, novo, 1), encoding="utf-8")
    monkeypatch.setenv("EMPORIO_MANUAL", str(destino))
    return destino


def test_alterar_o_yaml_muda_o_calculo_e_o_fato(tmp_path, monkeypatch):
    assert calcular_condicoes(produto_id=95, forma="pix").dados["final_centavos"] == 208905
    _copia_yaml(tmp_path, monkeypatch, "pix_desconto_percentual, valor: 5", "pix_desconto_percentual, valor: 10")
    assert calcular_condicoes(produto_id=95, forma="pix").dados["final_centavos"] == 197910
    assert manual.fato("pagamento.pix_desconto_percentual").valor == 10


def test_alterar_o_yaml_muda_frete_e_parcela_minima(tmp_path, monkeypatch):
    _copia_yaml(tmp_path, monkeypatch, "taxa_abaixo_centavos, valor: 3500", "taxa_abaixo_centavos, valor: 4200")
    frete = calcular_condicoes(valor=10000, forma="boleto", cidade="Campo Grande").dados["frete"]
    assert frete["taxa_centavos"] == 4200


def test_alterar_o_yaml_muda_a_consulta_de_politica(tmp_path, monkeypatch):
    antes = consultar_politica(["horario"]).dados["secoes"][0]
    _copia_yaml(tmp_path, monkeypatch, 'abre: "09:00", fecha: "18:00"', 'abre: "08:00", fecha: "18:00"')
    depois = consultar_politica(["horario"]).dados["secoes"][0]
    assert antes["hash"] != depois["hash"]
    assert depois["condicoes"][0]["valor"][0]["abre"] == "08:00"


def test_yaml_quebrado_vira_falha_e_nao_excecao(tmp_path, monkeypatch):
    ruim = tmp_path / "ruim.yaml"
    ruim.write_text("manual: {versao: '2.1'}\n", encoding="utf-8")  # sem secoes e sem titulo
    monkeypatch.setenv("EMPORIO_MANUAL", str(ruim))
    assert consultar_politica(["horario"]).estado == "falha"
    assert calcular_condicoes(produto_id=95, forma="pix").estado == "falha"


def test_chave_ausente_no_yaml_vira_falha_dado_ausente(tmp_path, monkeypatch):
    origem = Path(config.caminho_manual()).read_text(encoding="utf-8")
    dados = yaml.safe_load(origem)
    for s in dados["secoes"]:
        s["condicoes"] = [c for c in s["condicoes"] if c["chave"] != "pagamento.pix_desconto_percentual"]
    p = tmp_path / "sem_pix.yaml"
    p.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("EMPORIO_MANUAL", str(p))
    r = calcular_condicoes(produto_id=95, forma="pix")
    assert r.estado == "falha" and r.motivo == "dado_ausente"

