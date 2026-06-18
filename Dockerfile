FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
# Limpa cache do pip antes de instalar para evitar arquivos corrompidos
RUN pip cache purge && \
    pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create instance directory for SQLite (if used as fallback)
RUN mkdir -p instance

# Expose port 80
EXPOSE 80

# Command to run the application
# 1. Primeiro executa a inicialização do banco (tabelas, admin, schema) em processo separado
# 2. Depois inicia o Gunicorn (que NÃO faz nenhuma operação de banco na inicialização)
# 
# O uso de '&&' garante que o Gunicorn só inicia se a inicialização do banco for bem-sucedida.
# O health check da plataforma vai bater na rota /health que responde instantaneamente.
CMD python init_app.py && \
    echo "Iniciando Gunicorn..." && \
    gunicorn -w 4 -b 0.0.0.0:${PORT:-80} \
        --timeout 120 \
        --keep-alive 5 \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        wsgi:app
