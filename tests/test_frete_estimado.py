"""estimar_frete: simulação determinística, com tabelas em YAML próprio (SPEC, etapa 8)."""
from __future__ import annotations

import shutil

import pytest
import yaml

from emporio import config
from emporio.ferramentas import cep as cep_mod
from emporio.ferramentas.envelope import Resultado
from emporio.ferramentas.frete import estimar_frete

VIOLAO, GUITARRA, TECLADO_61, UKULELE_TENOR, UKULELE_SOPRANO, BAIXO, BATERIA = 81, 131, 142, 124, 117, 135, 139
LOCAIS = {
    "79800000": ("Dourados", "MS"), "01310100": ("São Paulo", "SP"), "50030230": ("Recife", "PE"),
    "69010001": ("Manaus", "AM"), "59000000": ("Campo Grande", "RN"), "79002000": ("Campo Grande", "MS"),
    "20040020": ("Rio de Janeiro", "RJ"), "66010000": ("Belém", "PA"),
}


@pytest.fixture(autouse=True)
def cep_falso(monkeypatch):
    monkeypatch.setenv("EMPORIO_CEP_EXTERNO", "1")
    cep_mod._memoria.clear()

    def falso(digitos):
        if digitos == "99999999":
            return {"erro": "true"}
        if digitos not in LOCAIS:
            raise OSError("fora do ar")
        cidade, uf = LOCAIS[digitos]
        return {"localidade": cidade, "uf": uf, "logradouro": "Rua A", "bairro": "Centro"}

    monkeypatch.setattr(cep_mod, "_consultar_externo", falso)
    yield
    cep_mod._memoria.clear()


def estimar(cep, *itens):
    return estimar_frete(itens=[{"produto_id": p, "quantidade": q} for p, q in itens], cep=cep)


def valores(r):
    return {m["id"]: m["valor_centavos"] for m in r.dados["modalidades"]}


@pytest.mark.parametrize("cep,item,pac,sedex", [
    ("79800-000", (VIOLAO, 1), 5559, 8223),       # Dourados, violão, 14 kg
    ("01310-100", (GUITARRA, 1), 6219, 9279),     # São Paulo, guitarra, 11 kg
    ("50030-230", (TECLADO_61, 1), 9219, 14079),  # Recife, teclado de 61 teclas, 16 kg
    ("69010-001", (UKULELE_TENOR, 1), 5400, 8640),  # Manaus, ukulele tenor, 6 kg
])
def test_exemplos_numericos_da_spec(cep, item, pac, sedex):
    r = estimar(cep, item)
    assert isinstance(r, Resultado) and r.estado == "ok" and r.dados["situacao"] == "estimado"
    assert valores(r) == {"economica": pac, "expressa": sedex}


def test_peso_taxado_e_o_maior_entre_real_e_cubado():
    d = {c["produto_id"]: c["peso_taxado_kg"] for c in estimar("79800-000", (VIOLAO, 1), (GUITARRA, 1),
                                                               (TECLADO_61, 1), (UKULELE_SOPRANO, 1)).dados["caixas"]}
    assert d == {VIOLAO: 14, GUITARRA: 11, TECLADO_61: 16, UKULELE_SOPRANO: 4}  # soprano: cubado 3,38 kg, real 1,5 kg


def test_baixo_eletrico_segue_a_formula():
    r = estimar("79800-000", (BAIXO, 1))
    assert valores(r) == {"economica": 5379, "expressa": 7935}  # 128 x 42 x 14 = 12,54 kg -> 13 kg, com adicional


def test_adicional_so_quando_algum_lado_passa_de_100_cm():
    # ukulele tenor: maior lado 80 cm, sem adicional. Manaus: 36,00 + 3,60 x 5 = 54,00
    assert valores(estimar("69010-001", (UKULELE_TENOR, 1)))["economica"] == 5400


def test_pedido_soma_as_caixas_e_cada_unidade_e_uma_caixa():
    a = estimar("79800-000", (VIOLAO, 2), (GUITARRA, 1))
    separado = [estimar("79800-000", (VIOLAO, 1)), estimar("79800-000", (VIOLAO, 1)), estimar("79800-000", (GUITARRA, 1))]
    for modalidade in ("economica", "expressa"):
        assert valores(a)[modalidade] == sum(valores(r)[modalidade] for r in separado)
    assert valores(estimar("79800-000", (VIOLAO, 1), (VIOLAO, 1))) == valores(estimar("79800-000", (VIOLAO, 2)))


def test_prazos_vem_so_do_manual_e_a_transportadora_fica_sem_preco():
    r = estimar("50030-230", (TECLADO_61, 1))
    prazos = {m["id"]: m["prazo_dias_uteis"] for m in r.dados["modalidades"]}
    assert prazos == {"economica": {"min": 5, "max": 12}, "expressa": {"min": 2, "max": 5}}
    assert len(r.dados["modalidades"]) == 2 and r.dados["simulacao"] is True and "Simulação" in r.dados["aviso"]


def test_grande_porte_fica_sem_valor_e_contamina_o_pedido_todo():
    r = estimar("79800-000", (BATERIA, 1))
    assert r.estado == "ok" and r.dados["situacao"] == "cotacao_individual" and r.dados["modalidades"] == []
    assert r.dados["itens_sem_valor"][0]["motivo"] == "grande_porte"
    misto = estimar("79800-000", (VIOLAO, 1), (BATERIA, 1))
    assert misto.dados["situacao"] == "cotacao_individual" and misto.dados["modalidades"] == []


def test_produto_sem_caixa_definida_fica_em_cotacao_individual(tmp_path, monkeypatch):
    cfg = yaml.safe_load(config.caminho_frete_simulado().read_text(encoding="utf-8"))
    cfg["produtos"] = [r for r in cfg["produtos"] if r.get("categoria") != "Violões"]
    alterado = tmp_path / "frete.yaml"
    alterado.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("EMPORIO_FRETE_SIMULADO", str(alterado))
    r = estimar("79800-000", (VIOLAO, 1))
    assert r.dados["situacao"] == "cotacao_individual" and r.dados["itens_sem_valor"][0]["motivo"] == "sem_caixa"


def test_alterar_o_yaml_muda_a_resposta(tmp_path, monkeypatch):
    antes = valores(estimar("79800-000", (VIOLAO, 1)))["economica"]
    cfg = yaml.safe_load(config.caminho_frete_simulado().read_text(encoding="utf-8"))
    cfg["zonas"][0]["base_centavos"] += 1000
    alterado = tmp_path / "frete.yaml"
    alterado.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("EMPORIO_FRETE_SIMULADO", str(alterado))
    assert valores(estimar("79800-000", (VIOLAO, 1)))["economica"] == antes + 1000


def test_campo_grande_do_rio_grande_do_norte_nao_recebe_a_regra_da_base():
    rn = estimar("59000-000", (VIOLAO, 1))
    assert rn.dados["situacao"] == "estimado" and rn.dados["uf"] == "RN" and rn.dados["zona"] == "z4"
    ms = estimar("79002-000", (VIOLAO, 1))
    assert ms.dados["situacao"] == "cidade_base" and "modalidades" not in ms.dados


def test_outras_zonas_usam_a_tabela_da_spec():
    assert valores(estimar("20040-020", (UKULELE_TENOR, 1)))["economica"] == 2900 + 290 * 5   # z3: 6 kg
    assert valores(estimar("66010-000", (UKULELE_TENOR, 1)))["economica"] == 3600 + 360 * 5   # z5


def test_servico_de_cep_fora_do_ar_nao_inventa_valor():
    r = estimar("30140-071", (VIOLAO, 1))  # CEP que o dublê não conhece: rede caiu
    assert r.estado == "falha" and r.motivo == "cep_indisponivel" and "modalidades" not in r.dados


def test_cep_inexistente_invalido_e_entradas_ruins():
    assert estimar("99999-999", (VIOLAO, 1)).estado == "vazio"
    assert estimar("123", (VIOLAO, 1)).motivo == "entrada_invalida"
    assert estimar("79800-000", (VIOLAO, 0)).motivo == "entrada_invalida"
    assert estimar_frete(itens=[], cep="79800-000").motivo == "entrada_invalida"
    assert estimar("79800-000", (99999, 1)).estado == "vazio"
    assert estimar_frete(itens=[{"produto_id": VIOLAO, "quantidade": 1}], cep="79800-000",
                         forma="pix").motivo == "entrada_invalida"  # a forma de pagamento nunca entra no frete


def test_e_deterministico():
    a, b = estimar("50030-230", (TECLADO_61, 1)), estimar("50030-230", (TECLADO_61, 1))
    assert a.dados == b.dados


def test_cidade_base_devolve_a_regra_da_loja_pelo_preco_com_promocao_e_sem_pix():
    ms = estimar("79002-000", (UKULELE_SOPRANO, 1))
    assert ms.dados["frete"]["situacao"] == "taxa" and ms.dados["frete"]["taxa_centavos"] == 3500
    caro = estimar("79002-000", (UKULELE_TENOR, 1), (GUITARRA, 1), (TECLADO_61, 1))
    assert caro.dados["frete"]["situacao"] == "gratis" and caro.dados["produtos_centavos"] >= 50000


def test_calcular_condicoes_compara_cidade_e_uf_quando_a_uf_vem():
    from emporio.ferramentas.condicoes import calcular_condicoes

    base = dict(valor=60000, forma="boleto", cidade="Campo Grande", valor_pedido=60000)
    assert calcular_condicoes(**base, uf="MS").dados["frete"]["situacao"] == "gratis"
    assert calcular_condicoes(**base, uf="RN").dados["frete"]["situacao"] == "cotacao_necessaria"
    assert calcular_condicoes(**base).dados["frete"]["situacao"] == "gratis"
