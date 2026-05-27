# routes/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user
from werkzeug.security import check_password_hash
from models import Usuario
from extensions import oauth
import traceback

auth = Blueprint('auth', __name__)

@auth.route('/')
def index():
    return redirect(url_for('auth.login'))

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        print(f"Tentativa de login para: {email}") # DEBUG
        
        try:
            user = Usuario.query.filter_by(email=email).first()
            
            if user:
                print(f"Usuário encontrado: {user.nome}, Papel: {user.papel}") # DEBUG
                if check_password_hash(user.senha, senha):
                    print("Senha correta.") # DEBUG
                    if not user.ativo:
                        flash('Sua conta está desativada. Entre em contato com a escola.', 'error')
                        return render_template('login.html')
                    
                    # Limpa sessão anterior para evitar cookies gigantes ou corrompidos
                    session.clear()
                    
                    print("Tentando login_user...")
                    login_user(user)
                    print("login_user sucesso. Redirecionando...")
                    return redirect(url_for('dashboard'))
                else:
                    print("Senha incorreta.") # DEBUG
            else:
                print("Usuário não encontrado.") # DEBUG
                
            flash('E-mail ou senha inválidos.', 'error')
        except Exception as e:
            print(f"❌ ERRO NO LOGIN: {str(e)}")
            traceback.print_exc()
            flash(f'Erro interno ao fazer login: {str(e)}', 'error')
            
    return render_template('login.html')

@auth.route('/login/google')
def google_login():
    redirect_uri = url_for('auth.google_auth', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@auth.route('/login/google/callback')
def google_auth():
    try:
        token = oauth.google.authorize_access_token()
        user_info = oauth.google.parse_id_token(token, nonce=None)
        
        email = user_info.get('email')
        if not email:
            flash('Não foi possível obter o e-mail do Google.', 'error')
            return redirect(url_for('auth.login'))

        user = Usuario.query.filter_by(email=email).first()
        
        if not user:
            flash(f'O e-mail {email} não está cadastrado no sistema. Contate o administrador.', 'error')
            return redirect(url_for('auth.login'))
            
        if not user.ativo:
            flash('Sua conta está desativada. Entre em contato com a escola.', 'error')
            return redirect(url_for('auth.login'))
            
        # Limpa sessão anterior
        session.clear()
        
        login_user(user)
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        flash(f'Erro ao realizar login com Google. Verifique as configurações.', 'error')
        print(f"Erro Google Auth: {e}")
        traceback.print_exc()
        return redirect(url_for('auth.login'))


@auth.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

# Rota de debug de sessão
@auth.route('/debug_session')
def debug_session():
    return f"Session: {dict(session)}"
