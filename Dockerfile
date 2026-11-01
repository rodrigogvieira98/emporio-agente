FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    EMPORIO_DB=/dados/emporio.db \
    EMPORIO_TRACE=/dados/trace.jsonl \
    EMPORIO_RAW=/app/data/raw \
    EMPORIO_DECISOR=regras

WORKDIR /app
COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt

COPY src ./src
COPY data/raw ./data/raw
COPY docker/entrada.sh ./docker/entrada.sh

RUN useradd --system --uid 10001 --home-dir /app lia \
    && mkdir /dados && chown lia /dados \
    && chmod +x docker/entrada.sh
USER lia
VOLUME /dados
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=10s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=8).status == 200 else 1)"

ENTRYPOINT ["docker/entrada.sh"]
CMD ["uvicorn", "emporio.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
