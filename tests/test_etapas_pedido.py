"""Etapa 21: etapas do pedido no padrão de mercado. Site, confirmação e Lia dizem a mesma etapa."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from emporio.agente.laco import Agente
from emporio.ferramentas.etapas_pedido import ANALISE_MINUTOS, STATUS_SITE, etapa_atual, etapas_do_pedido, frase_lia
from emporio.web.app import criar_app

TAKAMINE = 95
CEP = "79002-000"
CINCO = ["Pedido recebido", "Pagamento confirmado", "Em separação", "Enviado", "Entregue"]


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


def texto(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def etapas_na_pagina(html: str) -> list[tuple[str, str]]:
    """(rótulo, estado) de cada item da linha do tempo, na ordem da página."""
    itens = re.findall(r'<li class="etapa etapa-(\w+)"[^>]*>.*?<strong class="etapa-nome">(.*?)</strong>', html, re.S)
    return [(rotulo, estado) for estado, rotulo in itens]


def pedido_do_site(cliente, forma: str, parcelas: str = "1") -> str:
    cliente.post("/carrinho/adicionar", data={"produto_id": TAKAMINE, "quantidade": 1})
    r = cliente.get("/checkout", params={"forma": forma, "parcelas": parcelas, "cep": CEP})
    total = re.search(r'name="total_visto" value="(\d+)"', r.text).group(1)
    feito = cliente.post("/checkout", data={"forma": forma, "parcelas": parcelas, "cep": CEP, "total_visto": total})
    assert feito.status_code == 303
    return feito.headers["location"].rsplit("/", 1)[1]


def atual_na_pagina(html: str) -> str:
    return next(r for r, e in etapas_na_pagina(html) if e == "atual")


# ---- cada forma de pagamento no site ----------------------------------------------------------------------------------

@pytest.mark.parametrize("forma", ["pix", "debito"])
def test_pix_e_debito_ja_aparecem_em_separacao_na_confirmacao_e_no_rastreio(cliente, forma):
    numero = pedido_do_site(cliente, forma)
    esperado = [("Pedido recebido", "feita"), ("Pagamento confirmado", "feita"), ("Em separação", "atual"),
                ("Enviado", "pendente"), ("Entregue", "pendente")]
    assert etapas_na_pagina(cliente.get(f"/pedido/{numero}").text) == esperado
    assert etapas_na_pagina(cliente.post("/rastreio", data={"pedido": numero}).text) == esperado


def test_credito_fica_em_analise_e_depois_de_cinco_minutos_sai_da_analise(cliente, monkeypatch):
    numero = pedido_do_site(cliente, "credito", "3")
    pagina = cliente.get(f"/pedido/{numero}").text
    assert atual_na_pagina(pagina) == "Pagamento em análise"
    assert [r for r, _ in etapas_na_pagina(pagina)] == ["Pedido recebido", "Pagamento em análise", "Em separação",
                                                         "Enviado", "Entregue"]
    assert f"Aprovação em até {ANALISE_MINUTOS} minutos" in texto(pagina)
    # 4 min 59 s depois, ainda em análise
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-10-31T10:04:59")
    assert atual_na_pagina(cliente.post("/rastreio", data={"pedido": numero}).text) == "Pagamento em análise"
    # 5 min depois, confirmado e em separação
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-10-31T10:05:00")
    depois = cliente.post("/rastreio", data={"pedido": numero}).text
    assert etapas_na_pagina(depois) == [("Pedido recebido", "feita"), ("Pagamento confirmado", "feita"),
                                        ("Em separação", "atual"), ("Enviado", "pendente"), ("Entregue", "pendente")]
    assert "Pagamento em análise" not in depois


def test_boleto_aguarda_pagamento_com_a_compensacao_do_manual_e_nao_avanca(cliente, monkeypatch):
    numero = pedido_do_site(cliente, "boleto")
    for agora in ("2026-10-31T10:00:00", "2026-11-20T10:00:00"):
        monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", agora)
        html = cliente.post("/rastreio", data={"pedido": numero}).text
        assert etapas_na_pagina(html) == [("Pedido recebido", "feita"), ("Aguardando pagamento", "atual"),
                                          ("Em separação", "pendente"), ("Enviado", "pendente"),
                                          ("Entregue", "pendente")]
        assert "Compensação em até 3 dias úteis" in texto(html)


def test_pedido_recebido_mostra_data_e_horario_gravados(cliente):
    numero = pedido_do_site(cliente, "pix")
    assert "Em 31/10/2026 às 10h" in texto(cliente.get(f"/pedido/{numero}").text)


def test_site_nao_simula_envio_nem_entrega(cliente, monkeypatch):
    numero = pedido_do_site(cliente, "pix")
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2027-01-01T10:00:00")
    assert atual_na_pagina(cliente.post("/rastreio", data={"pedido": numero}).text) == "Em separação"


# ---- cada status do CSV ----------------------------------------------------------------------------------------------

ESPERADO_CSV = {
    "pending": ("Aguardando pagamento", ["Pedido recebido", "Aguardando pagamento", "Em separação", "Enviado", "Entregue"]),
    "confirmed": ("Em separação", CINCO),
    "shipped": ("Enviado", CINCO),
    "delivered": ("Entregue", CINCO),
    "cancelled": ("Cancelado", ["Pedido recebido", "Cancelado"]),
}


def um_pedido(sql, status: str) -> tuple[int, str]:
    r = sql.execute("SELECT p.id, c.telefone FROM pedidos p JOIN clientes c ON c.id = p.cliente_id "
                    "WHERE p.status = ? ORDER BY p.id LIMIT 1", (status,)).fetchone()
    return r["id"], re.sub(r"\D", "", r["telefone"])[-4:]


@pytest.mark.parametrize("status", list(ESPERADO_CSV))
def test_cada_status_do_csv_no_rastreio_e_na_lia(cliente, sql, status):
    atual, rotulos = ESPERADO_CSV[status]
    pid, final = um_pedido(sql, status)
    html = cliente.post("/rastreio", data={"pedido": str(pid), "final_telefone": final}).text
    pagina = etapas_na_pagina(html)
    assert [r for r, _ in pagina] == rotulos and atual_na_pagina(html) == atual
    assert html.count('aria-current="step"') == 1
    agente = Agente()
    agente.responder(f"c-{status}", f"onde está meu pedido {pid}?", "eval")
    resposta = agente.responder(f"c-{status}", f"o pedido é o {pid} e o final do telefone é {final}", "eval").texto
    frase = frase_lia(etapas_do_pedido(status))
    if status == "cancelled":
        assert frase == "" and "foi cancelado" in resposta
    else:
        assert frase and frase in resposta
        assert resposta.count(frase) == 1


def test_estados_de_cada_status_do_csv(sql):
    em_separacao = etapas_do_pedido("confirmed")
    assert [(e.rotulo, e.estado) for e in em_separacao][1:3] == [("Pagamento confirmado", "feita"),
                                                                  ("Em separação", "atual")]
    enviado = etapas_do_pedido("shipped", rastreio="BR9")
    assert [e.estado for e in enviado] == ["feita", "feita", "feita", "atual", "pendente"]
    entregue = etapas_do_pedido("delivered")
    assert [e.estado for e in entregue] == ["feita", "feita", "feita", "feita", "atual"]
    pendente = etapas_do_pedido("pending")
    assert [e.estado for e in pendente] == ["feita", "atual", "pendente", "pendente", "pendente"]
    cancelado = etapas_do_pedido("cancelled", nota="Pagamento não aprovado")
    assert [(e.rotulo, e.estado, e.detalhe) for e in cancelado][1] == ("Cancelado", "atual", "Pagamento não aprovado")


# ---- site e Lia com a mesma etapa -------------------------------------------------------------------------------------

def test_lia_diz_a_mesma_etapa_do_site_para_cada_forma(cliente, sql, monkeypatch):
    for forma, parcelas, rotulo, trecho in (("pix", "1", "Em separação", "em separação"),
                                            ("credito", "2", "Pagamento em análise", "em análise"),
                                            ("boleto", "1", "Aguardando pagamento", "aguardando a confirmação")):
        c = TestClient(criar_app(), follow_redirects=False)
        with c:
            numero = pedido_do_site(c, forma, parcelas)
            assert atual_na_pagina(c.get(f"/pedido/{numero}").text) == rotulo
            sessao = sql.execute("SELECT sessao FROM pedidos_demo WHERE numero = ?", (numero,)).fetchone()[0]
        resposta = Agente().responder(sessao, f"cadê o meu pedido {numero}?", "eval").texto
        assert trecho in resposta, (forma, resposta)
        assert "Nenhum valor foi cobrado" in resposta  # o que já havia na resposta continua


def test_lia_sai_da_analise_junto_com_o_site_depois_de_cinco_minutos(cliente, sql, monkeypatch):
    numero = pedido_do_site(cliente, "credito", "2")
    sessao = sql.execute("SELECT sessao FROM pedidos_demo").fetchone()[0]
    antes = Agente().responder(sessao, f"cadê o meu pedido {numero}?", "eval").texto
    assert "em análise" in antes
    monkeypatch.setenv("EMPORIO_DATA_REFERENCIA", "2026-10-31T10:06:00")
    depois = Agente().responder(sessao, f"e agora, como está o pedido {numero}?", "eval").texto
    assert "em análise" not in depois and "em separação" in depois
    assert atual_na_pagina(cliente.post("/rastreio", data={"pedido": numero}).text) == "Em separação"


def test_frase_da_lia_vem_da_etapa_atual_da_mesma_funcao():
    for forma in ("pix", "debito", "credito", "boleto"):
        etapas = etapas_do_pedido(STATUS_SITE, forma=forma, criado_em="2026-10-31T10:00:00")
        assert frase_lia(etapas).startswith("Pelo que eu vejo")
        assert etapa_atual(etapas).rotulo in {"Em separação", "Pagamento em análise", "Aguardando pagamento"}
