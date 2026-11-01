# Agente da Empório da Música

## Executar com Docker

```
docker compose up -d --build
```

Site em http://localhost:8000 e estado em http://localhost:8000/saude. Modelo padrão `qwen2.5:3b` (troque com `EMPORIO_MODELO`).
Com GPU NVIDIA: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`.
Parar: `docker compose down`.

## Executar sem Docker

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m emporio.dados.carga
set PYTHONPATH=src
.venv\Scripts\python -m uvicorn emporio.web.app:app --port 8000
```

Opcional: com o Ollama rodando, defina `EMPORIO_MODELO` (por exemplo `qwen2.5:3b`).

## Testes

```
python -m pytest
pip install -r requirements-e2e.txt && playwright install chromium
python -m pytest -m e2e
```
