"""Provedor de modelo mal configurado não derruba a Lia: ela segue só com as regras."""
from fastapi.testclient import TestClient


def test_provedor_desconhecido_cai_nas_regras(monkeypatch, tmp_path):
    monkeypatch.setenv("EMPORIO_PROVEDOR", "inexistente")
    from emporio.web.app import criar_app

    with TestClient(criar_app()) as cliente:
        cliente.get("/")
        r = cliente.post("/chat", data={"mensagem": "qual o horário de vocês?"},
                         headers={"HX-Request": "true", "Origin": "http://testserver"})
    assert r.status_code == 200 and "msg lia" in r.text
