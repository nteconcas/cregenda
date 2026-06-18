"""
Script de inicialização do banco de dados.
Pode ser executado manualmente ou como pre-start.
Exemplo: python init_app.py

Também é possível inicializar via HTTP após o servidor subir:
  curl http://localhost:80/init-db
"""
from app import create_app, initialize_database
import time
import sys

def init_database():
    """Inicializa o banco de dados: cria tabelas, admin e atualiza schema."""
    print("🚀 Inicializando banco de dados...")
    
    # Tenta criar o app com retry para o banco de dados
    retries = 5
    app = None
    while retries > 0:
        try:
            app = create_app()
            break
        except Exception as e:
            print(f"⚠️ Erro ao criar aplicação: {e}")
            retries -= 1
            if retries > 0:
                print(f"Tentando novamente em 5 segundos... ({retries} tentativas restantes)")
                time.sleep(5)
            else:
                print("❌ Falha ao criar aplicação após várias tentativas.")
                sys.exit(1)
    
    # Inicializa o banco usando a mesma função thread-safe do app.py
    success = initialize_database(app)
    
    if success:
        print("✅ Inicialização do banco concluída com sucesso!")
    else:
        print("❌ Falha na inicialização do banco.")
        sys.exit(1)

if __name__ == "__main__":
    init_database()
