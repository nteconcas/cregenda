from flask import Flask, redirect, url_for, request
from flask_login import LoginManager, current_user
from config import Config
from models import db, Usuario
from extensions import oauth
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
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

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

    # Rota de health check - responde IMEDIATAMENTE sem precisar de banco
    @app.route('/health')
    def health_check():
        return "OK", 200

    @app.route('/dashboard')
    def dashboard():
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        papel = current_user.papel
        
        mapa = {
            'gestor_geral': 'gestor_geral.dashboard',
            'gestor_regional': 'gestor_regional.dashboard',
            'gestor_escolar': 'gestor_escolar.dashboard',
            'professor': 'professor.dashboard',
        }
        if papel in mapa:
            return redirect(url_for(mapa[papel]))
            
        return redirect(url_for('auth.login'))
    
    # Rota de fallback para capturar 404 e logar
    @app.errorhandler(404)
    def page_not_found(e):
        print(f"404 Error na URL: {request.url}")
        return "Página não encontrada (404). Verifique a URL.", 404

    return app
