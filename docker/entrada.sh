#!/bin/sh
# Cria o banco a partir dos CSV se ainda nao existir, e entrega o controle ao comando (uvicorn).
set -eu
if [ ! -f "$EMPORIO_DB" ]; then
    echo "Banco ausente em $EMPORIO_DB, criando a partir de $EMPORIO_RAW"
    python -m emporio.dados.carga
fi
exec "$@"
