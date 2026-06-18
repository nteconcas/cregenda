"""
Script de teste para verificar se o servidor está funcionando.
Uso: python test_server.py
"""
import urllib.request
import sys
import time

def test_server():
    port = sys.argv[1] if len(sys.argv) > 1 else '80'
    host = 'localhost'
    
    urls = [
        f'http://{host}:{port}/health',
        f'http://{host}:{port}/',
    ]
    
    for url in urls:
        try:
            print(f"Testando: {url}")
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as response:
                print(f"  ✅ Status: {response.status}")
                print(f"  Resposta: {response.read().decode()}")
        except Exception as e:
            print(f"  ❌ Erro: {e}")
    
    print("\nDica: Se o servidor estiver rodando em um container Docker,")
    print("certifique-se de que a porta está mapeada:")
    print("  docker run -p 80:80 cregenda")
    print("  ou")
    print("  docker run -p 8080:80 cregenda  (e acesse http://localhost:8080)")

if __name__ == "__main__":
    test_server()
