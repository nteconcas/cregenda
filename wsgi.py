from app import create_app
import os
import sys

# Tenta criar o app com retry para o banco de dados
import time

app = None
retries = 5
while retries > 0:
    try:
        app = create_app()
        break
    except Exception as e:
        print(f"⚠️ Erro ao criar aplicação no wsgi.py: {e}")
        retries -= 1
        if retries > 0:
            print(f"Tentando novamente em 5 segundos... ({retries} tentativas restantes)")
            time.sleep(5)
        else:
            print("❌ Falha ao criar aplicação após várias tentativas.")
            sys.exit(1)

if __name__ == "__main__":
    app.run()
