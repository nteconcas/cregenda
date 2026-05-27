from app import create_app
from models import db, Usuario
from werkzeug.security import generate_password_hash
import time

def create_admin_user():
    app = create_app()
    with app.app_context():
        # Tenta conectar ao banco com retries, pois o MySQL pode demorar a subir
        retries = 5
        while retries > 0:
            try:
                # Garante que as tabelas existem
                db.create_all()
                
                admin_email = 'admin_cre@example.com'
                # Verifica se já existe
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
                
                break # Sucesso
            except Exception as e:
                print(f"⚠️ Erro ao inicializar banco/admin: {e}")
                retries -= 1
                if retries > 0:
                    print(f"Tentando novamente em 5 segundos... ({retries} tentativas restantes)")
                    time.sleep(5)
                else:
                    print("❌ Falha ao inicializar admin após várias tentativas.")

if __name__ == "__main__":
    create_admin_user()
