"""Canais e contato (decisao final): links padrao derivados do manual; faixa com endereco resumido."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from emporio.politicas.manual import fato
from emporio.web.app import criar_app

VARIAVEIS = ("EMPORIO_WHATSAPP_URL", "EMPORIO_TELEFONE_LINK", "EMPORIO_EMAIL_LINK")


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    for v in VARIAVEIS:
        monkeypatch.delenv(v, raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


def faixa(html: str) -> str:
    i = html.index('class="contorno faixa-contato"')
    return html[i:html.index("</section>", i)]


def test_faixa_sem_endereco_e_com_o_horario_derivado_do_manual(cliente):
    e = fato("empresa.endereco").valor
    f = faixa(cliente.get("/").text)
    assert e["logradouro"] not in f and e["cep"] not in f and e["bairro"] not in f
    assert "Seg. a sex., das 9h às 18h" in f  # horário no formato do site, vindo do manual


def test_botao_da_faixa_vai_a_fale_conosco_e_a_pagina_responde(cliente):
    f = faixa(cliente.get("/").text)
    assert re.search(r'<a class="botao" href="/fale-conosco">Fale conosco</a>', f)
    assert cliente.get("/fale-conosco").status_code == 200


def digitos(chave: str) -> str:
    return re.sub(r"\D", "", str(fato(chave).valor))


def wa() -> str:
    return f"https://wa.me/55{digitos('contato.whatsapp_secao_7')}"


def tel() -> str:
    return f"tel:+55{digitos('contato.telefone_capa')}"


def test_faixa_telefone_com_tel_e_icone_do_whatsapp_em_nova_aba(cliente):
    f = faixa(cliente.get("/").text)
    assert f'href="{tel()}"' in f and str(fato("contato.telefone_capa").valor) in f
    m = re.search(r'<a [^>]*href="' + re.escape(wa()) + r'"[^>]*>', f)
    assert m and 'target="_blank"' in m.group(0) and "noopener" in m.group(0) and "aria-label=" in m.group(0)
    assert "#whatsapp" in f and "mailto:" not in f


def test_fale_conosco_tem_wa_me_em_nova_aba_tel_e_mailto(cliente):
    html = cliente.get("/fale-conosco").text
    m = re.search(r'<a [^>]*href="' + re.escape(wa()) + r'"[^>]*>', html)
    assert m and 'target="_blank"' in m.group(0) and "noopener" in m.group(0)
    assert f'href="{tel()}"' in html


def test_variaveis_de_ambiente_substituem_os_padroes_na_faixa_e_na_pagina(cliente, monkeypatch):
    monkeypatch.setenv("EMPORIO_WHATSAPP_URL", "https://wa.me/5500000000000")
    monkeypatch.setenv("EMPORIO_TELEFONE_LINK", "tel:+550000000000")
    pagina = cliente.get("/fale-conosco").text
    f = faixa(cliente.get("/").text)
    for texto in (pagina, f):
        assert 'href="https://wa.me/5500000000000"' in texto and 'href="tel:+550000000000"' in texto
        assert wa() not in texto and tel() not in texto


def test_enviar_email_com_mailto_do_manual_e_unico_link_de_canal(cliente):
    html = cliente.get("/fale-conosco").text
    email = fato("contato.email_capa").valor
    assert html.count("mailto:") == 1
    assert re.search(rf'<a [^>]*href="mailto:{re.escape(email)}"[^>]*>Enviar e-mail</a>', html)


def test_variavel_do_telefone_da_faixa_vira_link(cliente, monkeypatch):
    monkeypatch.setenv("EMPORIO_TELEFONE_LINK", "tel:+550000000000")
    assert 'href="tel:+550000000000"' in faixa(cliente.get("/").text)


def test_variavel_do_email_substitui_o_mailto_padrao(cliente, monkeypatch):
    monkeypatch.setenv("EMPORIO_EMAIL_LINK", "mailto:outro@example.com")
    html = cliente.get("/fale-conosco").text
    assert 'href="mailto:outro@example.com"' in html and html.count("mailto:") == 1


def test_rodape_sem_fale_conosco_e_termina_em_politicas_e_privacidade(cliente):
    html = cliente.get("/").text
    rodape = html[html.index('<footer class="rodape">'):html.index("</footer>")]
    assert "Fale conosco" not in rodape and "/fale-conosco" not in rodape
    links = re.findall(r"<a [^>]*>([^<]+)</a>", rodape)  # rodapé compacto: sem títulos de coluna, links em linha única
    assert links[-2:] == ["Políticas da Loja", "Privacidade e cookies"]


@pytest.mark.parametrize("caminho", ["/perguntas-frequentes", "/privacidade"])
def test_faq_e_privacidade_ainda_levam_a_fale_conosco(cliente, caminho):
    assert 'href="/fale-conosco' in cliente.get(caminho).text


def test_nenhum_numero_literal_nos_py_do_site():
    from pathlib import Path
    for p in (Path(__file__).resolve().parents[1] / "src" / "emporio" / "web").glob("*.py"):
        t = p.read_text(encoding="utf-8")
        assert "3341" not in t and "3321" not in t and "Campo Grande" not in t


def _privacidade(cliente) -> str:
    from emporio.web.app import criar_app  # noqa: F401
    html = cliente.get("/privacidade").text
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_privacidade_diz_quando_nasce_o_cookie_e_que_nao_ha_prazo_automatico(cliente):
    t = _privacidade(cliente)
    assert "primeira visita" in t
    assert "não tem prazo automático de exclusão" in t and "até você pedir a exclusão" in t


def test_privacidade_explica_enviar_email_e_links_para_fora_do_site(cliente):
    t = _privacidade(cliente)
    assert "Enviar e-mail" in t and "aplicativo de e-mail" in t
    assert "WhatsApp" in t and "fora do site" in t


def test_privacidade_sem_jargao_nem_base_legal_ou_prazo_inventado(cliente):
    t = _privacidade(cliente).lower()
    for termo in ("samesite", "sessionstorage", "base legal", "legítimo interesse", "prazo de retenção"):
        assert termo not in t, termo
