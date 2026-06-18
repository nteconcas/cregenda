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
# O Gunicorn inicia IMEDIATAMENTE sem esperar inicialização do banco.
# A rota /health responde instantaneamente, evitando crash loop por health check.
# A inicialização do banco (tabelas, admin, schema) é feita de forma lazy
# ou manualmente via init_app.py em outro momento.
CMD gunicorn -w 1 -b 0.0.0.0:${PORT:-80} \
    --timeout 120 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    wsgi:app
