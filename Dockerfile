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

# Command to run the application using Gunicorn
# Primeiro roda o script de criação de admin e atualização de schema, depois inicia o servidor
CMD ["sh", "-c", "python create_admin.py && python update_schema.py && gunicorn -w 4 -b 0.0.0.0:80 wsgi:app"]
