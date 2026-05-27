from app import create_app
from models import db
from sqlalchemy import text

def update_schema():
    app = create_app()
    with app.app_context():
        print("🔄 Verificando atualizações de schema...")
        try:
            db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            if 'sqlite' in db_url:
                print("ℹ️ SQLite detectado. O SQLite não impõe limites rígidos de VARCHAR, pulando ALTER TABLE.")
            else:
                # Tenta alterar a coluna para VARCHAR(50) no MySQL/MariaDB
                print("Executando: ALTER TABLE blocos_aula MODIFY COLUMN periodo VARCHAR(50)")
                db.session.execute(text("ALTER TABLE blocos_aula MODIFY COLUMN periodo VARCHAR(50)"))
                db.session.commit()
                print("✅ Schema atualizado com sucesso!")
        except Exception as e:
            # Se falhar (ex: tabela não existe, ou sintaxe diferente se for SQLite local), apenas loga
            print(f"⚠️ Nota: Atualização de schema pulada ou falhou (pode ser normal se já atualizado): {e}")

if __name__ == "__main__":
    update_schema()
