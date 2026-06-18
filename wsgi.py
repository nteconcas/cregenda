"""
WSGI entry point for Gunicorn.
O Gunicorn importa este módulo para servir a aplicação.
A inicialização do banco (tabelas, admin, schema) é feita de forma LAZY,
ou seja, apenas quando o primeiro request que precisa do banco chegar.
A rota /health responde IMEDIATAMENTE sem precisar de banco.
"""
from app import create_app

# Cria a aplicação Flask (RÁPIDO - sem operações de banco)
app = create_app()

if __name__ == "__main__":
    app.run()
