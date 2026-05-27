# routes/gestor_geral.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from models import db, Usuario, Regiao
from functools import wraps

def papel_requerido(papel):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.papel != papel:
                flash('Acesso negado.', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

gestor_geral = Blueprint('gestor_geral', __name__)

@gestor_geral.route('/dashboard')
@login_required
@papel_requerido('gestor_geral')
def dashboard():
    regioes = Regiao.query.order_by(Regiao.nome).all()
    dados_regioes = []
    for regiao in regioes:
        gestores = Usuario.query.filter_by(regiao_id=regiao.id, papel='gestor_regional').all()
        dados_regioes.append({
            'regiao': regiao,
            'gestores': gestores
        })
    return render_template('gestor_geral/dashboard.html',
                           usuario=current_user,
                           dados_regioes=dados_regioes)

@gestor_geral.route('/cadastrar_gestor_regional', methods=['GET', 'POST'])
@login_required
@papel_requerido('gestor_geral')
def cadastrar_gestor_regional():
    if request.method == 'POST':
        nome = request.form.get('nome').strip()
        email = request.form.get('email').strip()
        telefone = request.form.get('telefone').strip()
        senha = request.form.get('senha').strip()
        regiao_nome = request.form.get('regiao_nome').strip()
        nova_regiao = request.form.get('nova_regiao')

        if not nome or not email or not senha or not (regiao_nome or nova_regiao):
            flash('Todos os campos são obrigatórios.', 'error')
            return redirect(url_for('gestor_geral.cadastrar_gestor_regional'))

        if Usuario.query.filter_by(email=email).first():
            flash('E-mail já cadastrado no sistema.', 'error')
            return redirect(url_for('gestor_geral.cadastrar_gestor_regional'))

        if nova_regiao:
            regiao = Regiao(nome=nova_regiao)
            db.session.add(regiao)
            db.session.flush()
        else:
            regiao = Regiao.query.filter_by(nome=regiao_nome).first()
            if not regiao:
                flash('Região selecionada não encontrada.', 'error')
                return redirect(url_for('gestor_geral.cadastrar_gestor_regional'))

        novo_usuario = Usuario(
            nome=nome,
            email=email,
            telefone=telefone,
            senha=generate_password_hash(senha, method='pbkdf2:sha256'),
            papel='gestor_regional',
            regiao_id=regiao.id
        )
        db.session.add(novo_usuario)
        db.session.commit()
        flash(f'Gestor regional "{nome}" cadastrado com sucesso!', 'success')
        return redirect(url_for('gestor_geral.cadastrar_gestor_regional'))

    regioes = Regiao.query.order_by(Regiao.nome).all()
    regiao_id_selecionada = request.args.get('regiao_id', type=int)
    return render_template('gestor_geral/cadastrar_regional.html',
                           usuario=current_user,
                           regioes=regioes,
                           regiao_id_selecionada=regiao_id_selecionada)

@gestor_geral.route('/editar_gestor_regional/<int:id>', methods=['GET', 'POST'])
@login_required
@papel_requerido('gestor_geral')
def editar_gestor_regional(id):
    gestor = Usuario.query.filter_by(id=id, papel='gestor_regional').first_or_404()
    
    if request.method == 'POST':
        nome = request.form.get('nome').strip()
        email = request.form.get('email').strip()
        telefone = request.form.get('telefone').strip()
        nova_senha = request.form.get('nova_senha', '').strip()
        regiao_nome = request.form.get('regiao_nome').strip()

        if not nome or not email or not regiao_nome:
            flash('Nome, e-mail e regional são obrigatórios.', 'error')
            return redirect(url_for('gestor_geral.editar_gestor_regional', id=id))

        outro_usuario = Usuario.query.filter(Usuario.email == email, Usuario.id != id).first()
        if outro_usuario:
            flash('E-mail já está em uso.', 'error')
            return redirect(url_for('gestor_geral.editar_gestor_regional', id=id))

        regiao = Regiao.query.filter_by(nome=regiao_nome).first()
        if not regiao:
            flash('Região selecionada não encontrada.', 'error')
            return redirect(url_for('gestor_geral.editar_gestor_regional', id=id))

        gestor.nome = nome
        gestor.email = email
        gestor.telefone = telefone
        gestor.regiao_id = regiao.id

        if nova_senha:
            gestor.senha = generate_password_hash(nova_senha, method='pbkdf2:sha256')

        db.session.commit()
        flash(f'Gestor regional "{nome}" atualizado com sucesso!', 'success')
        return redirect(url_for('dashboard'))

    regioes = Regiao.query.order_by(Regiao.nome).all()
    return render_template('gestor_geral/editar_regional.html',
                           usuario=current_user,
                           gestor=gestor,
                           regioes=regioes,
                           regiao_atual=gestor.regiao_id)