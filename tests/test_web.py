"""Site: rotas com TestClient. As ferramentas são as mesmas do agente; aqui se confere só a vitrine."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from emporio import config
from emporio.politicas.manual import fato
from emporio.web.app import COOKIE, criar_app

WEB = Path(__file__).resolve().parents[1] / "src" / "emporio" / "web"


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.delenv("EMPORIO_MODELO", raising=False)
    monkeypatch.delenv("EMPORIO_DECISOR", raising=False)
    with TestClient(criar_app()) as c:
        yield c


def test_saude_informa_banco_e_modelo(cliente):
    r = cliente.get("/saude")
    assert r.status_code == 200
    assert r.json()["banco"] == "ok" and r.json()["modelo"] == "nao_configurado"


def test_saude_com_banco_ausente_devolve_503(cliente, monkeypatch, tmp_path):
    monkeypatch.setenv("EMPORIO_DB", str(tmp_path / "nao_existe" / "x.db"))
    assert cliente.get("/saude").status_code == 503


def test_saude_com_ollama_fora_nao_derruba(monkeypatch):
    monkeypatch.setenv("EMPORIO_MODELO", "qwen2.5:3b")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")
    with TestClient(criar_app()) as c:
        r = c.get("/saude")
    assert r.status_code == 200 and r.json()["modelo"] == "indisponivel"


def test_inicio_tem_categorias_busca_chat_e_dados_da_loja(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert "Guitarras" in r.text and 'id="chat"' in r.text and 'role="search"' in r.text
    assert fato("empresa.nome_fantasia").valor in r.text
    assert fato("empresa.endereco").valor["logradouro"] in r.text


def test_catalogo_filtra_por_categoria_e_faixa_de_preco(cliente):
    r = cliente.get("/catalogo", params={"categoria": "Ukuleles", "preco_max": "400"})
    assert r.status_code == 200
    nomes = re.findall(r'<a href="/produto/\d+">([^<]+)</a>', r.text)
    assert nomes
    precos = [int(x.replace(".", "")) for x in re.findall(r'preco-final">R\$ ([\d.]+),', r.text)]
    assert precos and all(p <= 400 for p in precos)


def test_catalogo_estados_vazio_e_faixa_incoerente(cliente):
    assert "Nenhum produto encontrado" in cliente.get("/catalogo", params={"termo": "zzzxyz"}).text
    assert "Não temos essa categoria" in cliente.get("/catalogo", params={"categoria": "Tratores"}).text
    assert "incoerente" in cliente.get("/catalogo", params={"preco_min": "900", "preco_max": "100"}).text
    assert "apenas números" in cliente.get("/catalogo", params={"preco_min": "abc"}).text


def test_produto_descontinuado_aparece_marcado_sem_compra(cliente):
    r = cliente.get("/produto/113")
    assert r.status_code == 200
    assert "Descontinuado" in r.text and "btn-compra" not in r.text and "Formas de pagamento" not in r.text


def test_produto_disponivel_tem_compra_e_condicoes(cliente):
    r = cliente.get("/produto/81")
    assert "btn-compra" in r.text and "Formas de pagamento" in r.text and "PIX" in r.text


def test_produto_com_promocao_mostra_original_percentual_e_final_da_ferramenta(cliente):
    r = cliente.get("/produto/90")  # Crafter HT-100, promoção ativa de 18%
    assert "R$ 2.399,00" in r.text and "-18%" in r.text and "R$ 1.967,18" in r.text
    lista = cliente.get("/catalogo", params={"termo": "Crafter HT-100"}).text
    assert "R$ 1.967,18" in lista and "-18%" in lista


def test_produto_inexistente_devolve_404(cliente):
    assert cliente.get("/produto/99999").status_code == 404


def test_politicas_mostra_so_secoes_publicas(cliente):
    r = cliente.get("/politicas")
    assert r.status_code == 200 and "secao-3" in r.text
    assert "secao-7.1" not in r.text  # procedimento interno


def test_rastreio_ok_mostra_codigo(cliente):
    r = cliente.post("/rastreio", data={"pedido": "8", "final_telefone": "7821"})
    assert r.status_code == 200 and "BRJL5544332BR" in r.text


def test_rastreio_negado_e_unificado(cliente):
    errado = cliente.post("/rastreio", data={"pedido": "8", "final_telefone": "0000"})
    inexistente = cliente.post("/rastreio", data={"pedido": "9999", "final_telefone": "7821"})
    assert errado.status_code == inexistente.status_code == 403
    aviso = re.search(r'role="alert">([^<]+)<', errado.text).group(1)
    assert aviso == re.search(r'role="alert">([^<]+)<', inexistente.text).group(1)
    assert "BRJL5544332BR" not in errado.text


def test_rastreio_limite_de_tentativas_vale_por_sessao(cliente):
    for _ in range(3):
        cliente.post("/rastreio", data={"pedido": "8", "final_telefone": "0000"})
    assert cliente.post("/rastreio", data={"pedido": "8", "final_telefone": "7821"}).status_code == 403
    outro = TestClient(cliente.app)  # outro navegador, outra sessão
    assert outro.post("/rastreio", data={"pedido": "8", "final_telefone": "7821"}).status_code == 200


def test_rastreio_entrada_invalida_nao_consulta(cliente):
    r = cliente.post("/rastreio", data={"pedido": "oito", "final_telefone": "12"})
    assert r.status_code == 422 and "4 últimos dígitos" in r.text


def test_cookie_assinado_com_id_aleatorio_e_adulteracao_vira_sessao_nova(cliente):
    cliente.get("/")
    bruto = cliente.cookies.get(COOKIE)
    assert bruto and bruto.count(".") == 1  # id aleatório assinado, nada mais
    outro = TestClient(cliente.app)
    r = outro.get("/", headers={"Cookie": f"{COOKIE}=adulterado.xxx"})
    assert COOKIE in r.headers.get("set-cookie", "")  # cookie inválido é trocado por um novo


def test_chat_pedido_de_atendente_devolve_protocolo(cliente):
    r = cliente.post("/chat", data={"mensagem": "quero falar com um atendente"})
    assert r.status_code == 200 and "EM-" in r.text


def test_chat_escapa_html_do_cliente_e_do_agente(cliente):
    r = cliente.post("/chat", data={"mensagem": "<script>alert(1)</script> oi"})
    assert "<script>" not in r.text and "&lt;script&gt;" in r.text


def test_chat_mensagem_vazia_ou_longa(cliente):
    assert cliente.post("/chat", data={"mensagem": "   "}).status_code == 422
    assert cliente.post("/chat", data={"mensagem": "a" * 5000}).status_code == 422


def test_chat_responde_com_ollama_inacessivel(monkeypatch):
    monkeypatch.setenv("EMPORIO_MODELO", "qwen2.5:3b")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")  # conexão recusada
    with TestClient(criar_app()) as c:
        r = c.post("/chat", data={"mensagem": "quero falar com um atendente"})
        agente = c.app.state.agente
    assert r.status_code == 200 and "EM-" in r.text
    assert agente.redator is not None  # o modelo estava configurado e a conexão foi recusada
    trace = config.caminho_trace().read_text(encoding="utf-8")
    assert "erro_modelo" in trace  # a falha fica registrada, não silenciosa


def test_chat_nao_grava_pii_no_cookie(cliente):
    cliente.post("/chat", data={"mensagem": "meu telefone e (11) 91234-5678"})
    assert "91234" not in (cliente.cookies.get(COOKIE) or "")


def test_templates_e_web_sem_fatos_de_loja():
    """A varredura do .py já cobre web/; aqui os templates e os estáticos próprios."""
    proibidos = [re.compile(p, re.I) for p in (
        r"\(?\d{2}\)?\s?\d{4,5}-\d{4}", r"\b\d{5}-\d{3}\b", r"R\$\s?\d", r"\b\d{1,2}:\d{2}\b",
        r"Emp[óo]rio da M[úu]sica", r"Campo Grande", r"Rua 14", r"@\w+\.com", "—")]
    arquivos = [p for p in WEB.rglob("*") if p.is_file() and p.suffix in {".html", ".css"} or p.name == "chat.js"]
    achados = [(p.name, rx.pattern) for p in arquivos for rx in proibidos if rx.search(p.read_text(encoding="utf-8"))]
    assert achados == []
