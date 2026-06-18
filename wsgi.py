"""
WSGI entry point for Gunicorn.
Este módulo é importado pelo Gunicorn para servir a aplicação.
A inicialização (tabelas, admin, schema) é feita separadamente pelo init_app.py
ou pode ser feita aqui se necessário.
"""
from app import create_app

# Cria a aplicação Flask
app = create_app()

if __name__ == "__main__":
    app.run()
