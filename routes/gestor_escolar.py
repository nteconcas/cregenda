from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from models import db, Usuario, Turma, Recurso, BlocoAula, Reserva, Bloqueio, Vinculo, Disciplina, Escola
from functools import wraps
from datetime import date, datetime, timedelta
import calendar
from sqlalchemy import func, desc
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError, DataError
from io import BytesIO
from fpdf import FPDF

gestor_escolar = Blueprint('gestor_escolar', __name__)

DIAS_SEMANA = {0: 'Segunda-feira', 1: 'Terça-feira', 2: 'Quarta-feira', 3: 'Quinta-feira', 4: 'Sexta-feira', 5: 'Sábado', 6: 'Domingo'}

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

@gestor_escolar.route('/dashboard')
@login_required
@papel_requerido('gestor_escolar')
def dashboard():
    data_str = request.args.get('data')
    if data_str:
        try:
            data_filtro = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data_filtro = date.today()
    else:
        data_filtro = date.today()

    data_anterior = (data_filtro - timedelta(days=1)).strftime('%Y-%m-%d')
    data_proxima = (data_filtro + timedelta(days=1)).strftime('%Y-%m-%d')
    today_date = date.today().strftime('%Y-%m-%d')

    recursos = Recurso.query.filter_by(escola_id=current_user.escola_id).all()
    
    # Busca blocos de aula do dia da semana
    dia_semana = data_filtro.weekday()
    blocos = BlocoAula.query.filter_by(escola_id=current_user.escola_id, dia_semana=dia_semana).order_by(BlocoAula.id).all()
    
    # Organiza blocos por turno
    blocos_por_turno = {}
    for bloco in blocos:
        if ' - ' in bloco.periodo:
            turno = bloco.periodo.split(' - ')[0]
        else:
            turno = 'Geral'
        
        if turno not in blocos_por_turno:
            blocos_por_turno[turno] = []
        blocos_por_turno[turno].append(bloco)

    # Busca reservas e bloqueios
    reservas = Reserva.query.options(
        joinedload(Reserva.professor),
        joinedload(Reserva.turma),
        joinedload(Reserva.disciplina),
        joinedload(Reserva.recurso),
        joinedload(Reserva.bloco)
    ).filter(
        Reserva.data == data_filtro,
        Reserva.recurso_id.in_([r.id for r in recursos])
    ).all()
    
    bloqueios = Bloqueio.query.filter(
        Bloqueio.data == data_filtro,
        Bloqueio.recurso_id.in_([r.id for r in recursos])
    ).all()

    # Mapeia reservas e bloqueios
    mapa_reservas = {}
    for r in reservas:
        if r.status != 'cancelada':
            mapa_reservas[(r.recurso_id, r.bloco_aula_id)] = r
            
    mapa_bloqueios = {}
    for b in bloqueios:
        mapa_bloqueios[(b.recurso_id, b.bloco_aula_id)] = b

    # Construir Grid para o Template
    grid = {}
    for bloco in blocos:
        grid[bloco.id] = {}
        for recurso in recursos:
            cell = {'type': 'livre', 'obj': None}
            
            # Prioridade: Reserva > Bloqueio > Livre
            if (recurso.id, bloco.id) in mapa_reservas:
                cell['type'] = 'reserva'
                cell['obj'] = mapa_reservas[(recurso.id, bloco.id)]
            elif (recurso.id, bloco.id) in mapa_bloqueios:
                cell['type'] = 'bloqueio'
                cell['obj'] = mapa_bloqueios[(recurso.id, bloco.id)]
                
            grid[bloco.id][recurso.id] = cell

    if request.args.get('partial'):
        return render_template('gestor_escolar/_grid_content.html',
                               recursos=recursos,
                               blocos_por_turno=blocos_por_turno,
                               grid=grid,
                               data_filtro=data_filtro.strftime('%Y-%m-%d'))

    return render_template('gestor_escolar/dashboard.html',
                           usuario=current_user,
                           data_filtro=data_filtro.strftime('%Y-%m-%d'),
                           data_anterior=data_anterior,
                           data_proxima=data_proxima,
                           today_date=today_date,
                           recursos=recursos,
                           blocos_por_turno=blocos_por_turno,
                           grid=grid)

@gestor_escolar.route('/cancelar_reserva/<int:id>', methods=['POST'])
@login_required
@papel_requerido('gestor_escolar')
def cancelar_reserva(id):
    reserva = Reserva.query.get_or_404(id)
    if reserva.recurso.escola_id != current_user.escola_id:
        flash('Acesso negado.', 'error')
        return redirect(url_for('gestor_escolar.dashboard'))
        
    data_str = reserva.data.strftime('%Y-%m-%d')
    reserva.status = 'cancelada'
    db.session.commit()
    
    flash('Reserva cancelada com sucesso.', 'success')
    return redirect(url_for('gestor_escolar.dashboard', data=data_str))

@gestor_escolar.route('/marcar_nao_realizada/<int:id>', methods=['POST'])
@login_required
@papel_requerido('gestor_escolar')
def marcar_nao_realizada(id):
    reserva = Reserva.query.get_or_404(id)
    
    # Verificar permissão (apenas da escola do gestor)
    if reserva.recurso.escola_id != current_user.escola_id:
        flash('Acesso negado.', 'error')
        return redirect(url_for('gestor_escolar.dashboard'))
        
    motivo = request.form.get('motivo')
    if not motivo:
        flash('O motivo é obrigatório.', 'error')
        return redirect(url_for('gestor_escolar.dashboard'))
        
    reserva.status = 'nao_realizada'
    reserva.motivo_nao_realizacao = motivo
    db.session.commit()
    
    flash('Reserva marcada como não realizada.', 'success')
    return redirect(url_for('gestor_escolar.dashboard'))


@gestor_escolar.route('/bloquear_multiplos', methods=['POST'])
@login_required
@papel_requerido('gestor_escolar')
def bloquear_multiplos():
    try:
        data_str = request.form.get('data')
        justificativa = request.form.get('justificativa')
        # Itens selecionados vêm como 'itens[]': "recurso_id|bloco_id"
        itens = request.form.getlist('itens[]')

        if not data_str or not justificativa or not itens:
            flash('Dados inválidos para bloqueio múltiplo.', 'error')
            return redirect(url_for('gestor_escolar.dashboard', data=data_str))

        data_bloqueio = datetime.strptime(data_str, '%Y-%m-%d').date()
        count_bloqueios = 0

        for item in itens:
            try:
                r_id, b_id = item.split('|')
                
                # Verificar conflitos
                existente = Bloqueio.query.filter_by(
                    recurso_id=r_id,
                    bloco_aula_id=b_id,
                    data=data_bloqueio
                ).first()
                
                reserva = Reserva.query.filter_by(
                     recurso_id=r_id,
                     bloco_aula_id=b_id,
                     data=data_bloqueio
                ).first()

                if not existente and not reserva:
                    novo_bloqueio = Bloqueio(
                        recurso_id=r_id,
                        bloco_aula_id=b_id,
                        data=data_bloqueio,
                        justificativa=justificativa,
                        tipo='bloco_especifico',
                        escola_id=current_user.escola_id
                    )
                    db.session.add(novo_bloqueio)
                    count_bloqueios += 1
            except ValueError:
                continue

        db.session.commit()
        
        if count_bloqueios > 0:
            flash(f'{count_bloqueios} horários bloqueados com sucesso!', 'success')
        else:
            flash('Nenhum bloqueio foi realizado (talvez já estivessem ocupados).', 'warning')
            
        return redirect(url_for('gestor_escolar.dashboard', data=data_str))

    except Exception as e:
        db.session.rollback()
        print(f"Erro em bloquear_multiplos: {e}")
        flash('Erro ao processar bloqueios.', 'error')
        return redirect(url_for('gestor_escolar.dashboard'))


@gestor_escolar.route('/bloquear_aula', methods=['POST'])
@login_required
@papel_requerido('gestor_escolar')
def bloquear_aula():
    recurso_id = request.form.get('recurso_id')
    bloco_id = request.form.get('bloco_id')
    data_str = request.form.get('data')
    justificativa = request.form.get('justificativa')

    if not all([recurso_id, bloco_id, data_str, justificativa]):
        flash('Todos os campos são obrigatórios.', 'error')
        return redirect(url_for('gestor_escolar.dashboard', data=data_str))

    try:
        data_bloqueio = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Data inválida.', 'error')
        return redirect(url_for('gestor_escolar.dashboard'))

    # Verifica se já existe bloqueio ou reserva
    existente = Bloqueio.query.filter_by(
        recurso_id=recurso_id,
        bloco_aula_id=bloco_id,
        data=data_bloqueio
    ).first()

    if existente:
        flash('Já existe um bloqueio para este horário.', 'error')
        return redirect(url_for('gestor_escolar.dashboard', data=data_str))
    
    # Verifica se existe reserva ativa (não cancelada)
    reserva = Reserva.query.filter_by(
        recurso_id=recurso_id,
        bloco_aula_id=bloco_id,
        data=data_bloqueio
    ).filter(Reserva.status != 'cancelada').first()
    
    if reserva:
        flash('Existe uma reserva ativa para este horário. Cancele-a antes de bloquear.', 'error')
        return redirect(url_for('gestor_escolar.dashboard', data=data_str))

    bloqueio = Bloqueio(
        recurso_id=recurso_id,
        bloco_aula_id=bloco_id,
        data=data_bloqueio,
        tipo='bloco_especifico',
        justificativa=justificativa,
        escola_id=current_user.escola_id
    )

    db.session.add(bloqueio)
    db.session.commit()

    flash('Horário bloqueado com sucesso.', 'success')
    return redirect(url_for('gestor_escolar.dashboard', data=data_str))


@gestor_escolar.route('/desbloquear_aula', methods=['POST'])
@login_required
@papel_requerido('gestor_escolar')
def desbloquear_aula():
    bloqueio_id = request.form.get('bloqueio_id')
    data_str = request.form.get('data') # Para manter a navegação

    bloqueio = Bloqueio.query.get_or_404(bloqueio_id)
    
    if bloqueio.escola_id != current_user.escola_id:
        flash('Acesso negado.', 'error')
        return redirect(url_for('gestor_escolar.dashboard'))

    db.session.delete(bloqueio)
    db.session.commit()

    flash('Horário desbloqueado com sucesso.', 'success')
    return redirect(url_for('gestor_escolar.dashboard', data=data_str))


# === RECURSOS ===
@gestor_escolar.route('/recursos')
@login_required
def recursos():
    recursos = Recurso.query.filter_by(escola_id=current_user.escola_id).all()
    return render_template('gestor_escolar/recursos.html', usuario=current_user, recursos=recursos)

@gestor_escolar.route('/cadastrar_recurso', methods=['GET', 'POST'])
@login_required
def cadastrar_recurso():
    if request.method == 'POST':
        nome = request.form.get('nome').strip()
        descricao = request.form.get('descricao', '').strip()
        if not nome:
            flash('Nome do recurso é obrigatório.', 'error')
            return redirect(url_for('gestor_escolar.cadastrar_recurso'))
        recurso = Recurso(nome=nome, descricao=descricao, escola_id=current_user.escola_id)
        db.session.add(recurso)
        db.session.commit()
        flash(f'Recurso "{nome}" cadastrado com sucesso!', 'success')
        return redirect(url_for('gestor_escolar.recursos'))
    return render_template('gestor_escolar/cadastrar_recurso.html', usuario=current_user)

@gestor_escolar.route('/editar_recurso/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_recurso(id):
    recurso = Recurso.query.filter_by(id=id, escola_id=current_user.escola_id).first_or_404()
    if request.method == 'POST':
        nome = request.form.get('nome').strip()
        descricao = request.form.get('descricao', '').strip()
        if not nome:
            flash('Nome do recurso é obrigatório.', 'error')
            return redirect(url_for('gestor_escolar.editar_recurso', id=id))
        recurso.nome = nome
        recurso.descricao = descricao
        db.session.commit()
        flash(f'Recurso "{nome}" atualizado com sucesso!', 'success')
        return redirect(url_for('gestor_escolar.recursos'))
    return render_template('gestor_escolar/editar_recurso.html', usuario=current_user, recurso=recurso)

@gestor_escolar.route('/excluir_recurso/<int:id>', methods=['POST'])
@login_required
def excluir_recurso(id):
    recurso = Recurso.query.filter_by(id=id, escola_id=current_user.escola_id).first_or_404()
    nome = recurso.nome
    db.session.delete(recurso)
    db.session.commit()
    flash(f'Recurso "{nome}" excluído com sucesso!', 'success')
    return redirect(url_for('gestor_escolar.recursos'))

# === TURMAS ===
@gestor_escolar.route('/turmas')
@login_required
def turmas():
    turmas = Turma.query.filter_by(escola_id=current_user.escola_id).all()
    return render_template('gestor_escolar/turmas.html', usuario=current_user, turmas=turmas)

@gestor_escolar.route('/cadastrar_turma', methods=['GET', 'POST'])
@login_required
def cadastrar_turma():
    turnos = ['Matutino', 'Vespertino', 'Noturno']
    if request.method == 'POST':
        nome = request.form.get('nome').strip()
        turno = request.form.get('turno')
        if not nome or not turno:
            flash('Nome e turno são obrigatórios.', 'error')
            return redirect(url_for('gestor_escolar.cadastrar_turma'))
        turma = Turma(nome=nome, turno=turno, escola_id=current_user.escola_id)
        db.session.add(turma)
        db.session.commit()
        flash(f'Turma "{nome}" cadastrada com sucesso!', 'success')
        return redirect(url_for('gestor_escolar.turmas'))
    return render_template('gestor_escolar/cadastrar_turma.html', usuario=current_user, turnos=turnos)

@gestor_escolar.route('/editar_turma/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_turma(id):
    turma = Turma.query.filter_by(id=id, escola_id=current_user.escola_id).first_or_404()
    turnos = ['Matutino', 'Vespertino', 'Noturno']
    if request.method == 'POST':
        nome = request.form.get('nome').strip()
        turno = request.form.get('turno')
        if not nome or not turno:
            flash('Nome e turno são obrigatórios.', 'error')
            return redirect(url_for('gestor_escolar.editar_turma', id=id))
        turma.nome = nome
        turma.turno = turno
        db.session.commit()
        flash(f'Turma "{nome}" atualizada com sucesso!', 'success')
        return redirect(url_for('gestor_escolar.turmas'))
    return render_template('gestor_escolar/editar_turma.html', usuario=current_user, turma=turma, turnos=turnos)

@gestor_escolar.route('/excluir_turma/<int:id>', methods=['POST'])
@login_required
def excluir_turma(id):
    turma = Turma.query.filter_by(id=id, escola_id=current_user.escola_id).first_or_404()
    nome = turma.nome
    db.session.delete(turma)
    db.session.commit()
    flash(f'Turma "{nome}" excluída com sucesso!', 'success')
    return redirect(url_for('gestor_escolar.turmas'))

# === PROFESSORES ===
@gestor_escolar.route('/professores')
@login_required
def professores():
    view = request.args.get('view', 'professores')
    
    # Professores da própria escola (cadastro direto)
    professores_diretos = Usuario.query.filter_by(escola_id=current_user.escola_id, papel='professor').all()
    
    # Professores vinculados (aprovados)
    vinculos_aprovados = Vinculo.query.filter_by(escola_id=current_user.escola_id, status='aprovado').all()
    
    # Combinar listas e marcar origem
    todos_professores = []
    for p in professores_diretos:
        p.tipo_vinculo = 'Direto'
        todos_professores.append(p)
    
    for v in vinculos_aprovados:
        p = v.professor
        p.tipo_vinculo = 'Vinculado'
        p.vinculo_id = v.id
        todos_professores.append(p)
    
    # Solicitações pendentes
    solicitacoes = Vinculo.query.filter_by(escola_id=current_user.escola_id, status='pendente').all()
    
    return render_template('gestor_escolar/professores.html', 
                           usuario=current_user, 
                           professores=todos_professores,
                           solicitacoes=solicitacoes,
                           view=view)

@gestor_escolar.route('/confirmar_vinculo/<int:id>', methods=['GET'])
@login_required
@papel_requerido('gestor_escolar')
def confirmar_vinculo(id):
    try:
        vinculo = Vinculo.query.get_or_404(id)
        if vinculo.escola_id != current_user.escola_id:
            flash('Acesso negado.', 'error')
            return redirect(url_for('gestor_escolar.professores', view='solicitacoes'))
        
        if not vinculo.professor:
            flash('Erro: Professor não encontrado para este vínculo.', 'error')
            # Opcional: remover vínculo órfão
            # db.session.delete(vinculo)
            # db.session.commit()
            return redirect(url_for('gestor_escolar.professores', view='solicitacoes'))
        
        disciplinas = Disciplina.query.filter_by(escola_id=current_user.escola_id).all()
        turmas = Turma.query.filter_by(escola_id=current_user.escola_id).all()
        
        return render_template('gestor_escolar/confirmar_vinculo.html', 
                            usuario=current_user,
                            vinculo=vinculo, 
                            disciplinas=disciplinas, 
                            turmas=turmas)
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Erro ao abrir confirmação de vínculo: {str(e)}', 'error')
        return redirect(url_for('gestor_escolar.professores', view='solicitacoes'))

@gestor_escolar.route('/aprovar_vinculo/<int:id>', methods=['POST'])
@login_required
@papel_requerido('gestor_escolar')
def aprovar_vinculo(id):
    try:
        vinculo = Vinculo.query.get_or_404(id)
        if vinculo.escola_id != current_user.escola_id:
            flash('Acesso negado.', 'error')
            return redirect(url_for('gestor_escolar.professores', view='solicitacoes'))
        
        if not vinculo.professor:
            flash('Erro: Professor não encontrado.', 'error')
            return redirect(url_for('gestor_escolar.professores', view='solicitacoes'))

        vinculo.status = 'aprovado'
        professor = vinculo.professor

        # Adicionar disciplinas selecionadas
        disciplinas_ids = request.form.getlist('disciplinas')
        prof_disciplinas_ids = [d.id for d in professor.disciplinas]
        
        for d_id in disciplinas_ids:
            try:
                d_id_int = int(d_id)
                if d_id_int not in prof_disciplinas_ids:
                    disciplina = Disciplina.query.get(d_id_int)
                    if disciplina and disciplina.escola_id == current_user.escola_id:
                        professor.disciplinas.append(disciplina)
                        prof_disciplinas_ids.append(d_id_int) # Atualiza lista local
            except ValueError:
                continue
                
        # Adicionar turmas selecionadas
        turmas_ids = request.form.getlist('turmas')
        prof_turmas_ids = [t.id for t in professor.turmas]
        
        for t_id in turmas_ids:
            try:
                t_id_int = int(t_id)
                if t_id_int not in prof_turmas_ids:
                    turma = Turma.query.get(t_id_int)
                    if turma and turma.escola_id == current_user.escola_id:
                        professor.turmas.append(turma)
                        prof_turmas_ids.append(t_id_int) # Atualiza lista local
            except ValueError:
                continue

        db.session.commit()
        flash(f'Vínculo com professor {professor.nome} aprovado e atribuições realizadas!', 'success')
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        flash(f'Erro ao aprovar vínculo: {str(e)}', 'error')
        
    return redirect(url_for('gestor_escolar.professores', view='solicitacoes'))

@gestor_escolar.route('/rejeitar_vinculo/<int:id>', methods=['POST'])
@login_required
@papel_requerido('gestor_escolar')
def rejeitar_vinculo(id):
    vinculo = Vinculo.query.get_or_404(id)
    if vinculo.escola_id != current_user.escola_id:
        flash('Acesso negado.', 'error')
        return redirect(url_for('gestor_escolar.professores', view='solicitacoes'))
    
    vinculo.status = 'recusado'
    db.session.commit()
    flash(f'Solicitação de {vinculo.professor.nome} recusada.', 'success')
    return redirect(url_for('gestor_escolar.professores', view='solicitacoes'))

@gestor_escolar.route('/desvincular_professor/<int:id>', methods=['POST'])
@login_required
@papel_requerido('gestor_escolar')
def desvincular_professor(id):
    vinculo = Vinculo.query.get_or_404(id)
    if vinculo.escola_id != current_user.escola_id:
        flash('Acesso negado.', 'error')
        return redirect(url_for('gestor_escolar.professores'))
    
    # 1. Manter reservas anteriores (data < hoje ou data <= hoje?)
    from datetime import date
    hoje = date.today()
    
    # Busca reservas futuras deste professor NESTA escola
    reservas_futuras = Reserva.query.join(Recurso).filter(
        Reserva.professor_id == vinculo.professor_id,
        Reserva.data > hoje,
        Recurso.escola_id == current_user.escola_id
    ).all()
    
    # Excluir reservas futuras
    count_removidas = 0
    for reserva in reservas_futuras:
        db.session.delete(reserva)
        count_removidas += 1
    
    nome_professor = vinculo.professor.nome
    db.session.delete(vinculo)
    db.session.commit()
    
    msg = f'Professor {nome_professor} desvinculado.'
    if count_removidas > 0:
        msg += f' {count_removidas} reservas futuras foram liberadas.'
        
    flash(msg, 'success')
    return redirect(url_for('gestor_escolar.professores'))

@gestor_escolar.route('/desativar_professor_direto/<int:id>', methods=['POST'])
@login_required
@papel_requerido('gestor_escolar')
def desativar_professor_direto(id):
    professor = Usuario.query.filter_by(id=id, escola_id=current_user.escola_id, papel='professor').first_or_404()
    
    # 1. Cancelar reservas futuras (igual ao desvincular)
    from datetime import date
    hoje = date.today()
    
    reservas_futuras = Reserva.query.join(Recurso).filter(
        Reserva.professor_id == professor.id,
        Reserva.data > hoje,
        Recurso.escola_id == current_user.escola_id
    ).all()
    
    count_removidas = 0
    for reserva in reservas_futuras:
        db.session.delete(reserva)
        count_removidas += 1
        
    # 2. Desativar usuário
    professor.ativo = False
    db.session.commit()
    
    msg = f'Professor {professor.nome} foi desativado e desvinculado das atividades futuras.'
    if count_removidas > 0:
        msg += f' {count_removidas} reservas futuras foram liberadas.'
        
    flash(msg, 'success')
    return redirect(url_for('gestor_escolar.professores'))

@gestor_escolar.route('/cadastrar_professor', methods=['GET', 'POST'])
@login_required
def cadastrar_professor():
    if request.method == 'POST':
        nome = request.form.get('nome').strip()
        email = request.form.get('email').strip()
        senha = request.form.get('senha').strip()
        telefone = request.form.get('telefone', '').strip()
        disciplinas_str = request.form.get('disciplinas', '').strip()

        if not nome or not email or not senha:
            flash('Nome, e-mail e senha são obrigatórios.', 'error')
            return redirect(url_for('gestor_escolar.cadastrar_professor'))
        if Usuario.query.filter_by(email=email).first():
            flash('E-mail já cadastrado.', 'error')
            return redirect(url_for('gestor_escolar.cadastrar_professor'))
        
        professor = Usuario(
            nome=nome,
            email=email,
            telefone=telefone,
            senha=generate_password_hash(senha, method='pbkdf2:sha256'),
            papel='professor',
            escola_id=current_user.escola_id,
            regiao_id=current_user.regiao_id,
            ativo=True
        )

        # Processar disciplinas
        if disciplinas_str:
            nomes_disciplinas = [d.strip() for d in disciplinas_str.split(',') if d.strip()]
            for nome_d in nomes_disciplinas:
                # Verifica se disciplina já existe na escola, senão cria
                disciplina = Disciplina.query.filter_by(nome=nome_d, escola_id=current_user.escola_id).first()
                if not disciplina:
                    disciplina = Disciplina(nome=nome_d, escola_id=current_user.escola_id)
                    db.session.add(disciplina)
                professor.disciplinas.append(disciplina)

        db.session.add(professor)
        db.session.commit()
        flash(f'Professor "{nome}" cadastrado com sucesso!', 'success')
        return redirect(url_for('gestor_escolar.professores'))
    return render_template('gestor_escolar/cadastrar_professor.html', usuario=current_user)

@gestor_escolar.route('/editar_professor/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_professor(id):
    professor = Usuario.query.filter_by(id=id, escola_id=current_user.escola_id, papel='professor').first_or_404()
    if request.method == 'POST':
        nome = request.form.get('nome').strip()
        email = request.form.get('email').strip()
        telefone = request.form.get('telefone', '').strip()
        nova_senha = request.form.get('nova_senha', '').strip()
        disciplinas_str = request.form.get('disciplinas', '').strip()
        ativo = request.form.get('ativo') == 'on'

        if not nome or not email:
            flash('Nome e e-mail são obrigatórios.', 'error')
            return redirect(url_for('gestor_escolar.editar_professor', id=id))

        outro = Usuario.query.filter(Usuario.email == email, Usuario.id != id).first()
        if outro:
            flash('E-mail já em uso.', 'error')
            return redirect(url_for('gestor_escolar.editar_professor', id=id))

        professor.nome = nome
        professor.email = email
        professor.telefone = telefone
        professor.ativo = ativo
        if nova_senha:
            professor.senha = generate_password_hash(nova_senha, method='pbkdf2:sha256')

        # Atualizar disciplinas
        professor.disciplinas = [] # Limpa as atuais
        if disciplinas_str:
            nomes_disciplinas = [d.strip() for d in disciplinas_str.split(',') if d.strip()]
            for nome_d in nomes_disciplinas:
                disciplina = Disciplina.query.filter_by(nome=nome_d, escola_id=current_user.escola_id).first()
                if not disciplina:
                    disciplina = Disciplina(nome=nome_d, escola_id=current_user.escola_id)
                    db.session.add(disciplina)
                professor.disciplinas.append(disciplina)

        db.session.commit()
        flash(f'Professor "{nome}" atualizado com sucesso!', 'success')
        return redirect(url_for('gestor_escolar.professores'))
    return render_template('gestor_escolar/editar_professor.html', usuario=current_user, professor=professor)

@gestor_escolar.route('/gerenciar_atribuicoes/<int:id>', methods=['GET'])
@login_required
@papel_requerido('gestor_escolar')
def gerenciar_atribuicoes(id):
    try:
        professor = Usuario.query.get_or_404(id)
        
        # Verificar se o professor pertence à escola (direto) ou tem vínculo aprovado
        is_direto = (professor.escola_id == current_user.escola_id)
        is_vinculado = Vinculo.query.filter_by(professor_id=id, escola_id=current_user.escola_id, status='aprovado').first()
        
        if not (is_direto or is_vinculado):
            flash('Acesso negado. Professor não vinculado a esta escola.', 'error')
            return redirect(url_for('gestor_escolar.professores'))
        
        disciplinas = Disciplina.query.filter_by(escola_id=current_user.escola_id).all()
        turmas = Turma.query.filter_by(escola_id=current_user.escola_id).all()
        
        return render_template('gestor_escolar/gerenciar_atribuicoes.html', 
                            usuario=current_user,
                            professor=professor, 
                            disciplinas=disciplinas, 
                            turmas=turmas)
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Erro ao carregar atribuições: {str(e)}', 'error')
        return redirect(url_for('gestor_escolar.professores'))

@gestor_escolar.route('/salvar_atribuicoes/<int:id>', methods=['POST'])
@login_required
@papel_requerido('gestor_escolar')
def salvar_atribuicoes(id):
    professor = Usuario.query.get_or_404(id)
    
    # Verificar permissão (mesma lógica)
    is_direto = (professor.escola_id == current_user.escola_id)
    is_vinculado = Vinculo.query.filter_by(professor_id=id, escola_id=current_user.escola_id, status='aprovado').first()
    
    if not (is_direto or is_vinculado):
        flash('Acesso negado.', 'error')
        return redirect(url_for('gestor_escolar.professores'))
        
    # 1. Recuperar IDs das seleções do formulário
    ids_disciplinas = request.form.getlist('disciplinas')
    ids_turmas = request.form.getlist('turmas')
    
    # 2. Atualizar Disciplinas (Mantendo as de outras escolas)
    novas_disciplinas = [d for d in professor.disciplinas if d.escola_id != current_user.escola_id]
    
    for d_id in ids_disciplinas:
        d = Disciplina.query.get(d_id)
        if d and d.escola_id == current_user.escola_id:
            novas_disciplinas.append(d)
            
    professor.disciplinas = novas_disciplinas
    
    # 3. Atualizar Turmas (Mantendo as de outras escolas)
    novas_turmas = [t for t in professor.turmas if t.escola_id != current_user.escola_id]
    
    for t_id in ids_turmas:
        t = Turma.query.get(t_id)
        if t and t.escola_id == current_user.escola_id:
            novas_turmas.append(t)
            
    professor.turmas = novas_turmas
    
    db.session.commit()
    flash('Atribuições atualizadas com sucesso!', 'success')
    return redirect(url_for('gestor_escolar.professores'))

# === GRADE HORÁRIA ===
MAX_AULAS = 10  # Número máximo de aulas por turno

@gestor_escolar.route('/grade')
@login_required
def grade():
    blocos = BlocoAula.query.filter_by(escola_id=current_user.escola_id).order_by(BlocoAula.dia_semana, BlocoAula.id).all()
    
    # 1. Organizar por Dia -> Turno -> Aulas (Estrutura)
    daily_structures = {} # dia_idx -> { 'Matutino': ['Aula 1', ...], ... }
    dias_map = dict(DIAS_SEMANA)
    
    for bloco in blocos:
        dia_idx = bloco.dia_semana
        
        # Parse do periodo (ex: "Matutino - Aula 1")
        if ' - ' in bloco.periodo:
            parts = bloco.periodo.split(' - ', 1)
            turno = parts[0]
            aula = parts[1]
        else:
            turno = 'Geral'
            aula = bloco.periodo
            
        if dia_idx not in daily_structures:
            daily_structures[dia_idx] = {}
            
        if turno not in daily_structures[dia_idx]:
            daily_structures[dia_idx][turno] = []
            
        daily_structures[dia_idx][turno].append(aula)

    # 2. Agrupar dias com estrutura idêntica
    grade_agrupada = []
    processed_days = set()
    
    # Iterar pelos dias ordenados para manter consistência
    sorted_days = sorted(daily_structures.keys())
    
    for dia_idx in sorted_days:
        if dia_idx in processed_days:
            continue
            
        current_struct = daily_structures[dia_idx]
        matching_days = [dia_idx]
        processed_days.add(dia_idx)
        
        # Verificar dias subsequentes
        for other_dia in sorted_days:
            if other_dia <= dia_idx: continue
            if other_dia in processed_days: continue
            
            if daily_structures[other_dia] == current_struct:
                matching_days.append(other_dia)
                processed_days.add(other_dia)
        
        # Formatar nomes dos dias
        dias_nomes = [dias_map.get(d, 'Desconhecido') for d in matching_days]
        
        grade_agrupada.append({
            'dias_indices': matching_days,
            'dias_nomes': dias_nomes,
            'turnos': current_struct
        })
    
    return render_template('gestor_escolar/grade.html', usuario=current_user, grade_agrupada=grade_agrupada)

@gestor_escolar.route('/configurar_grade', methods=['GET', 'POST'])
@login_required
def configurar_grade():
    if request.method == 'POST':
        dias = request.form.getlist('dias')
        turnos = request.form.getlist('turnos')

        if not dias or not turnos:
            flash('Selecione pelo menos um dia e um turno.', 'error')
            return redirect(url_for('gestor_escolar.configurar_grade'))

        # Remove blocos antigos
        try:
            # Verifica se existem reservas futuras ou bloqueios antes de tentar deletar
            # Otimização: Apenas deletar se não houver conflitos, ou usar DELETE CASCADE se o banco suportasse,
            # mas aqui vamos prevenir erros de integridade.
            
            # Tenta limpar bloqueios antigos da escola primeiro (opcional, mas ajuda)
            # Bloqueio.query.filter_by(escola_id=current_user.escola_id).delete() 
            
            BlocoAula.query.filter_by(escola_id=current_user.escola_id).delete()

            # ✅ NOVA LÓGICA: Quantidade de aulas por turno específica
            for dia in dias:
                for turno in turnos:
                    qtd_aulas = request.form.get(f'aulas_{turno}', type=int)
                    if not qtd_aulas or qtd_aulas < 1:
                        qtd_aulas = 5 # Default de segurança

                    periodos = [f'Aula {i}' for i in range(1, qtd_aulas + 1)]
                    for periodo in periodos:
                        # Nome único: "Matutino - Aula 1"
                        nome_bloco = f"{turno} - {periodo}"
                        bloco = BlocoAula(dia_semana=int(dia), periodo=nome_bloco, escola_id=current_user.escola_id)
                        db.session.add(bloco)
            
            db.session.commit()
            flash('Grade horária configurada com sucesso!', 'success')
            return redirect(url_for('gestor_escolar.grade'))

        except IntegrityError:
            db.session.rollback()
            flash('Não foi possível alterar a grade pois existem Reservas ou Bloqueios ativos vinculados aos horários atuais. Por favor, cancele as reservas futuras antes de reconfigurar a grade.', 'error')
            return redirect(url_for('gestor_escolar.grade'))
        except DataError as e:
            db.session.rollback()
            flash(f'Erro de dados: {str(e)}', 'error')
            return redirect(url_for('gestor_escolar.configurar_grade'))
        except Exception as e:
            db.session.rollback()
            print(f"Erro ao configurar grade: {e}")
            flash(f'Erro interno ao salvar grade: {str(e)}', 'error')
            return redirect(url_for('gestor_escolar.configurar_grade'))

    return render_template('gestor_escolar/configurar_grade.html',
                           usuario=current_user,
                           dias_semana=[d for d in DIAS_SEMANA.items() if d[0] < 5],  # Só dias úteis (simplificado)
                           turnos=['Matutino', 'Vespertino', 'Noturno'],
                           max_aulas=MAX_AULAS)

@gestor_escolar.route('/configuracoes')
@login_required
@papel_requerido('gestor_escolar')
def configuracoes():
    return render_template('gestor_escolar/configuracoes.html', usuario=current_user)

@gestor_escolar.route('/metricas')
@login_required
@papel_requerido('gestor_escolar')
def metricas():
    # 1. Filtro de Data
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    
    today = date.today()
    if not data_inicio_str:
        # Primeiro dia do mês corrente
        data_inicio = date(today.year, today.month, 1)
    else:
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        except ValueError:
             data_inicio = date(today.year, today.month, 1)
        
    if not data_fim_str:
        # Último dia do mês corrente
        _, last_day = calendar.monthrange(today.year, today.month)
        data_fim = date(today.year, today.month, last_day)
    else:
        try:
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        except ValueError:
            _, last_day = calendar.monthrange(today.year, today.month)
            data_fim = date(today.year, today.month, last_day)

    # Query Base: Reservas da escola no período
    query_base = Reserva.query.join(Recurso).filter(
        Recurso.escola_id == current_user.escola_id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim
    )

    # 2. Métricas por Recurso (Total Solicitado, Concretizadas, Aproveitamento, Possibilidade, % Agendamento)
    recursos = Recurso.query.filter_by(escola_id=current_user.escola_id).all()
    
    # Calcular total de slots disponíveis por recurso no período
    blocos = BlocoAula.query.filter_by(escola_id=current_user.escola_id).all()
    blocos_por_dia = {}
    for b in blocos:
        blocos_por_dia[b.dia_semana] = blocos_por_dia.get(b.dia_semana, 0) + 1
    
    total_slots_periodo = 0
    curr = data_inicio
    while curr <= data_fim:
        total_slots_periodo += blocos_por_dia.get(curr.weekday(), 0)
        curr += timedelta(days=1)
    
    metricas_recursos = []
    for recurso in recursos:
        # Total Solicitado (todas as reservas do recurso no período)
        total_solicitado = Reserva.query.filter(
            Reserva.recurso_id == recurso.id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim
        ).count()
        
        # Concretizadas (status = confirmada)
        concretizadas = Reserva.query.filter(
            Reserva.recurso_id == recurso.id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim,
            Reserva.status == 'confirmada'
        ).count()
        
        # Aproveitamento (% de concretizadas sobre total solicitado)
        aproveitamento = round((concretizadas / total_solicitado * 100), 1) if total_solicitado > 0 else 0
        
        # Possibilidade de agendamento no período (total de slots - bloqueios do recurso)
        num_bloqueios_recurso = Bloqueio.query.filter(
            Bloqueio.recurso_id == recurso.id,
            Bloqueio.data >= data_inicio,
            Bloqueio.data <= data_fim
        ).count()
        possibilidade_agendamento = total_slots_periodo - num_bloqueios_recurso
        if possibilidade_agendamento < 0:
            possibilidade_agendamento = 0
        
        # % de agendamento (concretizadas / possibilidade_agendamento * 100)
        pct_agendamento = round((concretizadas / possibilidade_agendamento * 100), 1) if possibilidade_agendamento > 0 else 0
        
        # Top Professores por Recurso
        top_professores_recurso = Reserva.query.join(Usuario).filter(
            Reserva.recurso_id == recurso.id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim,
            Reserva.status.notin_(['cancelada', 'nao_realizada'])
        ).with_entities(
            Usuario.nome, func.count(Reserva.id)
        ).group_by(Usuario.nome).order_by(desc(func.count(Reserva.id))).limit(5).all()
        
        professores_com_pct = []
        for nome, total in top_professores_recurso:
            pct = round((total / total_solicitado * 100), 1) if total_solicitado > 0 else 0
            professores_com_pct.append({'nome': nome, 'total': total, 'pct': pct})
        
        # Top Turmas por Recurso
        top_turmas_recurso = Reserva.query.join(Turma).filter(
            Reserva.recurso_id == recurso.id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim,
            Reserva.status.notin_(['cancelada', 'nao_realizada']),
            Reserva.turma_id != None
        ).with_entities(
            Turma.nome, func.count(Reserva.id)
        ).group_by(Turma.nome).order_by(desc(func.count(Reserva.id))).limit(5).all()
        
        turmas_com_pct = []
        for nome, total in top_turmas_recurso:
            pct = round((total / total_solicitado * 100), 1) if total_solicitado > 0 else 0
            turmas_com_pct.append({'nome': nome, 'total': total, 'pct': pct})
        
        metricas_recursos.append({
            'nome': recurso.nome,
            'total_solicitado': total_solicitado,
            'concretizadas': concretizadas,
            'aproveitamento': aproveitamento,
            'possibilidade_agendamento': possibilidade_agendamento,
            'pct_agendamento': pct_agendamento,
            'professores': professores_com_pct,
            'turmas': turmas_com_pct
        })
    
    # 3. Status das Reservas (geral)
    status_counts = query_base.with_entities(
        Reserva.status, func.count(Reserva.id)
    ).group_by(Reserva.status).all()
    
    status_dict = {s: c for s, c in status_counts}
    realizadas = status_dict.get('confirmada', 0)
    nao_realizadas = status_dict.get('nao_realizada', 0)
    canceladas = status_dict.get('cancelada', 0)
    
    # 4. Reservas Possíveis (geral)
    num_recursos = len(recursos)
    num_bloqueios = Bloqueio.query.join(Recurso).filter(
        Recurso.escola_id == current_user.escola_id,
        Bloqueio.data >= data_inicio,
        Bloqueio.data <= data_fim
    ).count()

    total_possiveis = (total_slots_periodo * num_recursos) - num_bloqueios
    if total_possiveis < 0: total_possiveis = 0
    
    # Capacidade por recurso (total_possiveis dividido pela quantidade de recursos)
    capacidade_por_recurso = round(total_possiveis / num_recursos, 1) if num_recursos > 0 else 0
    
    # Construir lookup de possibilidade_agendamento por nome do recurso
    possibilidade_por_recurso = {}
    for r in metricas_recursos:
        possibilidade_por_recurso[r['nome']] = r['possibilidade_agendamento']
    
    # 5. Top 10 Professores (com detalhamento por recurso)
    top_professores = query_base.join(Usuario).with_entities(
        Usuario.nome, func.count(Reserva.id)
    ).group_by(Usuario.nome).order_by(desc(func.count(Reserva.id))).limit(10).all()
    
    # Calcular % de cada professor em relação ao total de reservas válidas
    total_reservas_validas = realizadas
    top_professores_com_pct = []
    for nome, total in top_professores:
        pct = round((total / total_reservas_validas * 100), 1) if total_reservas_validas > 0 else 0
        # Reservas por recurso para este professor
        prof_recursos = Reserva.query.join(Recurso).join(Usuario).filter(
            Usuario.nome == nome,
            Recurso.escola_id == current_user.escola_id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim,
            Reserva.status.notin_(['cancelada', 'nao_realizada'])
        ).with_entities(
            Recurso.nome, func.count(Reserva.id)
        ).group_by(Recurso.nome).order_by(desc(func.count(Reserva.id))).all()
        
        prof_recursos_pct = []
        for rec_nome, rec_total in prof_recursos:
            possib = possibilidade_por_recurso.get(rec_nome, 0)
            rec_pct = round((rec_total / possib * 100), 1) if possib > 0 else 0
            prof_recursos_pct.append({'nome': rec_nome, 'total': rec_total, 'pct': rec_pct})
        
        top_professores_com_pct.append({
            'nome': nome,
            'total': total,
            'pct': pct,
            'recursos': prof_recursos_pct
        })
    
    # 6. Top 10 Turmas (com detalhamento por recurso)
    top_turmas = query_base.join(Turma).with_entities(
        Turma.nome, func.count(Reserva.id)
    ).group_by(Turma.nome).order_by(desc(func.count(Reserva.id))).limit(10).all()
    
    # Calcular % de cada turma em relação ao total de reservas válidas
    top_turmas_com_pct = []
    for nome, total in top_turmas:
        pct = round((total / total_reservas_validas * 100), 1) if total_reservas_validas > 0 else 0
        # Reservas por recurso para esta turma
        turma_recursos = Reserva.query.join(Recurso).join(Turma).filter(
            Turma.nome == nome,
            Recurso.escola_id == current_user.escola_id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim,
            Reserva.status.notin_(['cancelada', 'nao_realizada'])
        ).with_entities(
            Recurso.nome, func.count(Reserva.id)
        ).group_by(Recurso.nome).order_by(desc(func.count(Reserva.id))).all()
        
        turma_recursos_pct = []
        for rec_nome, rec_total in turma_recursos:
            possib = possibilidade_por_recurso.get(rec_nome, 0)
            rec_pct = round((rec_total / possib * 100), 1) if possib > 0 else 0
            
            # Professores que usaram este recurso para esta turma
            profs_no_recurso = Reserva.query.join(Usuario).join(Recurso).join(Turma).filter(
                Turma.nome == nome,
                Recurso.nome == rec_nome,
                Recurso.escola_id == current_user.escola_id,
                Reserva.data >= data_inicio,
                Reserva.data <= data_fim,
                Reserva.status.notin_(['cancelada', 'nao_realizada'])
            ).with_entities(
                Usuario.nome, func.count(Reserva.id)
            ).group_by(Usuario.nome).order_by(desc(func.count(Reserva.id))).all()
            
            profs_list = []
            for p_nome, p_total in profs_no_recurso:
                p_pct = round((p_total / possib * 100), 1) if possib > 0 else 0
                profs_list.append({'nome': p_nome, 'total': p_total, 'pct': p_pct})
            
            # Disciplinas usadas neste recurso para esta turma
            discs_no_recurso = Reserva.query.join(Disciplina).join(Recurso).join(Turma).filter(
                Turma.nome == nome,
                Recurso.nome == rec_nome,
                Recurso.escola_id == current_user.escola_id,
                Reserva.data >= data_inicio,
                Reserva.data <= data_fim,
                Reserva.status.notin_(['cancelada', 'nao_realizada']),
                Reserva.disciplina_id != None
            ).with_entities(
                Disciplina.nome, func.count(Reserva.id)
            ).group_by(Disciplina.nome).order_by(desc(func.count(Reserva.id))).all()
            
            discs_list = []
            for d_nome, d_total in discs_no_recurso:
                d_pct = round((d_total / possib * 100), 1) if possib > 0 else 0
                discs_list.append({'nome': d_nome, 'total': d_total, 'pct': d_pct})
            
            turma_recursos_pct.append({
                'nome': rec_nome,
                'total': rec_total,
                'pct': rec_pct,
                'professores': profs_list,
                'disciplinas': discs_list
            })
        
        top_turmas_com_pct.append({
            'nome': nome,
            'total': total,
            'pct': pct,
            'recursos': turma_recursos_pct
        })
    
    return render_template('gestor_escolar/metricas.html',
                           usuario=current_user,
                           data_inicio=data_inicio,
                           data_fim=data_fim,
                           metricas_recursos=metricas_recursos,
                           total_possiveis=total_possiveis,
                           capacidade_por_recurso=capacidade_por_recurso,
                           realizadas=realizadas,
                           nao_realizadas=nao_realizadas,
                           canceladas=canceladas,
                           top_professores=top_professores_com_pct,
                           top_turmas=top_turmas_com_pct)

@gestor_escolar.route('/metricas/pdf')
@login_required
@papel_requerido('gestor_escolar')
def metricas_pdf():
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    
    today = date.today()
    if not data_inicio_str:
        data_inicio = date(today.year, today.month, 1)
    else:
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        except ValueError:
            data_inicio = date(today.year, today.month, 1)
        
    if not data_fim_str:
        _, last_day = calendar.monthrange(today.year, today.month)
        data_fim = date(today.year, today.month, last_day)
    else:
        try:
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        except ValueError:
            _, last_day = calendar.monthrange(today.year, today.month)
            data_fim = date(today.year, today.month, last_day)

    query_base = Reserva.query.join(Recurso).filter(
        Recurso.escola_id == current_user.escola_id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim
    )

    recursos = Recurso.query.filter_by(escola_id=current_user.escola_id).all()

    blocos = BlocoAula.query.filter_by(escola_id=current_user.escola_id).all()
    blocos_por_dia = {}
    for b in blocos:
        blocos_por_dia[b.dia_semana] = blocos_por_dia.get(b.dia_semana, 0) + 1
    
    total_slots_periodo = 0
    curr = data_inicio
    while curr <= data_fim:
        total_slots_periodo += blocos_por_dia.get(curr.weekday(), 0)
        curr += timedelta(days=1)
    
    metricas_recursos = []
    for recurso in recursos:
        total_solicitado = Reserva.query.filter(
            Reserva.recurso_id == recurso.id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim
        ).count()
        
        concretizadas = Reserva.query.filter(
            Reserva.recurso_id == recurso.id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim,
            Reserva.status == 'confirmada'
        ).count()
        
        aproveitamento = round((concretizadas / total_solicitado * 100), 1) if total_solicitado > 0 else 0
        
        num_bloqueios_recurso = Bloqueio.query.filter(
            Bloqueio.recurso_id == recurso.id,
            Bloqueio.data >= data_inicio,
            Bloqueio.data <= data_fim
        ).count()
        possibilidade_agendamento = total_slots_periodo - num_bloqueios_recurso
        if possibilidade_agendamento < 0:
            possibilidade_agendamento = 0
        
        pct_agendamento = round((concretizadas / possibilidade_agendamento * 100), 1) if possibilidade_agendamento > 0 else 0
        
        metricas_recursos.append({
            'nome': recurso.nome,
            'total_solicitado': total_solicitado,
            'concretizadas': concretizadas,
            'aproveitamento': aproveitamento,
            'possibilidade_agendamento': possibilidade_agendamento,
            'pct_agendamento': pct_agendamento
        })

    status_counts = query_base.with_entities(
        Reserva.status, func.count(Reserva.id)
    ).group_by(Reserva.status).all()
    
    status_dict = {s: c for s, c in status_counts}
    realizadas = status_dict.get('confirmada', 0)
    nao_realizadas = status_dict.get('nao_realizada', 0)
    canceladas = status_dict.get('cancelada', 0)
    
    num_recursos = len(recursos)
    num_bloqueios = Bloqueio.query.join(Recurso).filter(
        Recurso.escola_id == current_user.escola_id,
        Bloqueio.data >= data_inicio,
        Bloqueio.data <= data_fim
    ).count()

    total_possiveis = (total_slots_periodo * num_recursos) - num_bloqueios
    if total_possiveis < 0:
        total_possiveis = 0
    capacidade_por_recurso = round(total_possiveis / num_recursos, 1) if num_recursos > 0 else 0
    
    escola = Escola.query.get(current_user.escola_id)
    escola_nome = escola.nome if escola else 'Escola'

    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    effective_width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(effective_width, 8, f"Relatorio de Metricas - {escola_nome}", new_x="LMARGIN", new_y="NEXT", wrapmode="CHAR")
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f"Periodo: {data_inicio.strftime('%d/%m/%Y')} ate {data_fim.strftime('%d/%m/%Y')}", ln=True)
    pdf.cell(0, 6, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True)
    pdf.ln(2)

    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 7, "Resumo", ln=True)
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f"Realizadas: {realizadas}", ln=True)
    pdf.cell(0, 6, f"Nao concretizadas: {nao_realizadas}", ln=True)
    pdf.cell(0, 6, f"Canceladas: {canceladas}", ln=True)
    pdf.cell(0, 6, f"Total possiveis: {total_possiveis}", ln=True)
    pdf.cell(0, 6, f"Capacidade por recurso: {capacidade_por_recurso}", ln=True)
    pdf.ln(2)

    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 7, "Metricas por recurso", ln=True)
    pdf.set_font('Helvetica', '', 9)
    if metricas_recursos:
        metricas_recursos.sort(key=lambda r: r['total_solicitado'], reverse=True)
        for r in metricas_recursos:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(
                effective_width,
                5,
                f"- {r['nome']} | Solicitado: {r['total_solicitado']} | Concretizadas: {r['concretizadas']} | Aproveitamento: {r['aproveitamento']}% | Possib.: {r['possibilidade_agendamento']} | % Agend.: {r['pct_agendamento']}%",
                new_x="LMARGIN",
                new_y="NEXT",
                wrapmode="CHAR"
            )
    else:
        pdf.cell(0, 6, "Sem dados no periodo.", ln=True)

    safe_name = ''.join([c if c.isalnum() or c in ('_', '-') else '_' for c in escola_nome.replace(' ', '_')])
    filename = f"relatorio_metricas_{safe_name}.pdf"
    content = pdf.output(dest='S').encode('latin1', errors='replace')
    return send_file(BytesIO(content), mimetype='application/pdf', as_attachment=True, download_name=filename)
