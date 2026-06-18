#!/bin/sh
# Script de entrada para o container Docker
# Inicializa a aplicação (tabelas, admin, schema) e depois inicia o Gunicorn

set -e

echo "=========================================="
echo "  CREGENDA - Inicializando aplicação..."
echo "=========================================="

# Executa a inicialização (tabelas, admin, schema)
python init_app.py
INIT_EXIT=$?

if [ $INIT_EXIT -ne 0 ]; then
    echo "⚠️  Inicialização teve avisos, mas continuando..."
fi

echo ""
echo "=========================================="
echo "  Iniciando Gunicorn..."
echo "=========================================="

# Usa a porta da variável de ambiente PORT ou 80 como fallback
PORT=${PORT:-80}

exec gunicorn \
    -w 4 \
    -b 0.0.0.0:${PORT} \
    --timeout 120 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    wsgi:app
