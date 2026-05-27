from flask import Flask, redirect, url_for, request
from flask_login import LoginManager, current_user, login_required
from config import Config
from models import db, Usuario
from extensions import oauth
from werkzeug.security import generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import os
from dotenv import load_dotenv
import pymysql

# Instala o pymysql como driver MySQLdb padrão para evitar necessidade de compilação do mysqlclient
pymysql.install_as_MySQLdb()

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

from routes.auth import auth
from routes.gestor_geral import gestor_geral
from routes.gestor_regional import gestor_regional
from routes.gestor_escolar import gestor_escolar
from routes.professor import professor

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Configura ProxyFix para lidar corretamente com headers X-Forwarded-* (HTTPS, Host, etc)
    # x_for=1, x_proto=1. Evitamos x_host=1 para não confiar cegamente se o proxy não enviar.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # Log para confirmar qual banco está sendo usado (sem mostrar senha)
    db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if 'sqlite' in db_url:
        print("⚠️  AVISO: Usando banco de dados SQLite Local. Verifique se DATABASE_URL está configurada.")
    else:
        print("✅ Usando banco de dados externo/produção.")

    db.init_app(app)
    
    # Inicializa OAuth
    oauth.init_app(app)
    
    # Registra o cliente Google
    oauth.register(
        name='google',
        client_id=os.environ.get('GOOGLE_CLIENT_ID'),
        client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))

    # Registrar blueprints
    app.register_blueprint(auth)
    app.register_blueprint(gestor_geral, url_prefix='/gestor_geral')
    app.register_blueprint(gestor_regional, url_prefix='/gestor_regional')
    app.register_blueprint(gestor_escolar, url_prefix='/gestor_escolar')
    app.register_blueprint(professor, url_prefix='/professor')

    # Hook para logar todas as requisições
    @app.before_request
    def log_request_info():
        # Apenas logar se não for static
        if not request.path.startswith('/static'):
            print(f"📡 Request: {request.method} {request.url}")
            print(f"Headers: {dict(request.headers)}")

    # Rota central de dashboard
    @app.route('/health')
    def health_check():
        return "OK", 200

    @app.route('/dashboard')
    # @login_required  <-- Removido temporariamente para evitar NameError se o import falhar, já temos verificação manual abaixo
    def dashboard():
        print(f"Acessando dashboard. Usuário autenticado? {current_user.is_authenticated}") # DEBUG
        if not current_user.is_authenticated:
            print("Redirecionando para login por falta de autenticação.") # DEBUG
            return redirect(url_for('auth.login'))
        
        papel = current_user.papel
        print(f"Papel do usuário: {papel}") # DEBUG
        
        mapa = {
            'gestor_geral': 'gestor_geral.dashboard',
            'gestor_regional': 'gestor_regional.dashboard',
            'gestor_escolar': 'gestor_escolar.dashboard',
            'professor': 'professor.dashboard',
        }
        if papel in mapa:
            target_url = url_for(mapa[papel])
            print(f"Redirecionando para {mapa[papel]}: {target_url}") # DEBUG
            return redirect(target_url)
            
        print("Papel não mapeado. Redirecionando para login.") # DEBUG
        return redirect(url_for('auth.login'))
    
    # Rota de fallback para capturar 404 e logar
    @app.errorhandler(404)
    def page_not_found(e):
        print(f"❌ 404 Error na URL: {request.url}")
        return "Página não encontrada (404). Verifique a URL.", 404

    # Criação do usuário admin
    with app.app_context():
        db.create_all()
        
        # Verifica se o usuário admin já existe antes de tentar criar
        # admin_email = 'admin_cre@example.com'
        # try:
        #     # Tenta buscar o usuário primeiro
        #     existing_admin = Usuario.query.filter_by(email=admin_email).first()
        #     
        #     if not existing_admin:
        #         admin = Usuario(
        #             nome='Admin CRE',
        #             email=admin_email,
        #             senha=generate_password_hash('cre_admin'), # Usa método padrão seguro
        #             papel='gestor_geral'
        #         )
        #         db.session.add(admin)
        #         db.session.commit()
        #         print("✅ Usuário admin criado.")
        #     else:
        #         # Atualiza a senha para garantir acesso se o usuário já existir
        #         # existing_admin.senha = generate_password_hash('cre_admin')
        #         # db.session.commit()
        #         print("✅ Usuário admin já existe. Senha redefinida para 'cre_admin'.")
        #         
        # except Exception as e:
        #     db.session.rollback()
        #     print(f"ℹ️ Admin já existe (concorrência tratada): {e}")

    return app
