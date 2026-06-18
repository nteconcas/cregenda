"""
Script de inicialização do banco de dados.
Executa APENAS a criação de tabelas, admin e atualização de schema.
NÃO inicia o servidor Gunicorn - isso é feito separadamente.

Este script DEVE ser executado antes do Gunicorn, em um processo separado.
"""
from app import create_app
from models import db, Usuario
from werkzeug.security import generate_password_hash
from sqlalchemy import text
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
    
    with app.app_context():
        # 1. Garante que as tabelas existem
        try:
            db.create_all()
            print("✅ Tabelas verificadas/criadas.")
        except Exception as e:
            print(f"⚠️ Erro ao criar tabelas: {e}")
        
        # 2. Cria usuário admin se não existir
        try:
            admin_email = 'admin_cre@example.com'
            existing_admin = Usuario.query.filter_by(email=admin_email).first()
            
            if not existing_admin:
                print(f"Criando usuário admin: {admin_email}")
                admin = Usuario(
                    nome='Admin CRE',
                    email=admin_email,
                    senha=generate_password_hash('cre_admin'),
                    papel='gestor_geral'
                )
                db.session.add(admin)
                db.session.commit()
                print("✅ Usuário admin criado com sucesso!")
            else:
                print("ℹ️ Usuário admin já existe.")
        except Exception as e:
            db.session.rollback()
            print(f"⚠️ Erro ao criar/verificar admin: {e}")
        
        # 3. Atualiza schema (MySQL)
        try:
            db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            if 'sqlite' in db_url:
                print("ℹ️ SQLite detectado. Pulando ALTER TABLE.")
            else:
                print("🔄 Verificando atualizações de schema...")
                print("Executando: ALTER TABLE blocos_aula MODIFY COLUMN periodo VARCHAR(50)")
                db.session.execute(text("ALTER TABLE blocos_aula MODIFY COLUMN periodo VARCHAR(50)"))
                db.session.commit()
                print("✅ Schema atualizado com sucesso!")
        except Exception as e:
            print(f"ℹ️ Atualização de schema pulada (pode ser normal): {e}")
        
        print("✅ Inicialização do banco concluída com sucesso!")

if __name__ == "__main__":
    init_database()
