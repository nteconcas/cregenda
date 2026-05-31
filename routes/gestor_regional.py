# routes/gestor_regional.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from models import db, Usuario, Escola, Regiao, Recurso, Reserva, Turma, Disciplina, BlocoAula, Bloqueio
from functools import wraps
from datetime import datetime, date, timedelta
from sqlalchemy import func, case
from io import BytesIO
from fpdf import FPDF

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

gestor_regional = Blueprint('gestor_regional', __name__)

@gestor_regional.route('/dashboard')
@login_required
@papel_requerido('gestor_regional')
def dashboard():
    # Calcular datas padrão (mês corrente)
    hoje = date.today()
    primeiro_dia = date(hoje.year, hoje.month, 1)
    
    # Para o último dia, pegamos o primeiro dia do próximo mês e subtraímos 1 dia
    if hoje.month == 12:
        proximo_mes = date(hoje.year + 1, 1, 1)
    else:
        proximo_mes = date(hoje.year, hoje.month + 1, 1)
    ultimo_dia = proximo_mes - timedelta(days=1)
    
    escolas = Escola.query.filter_by(regiao_id=current_user.regiao_id).all()
    total_escolas = len(escolas)
    total_recursos = db.session.query(Recurso).join(Escola).filter(Escola.regiao_id == current_user.regiao_id).count()
    total_professores = db.session.query(Usuario).filter_by(papel='professor').join(Escola).filter(Escola.regiao_id == current_user.regiao_id).count()
    
    # Reservas Confirmadas (exclui canceladas e não realizadas)
    total_reservas = db.session.query(Reserva).join(Usuario, Reserva.professor_id == Usuario.id).join(Escola).filter(
        Escola.regiao_id == current_user.regiao_id,
        Reserva.status.notin_(['cancelada', 'nao_realizada'])
    ).count()

    dados_escolas = []
    for escola in escolas:
        recursos = Recurso.query.filter_by(escola_id=escola.id).count()
        professores = Usuario.query.filter_by(escola_id=escola.id, papel='professor').count()
        
        # Reservas Confirmadas por Escola (Mês Corrente)
        reservas = Reserva.query.join(Usuario, Reserva.professor_id == Usuario.id).filter(
            Usuario.escola_id == escola.id,
            Reserva.status.notin_(['cancelada', 'nao_realizada']),
            Reserva.data >= primeiro_dia,
            Reserva.data <= ultimo_dia
        ).count()
        
        dados_escolas.append({
            'escola': escola,
            'recursos': recursos,
            'professores': professores,
            'reservas': reservas
        })

    return render_template('gestor_regional/dashboard.html',
                           usuario=current_user,
                           escolas=escolas,
                           total_escolas=total_escolas,
                           total_recursos=total_recursos,
                           total_professores=total_professores,
                           total_reservas=total_reservas,
                           dados_escolas=dados_escolas,
                           data_inicio_padrao=primeiro_dia.strftime('%Y-%m-%d'),
                           data_fim_padrao=ultimo_dia.strftime('%Y-%m-%d'),
                           mes_referencia=primeiro_dia.strftime('%m/%Y'))


@gestor_regional.route('/cadastrar_escola', methods=['GET', 'POST'])
@login_required
@papel_requerido('gestor_regional')
def cadastrar_escola():
    if request.method == 'POST':
        nome_escola = request.form.get('nome_escola').strip()
        nome_gestor = request.form.get('nome_gestor').strip()
        email_gestor = request.form.get('email_gestor').strip()
        senha_gestor = request.form.get('senha_gestor').strip()
        telefone_gestor = request.form.get('telefone_gestor', '').strip()

        if not nome_escola or not nome_gestor or not email_gestor or not senha_gestor:
            flash('Todos os campos são obrigatórios.', 'error')
            return redirect(url_for('gestor_regional.cadastrar_escola'))

        if Usuario.query.filter_by(email=email_gestor).first():
            flash('E-mail do gestor já cadastrado.', 'error')
            return redirect(url_for('gestor_regional.cadastrar_escola'))

        escola = Escola(nome=nome_escola, regiao_id=current_user.regiao_id)
        db.session.add(escola)
        db.session.flush()

        gestor = Usuario(
            nome=nome_gestor,
            email=email_gestor,
            telefone=telefone_gestor,
            senha=generate_password_hash(senha_gestor, method='pbkdf2:sha256'),
            papel='gestor_escolar',
            escola_id=escola.id,
            regiao_id=current_user.regiao_id
        )
        db.session.add(gestor)
        db.session.commit()
        flash(f'Escola "{nome_escola}" e gestor cadastrados com sucesso!', 'success')
        return redirect(url_for('gestor_regional.cadastrar_escola'))

    escolas = Escola.query.filter_by(regiao_id=current_user.regiao_id).all()
    return render_template('gestor_regional/cadastrar_escola.html', usuario=current_user, escolas=escolas)

@gestor_regional.route('/editar_escola/<int:id>', methods=['GET', 'POST'])
@login_required
@papel_requerido('gestor_regional')
def editar_escola(id):
    escola = Escola.query.filter_by(id=id, regiao_id=current_user.regiao_id).first_or_404()
    gestores = Usuario.query.filter_by(escola_id=id, papel='gestor_escolar').all()

    if request.method == 'POST':
        novo_nome = request.form.get('nome_escola').strip()
        if not novo_nome:
            flash('Nome da escola é obrigatório.', 'error')
            return redirect(url_for('gestor_regional.editar_escola', id=id))
        escola.nome = novo_nome

        for gestor in gestores:
            nome_key = f'nome_gestor_{gestor.id}'
            email_key = f'email_gestor_{gestor.id}'
            telefone_key = f'telefone_gestor_{gestor.id}'
            senha_key = f'senha_gestor_{gestor.id}'

            gestor.nome = request.form.get(nome_key, gestor.nome)
            gestor.email = request.form.get(email_key, gestor.email)
            gestor.telefone = request.form.get(telefone_key, gestor.telefone)
            nova_senha = request.form.get(senha_key, '').strip()
            if nova_senha:
                gestor.senha = generate_password_hash(nova_senha, method='pbkdf2:sha256')

        novo_nome_gestor = request.form.get('novo_nome_gestor', '').strip()
        if novo_nome_gestor:
            novo_email = request.form.get('novo_email_gestor', '').strip()
            nova_senha_gestor = request.form.get('nova_senha_novo_gestor', '').strip()
            if not novo_email or not nova_senha_gestor:
                flash('Para adicionar novo gestor, preencha e-mail e senha.', 'error')
                return redirect(url_for('gestor_regional.editar_escola', id=id))
            if Usuario.query.filter_by(email=novo_email).first():
                flash('E-mail já em uso.', 'error')
                return redirect(url_for('gestor_regional.editar_escola', id=id))
            novo_gestor = Usuario(
                nome=novo_nome_gestor,
                email=novo_email,
                senha=generate_password_hash(nova_senha_gestor, method='pbkdf2:sha256'),
                telefone=request.form.get('novo_telefone_gestor', ''),
                papel='gestor_escolar',
                escola_id=escola.id,
                regiao_id=current_user.regiao_id
            )
            db.session.add(novo_gestor)

        db.session.commit()
        flash('Escola e gestores atualizados com sucesso!', 'success')
        return redirect(url_for('gestor_regional.editar_escola', id=id))

    return render_template('gestor_regional/editar_escola.html',
                           usuario=current_user,
                           escola=escola,
                           gestores=gestores)

@gestor_regional.route('/excluir_escola/<int:id>', methods=['POST'])
@login_required
@papel_requerido('gestor_regional')
def excluir_escola(id):
    escola = Escola.query.filter_by(id=id, regiao_id=current_user.regiao_id).first_or_404()
    Usuario.query.filter_by(escola_id=id, papel='gestor_escolar').delete()
    Recurso.query.filter_by(escola_id=id).delete()
    Reserva.query.join(Usuario, Reserva.professor_id == Usuario.id).filter(Usuario.escola_id == id).delete()
    db.session.delete(escola)
    db.session.commit()
    flash(f'Escola "{escola.nome}" excluída com sucesso!', 'success')
    return redirect(url_for('dashboard'))

@gestor_regional.route('/relatorio_escola/<int:id>')
@login_required
@papel_requerido('gestor_regional')
def relatorio_escola(id):
    escola = Escola.query.filter_by(id=id, regiao_id=current_user.regiao_id).first_or_404()
    
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')

    # Datas padrão se não fornecidas
    hoje = date.today()
    if not data_inicio_str:
        data_inicio = date(hoje.year, hoje.month, 1)
    else:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        
    if not data_fim_str:
        if hoje.month == 12:
            proximo_mes = date(hoje.year + 1, 1, 1)
        else:
            proximo_mes = date(hoje.year, hoje.month + 1, 1)
        data_fim = proximo_mes - timedelta(days=1)
    else:
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
    
    # Métricas Filtradas por Data
    
    # Total de Reservas no período (Apenas Confirmadas/Realizadas)
    reservas_periodo_query = Reserva.query.join(Recurso).filter(
        Recurso.escola_id == id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim
    )
    
    # Total Geral (inclui canceladas)
    total_geral = reservas_periodo_query.count()
    
    # Total Não Concretizadas
    total_nao_realizadas = reservas_periodo_query.filter(Reserva.status == 'nao_realizada').count()
    
    # Total Válidas (exclui canceladas/não realizadas)
    total_reservas = reservas_periodo_query.filter(
        Reserva.status.notin_(['cancelada', 'nao_realizada'])
    ).count()

    # Reservas por Status
    reservas_por_status = db.session.query(
        Reserva.status, func.count(Reserva.id)
    ).join(Recurso).filter(
        Recurso.escola_id == id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim
    ).group_by(Reserva.status).all()
    
    # Recursos - Distribuição (Solicitados vs Concretizados + Possibilidade + % Agendamento)
    recursos = Recurso.query.filter_by(escola_id=id).all()
    
    # Calcular total de slots disponíveis por recurso no período
    blocos = BlocoAula.query.filter_by(escola_id=id).all()
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
        # Total Solicitado
        total_solicitado = Reserva.query.filter(
            Reserva.recurso_id == recurso.id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim
        ).count()
        
        # Concretizadas (confirmadas)
        concretizadas = Reserva.query.filter(
            Reserva.recurso_id == recurso.id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim,
            Reserva.status == 'confirmada'
        ).count()
        
        # Aproveitamento
        aproveitamento = round((concretizadas / total_solicitado * 100), 1) if total_solicitado > 0 else 0
        
        # Possibilidade de agendamento
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
        ).group_by(Usuario.nome).order_by(func.count(Reserva.id).desc()).limit(5).all()
        
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
        ).group_by(Turma.nome).order_by(func.count(Reserva.id).desc()).limit(5).all()
        
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
    
    # Ordenar por total solicitado (decrescente)
    metricas_recursos.sort(key=lambda r: r['total_solicitado'], reverse=True)

    # Capacidade por recurso (total_slots_periodo dividido pela quantidade de recursos)
    num_recursos = len(recursos)
    capacidade_por_recurso = round(total_slots_periodo / num_recursos, 1) if num_recursos > 0 else 0
    
    # Construir lookup de possibilidade_agendamento por nome do recurso
    possibilidade_por_recurso = {}
    for r in metricas_recursos:
        possibilidade_por_recurso[r['nome']] = r['possibilidade_agendamento']
    
    # Professores Mais Ativos (com detalhamento por recurso)
    professores_top = db.session.query(
        Usuario.nome, func.count(Reserva.id).label('total')
    ).join(Reserva).join(Recurso).filter(
        Recurso.escola_id == id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim,
        Usuario.papel == 'professor',
        Reserva.status.notin_(['cancelada', 'nao_realizada'])
    ).group_by(Usuario.id).order_by(func.count(Reserva.id).desc()).limit(5).all()
    
    # Calcular % de cada professor em relação ao total de reservas válidas
    professores_top_com_pct = []
    for nome, total in professores_top:
        pct = round((total / total_reservas * 100), 1) if total_reservas > 0 else 0
        # Reservas por recurso para este professor
        prof_recursos = Reserva.query.join(Recurso).join(Usuario).filter(
            Usuario.nome == nome,
            Recurso.escola_id == id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim,
            Reserva.status.notin_(['cancelada', 'nao_realizada'])
        ).with_entities(
            Recurso.nome, func.count(Reserva.id)
        ).group_by(Recurso.nome).order_by(func.count(Reserva.id).desc()).all()
        
        prof_recursos_pct = []
        for rec_nome, rec_total in prof_recursos:
            possib = possibilidade_por_recurso.get(rec_nome, 0)
            rec_pct = round((rec_total / possib * 100), 1) if possib > 0 else 0
            prof_recursos_pct.append({'nome': rec_nome, 'total': rec_total, 'pct': rec_pct})
        
        professores_top_com_pct.append({
            'nome': nome,
            'total': total,
            'pct': pct,
            'recursos': prof_recursos_pct
        })
    
    # Disciplinas/Temáticas Mais Solicitadas (Apenas Confirmadas)
    disciplinas_stats = db.session.query(
        Disciplina.nome, func.count(Reserva.id).label('total')
    ).join(Reserva).join(Recurso).filter(
        Recurso.escola_id == id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim,
        Reserva.disciplina_id != None,
        Reserva.status.notin_(['cancelada', 'nao_realizada'])
    ).group_by(Disciplina.id).order_by(func.count(Reserva.id).desc()).limit(5).all()
    
    # Calcular % de cada disciplina em relação ao total de reservas válidas
    disciplinas_stats_com_pct = []
    for nome, total in disciplinas_stats:
        pct = round((total / total_reservas * 100), 1) if total_reservas > 0 else 0
        disciplinas_stats_com_pct.append((nome, total, pct))
    
    # Top Turmas (com detalhamento por recurso)
    top_turmas = db.session.query(
        Turma.nome, func.count(Reserva.id).label('total')
    ).join(Reserva).join(Recurso).filter(
        Recurso.escola_id == id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim,
        Reserva.turma_id != None,
        Reserva.status.notin_(['cancelada', 'nao_realizada'])
    ).group_by(Turma.id).order_by(func.count(Reserva.id).desc()).limit(5).all()
    
    top_turmas_com_pct = []
    for nome, total in top_turmas:
        pct = round((total / total_reservas * 100), 1) if total_reservas > 0 else 0
        # Reservas por recurso para esta turma
        turma_recursos = Reserva.query.join(Recurso).join(Turma).filter(
            Turma.nome == nome,
            Recurso.escola_id == id,
            Reserva.data >= data_inicio,
            Reserva.data <= data_fim,
            Reserva.status.notin_(['cancelada', 'nao_realizada'])
        ).with_entities(
            Recurso.nome, func.count(Reserva.id)
        ).group_by(Recurso.nome).order_by(func.count(Reserva.id).desc()).all()
        
        turma_recursos_pct = []
        for rec_nome, rec_total in turma_recursos:
            possib = possibilidade_por_recurso.get(rec_nome, 0)
            rec_pct = round((rec_total / possib * 100), 1) if possib > 0 else 0
            
            # Professores que usaram este recurso para esta turma
            profs_no_recurso = Reserva.query.join(Usuario).join(Recurso).join(Turma).filter(
                Turma.nome == nome,
                Recurso.nome == rec_nome,
                Recurso.escola_id == id,
                Reserva.data >= data_inicio,
                Reserva.data <= data_fim,
                Reserva.status.notin_(['cancelada', 'nao_realizada'])
            ).with_entities(
                Usuario.nome, func.count(Reserva.id)
            ).group_by(Usuario.nome).order_by(func.count(Reserva.id).desc()).all()
            
            profs_list = []
            for p_nome, p_total in profs_no_recurso:
                p_pct = round((p_total / possib * 100), 1) if possib > 0 else 0
                profs_list.append({'nome': p_nome, 'total': p_total, 'pct': p_pct})
            
            # Disciplinas usadas neste recurso para esta turma
            discs_no_recurso = Reserva.query.join(Disciplina).join(Recurso).join(Turma).filter(
                Turma.nome == nome,
                Recurso.nome == rec_nome,
                Recurso.escola_id == id,
                Reserva.data >= data_inicio,
                Reserva.data <= data_fim,
                Reserva.status.notin_(['cancelada', 'nao_realizada']),
                Reserva.disciplina_id != None
            ).with_entities(
                Disciplina.nome, func.count(Reserva.id)
            ).group_by(Disciplina.nome).order_by(func.count(Reserva.id).desc()).all()
            
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

    return render_template('gestor_regional/relatorio_escola.html',
                           escola=escola,
                           data_inicio=data_inicio,
                           data_fim=data_fim,
                           total_reservas=total_reservas,
                           total_geral=total_geral,
                           total_nao_realizadas=total_nao_realizadas,
                           reservas_por_status=reservas_por_status,
                           metricas_recursos=metricas_recursos,
                           capacidade_por_recurso=capacidade_por_recurso,
                           professores_top=professores_top_com_pct,
                           disciplinas_stats=disciplinas_stats_com_pct,
                           top_turmas=top_turmas_com_pct,
                           usuario=current_user)

@gestor_regional.route('/relatorio_escola/<int:id>/pdf')
@login_required
@papel_requerido('gestor_regional')
def relatorio_escola_pdf(id):
    escola = Escola.query.filter_by(id=id, regiao_id=current_user.regiao_id).first_or_404()
    
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')

    hoje = date.today()
    if not data_inicio_str:
        data_inicio = date(hoje.year, hoje.month, 1)
    else:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        
    if not data_fim_str:
        if hoje.month == 12:
            proximo_mes = date(hoje.year + 1, 1, 1)
        else:
            proximo_mes = date(hoje.year, hoje.month + 1, 1)
        data_fim = proximo_mes - timedelta(days=1)
    else:
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
    
    reservas_periodo_query = Reserva.query.join(Recurso).filter(
        Recurso.escola_id == id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim
    )
    
    total_geral = reservas_periodo_query.count()
    total_nao_realizadas = reservas_periodo_query.filter(Reserva.status == 'nao_realizada').count()
    total_reservas = reservas_periodo_query.filter(
        Reserva.status.notin_(['cancelada', 'nao_realizada'])
    ).count()

    reservas_por_status = db.session.query(
        Reserva.status, func.count(Reserva.id)
    ).join(Recurso).filter(
        Recurso.escola_id == id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim
    ).group_by(Reserva.status).all()
    
    recursos = Recurso.query.filter_by(escola_id=id).all()
    blocos = BlocoAula.query.filter_by(escola_id=id).all()
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
    
    metricas_recursos.sort(key=lambda r: r['total_solicitado'], reverse=True)

    num_recursos = len(recursos)
    capacidade_por_recurso = round(total_slots_periodo / num_recursos, 1) if num_recursos > 0 else 0

    professores_top = db.session.query(
        Usuario.nome, func.count(Reserva.id).label('total')
    ).join(Reserva).join(Recurso).filter(
        Recurso.escola_id == id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim,
        Usuario.papel == 'professor',
        Reserva.status.notin_(['cancelada', 'nao_realizada'])
    ).group_by(Usuario.id).order_by(func.count(Reserva.id).desc()).limit(10).all()

    professores_top_com_pct = []
    for nome, total in professores_top:
        pct = round((total / total_reservas * 100), 1) if total_reservas > 0 else 0
        professores_top_com_pct.append({'nome': nome, 'total': total, 'pct': pct})

    disciplinas_stats = db.session.query(
        Disciplina.nome, func.count(Reserva.id).label('total')
    ).join(Reserva).join(Recurso).filter(
        Recurso.escola_id == id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim,
        Reserva.disciplina_id != None,
        Reserva.status.notin_(['cancelada', 'nao_realizada'])
    ).group_by(Disciplina.id).order_by(func.count(Reserva.id).desc()).limit(10).all()

    disciplinas_stats_com_pct = []
    for nome, total in disciplinas_stats:
        pct = round((total / total_reservas * 100), 1) if total_reservas > 0 else 0
        disciplinas_stats_com_pct.append((nome, total, pct))

    top_turmas = db.session.query(
        Turma.nome, func.count(Reserva.id).label('total')
    ).join(Reserva).join(Recurso).filter(
        Recurso.escola_id == id,
        Reserva.data >= data_inicio,
        Reserva.data <= data_fim,
        Reserva.turma_id != None,
        Reserva.status.notin_(['cancelada', 'nao_realizada'])
    ).group_by(Turma.id).order_by(func.count(Reserva.id).desc()).limit(10).all()

    top_turmas_com_pct = []
    for nome, total in top_turmas:
        pct = round((total / total_reservas * 100), 1) if total_reservas > 0 else 0
        top_turmas_com_pct.append({'nome': nome, 'total': total, 'pct': pct})

    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 16)
    pdf.multi_cell(0, 8, f"Relatorio de Metricas - {escola.nome}")
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f"Periodo: {data_inicio.strftime('%d/%m/%Y')} ate {data_fim.strftime('%d/%m/%Y')}", ln=True)
    pdf.cell(0, 6, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True)
    pdf.ln(2)

    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 7, "Resumo", ln=True)
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f"Total (geral): {total_geral}", ln=True)
    pdf.cell(0, 6, f"Total (validas): {total_reservas}", ln=True)
    pdf.cell(0, 6, f"Total nao concretizadas: {total_nao_realizadas}", ln=True)
    pdf.cell(0, 6, f"Capacidade por recurso: {capacidade_por_recurso}", ln=True)
    pdf.ln(2)

    if reservas_por_status:
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(0, 7, "Reservas por status", ln=True)
        pdf.set_font('Helvetica', '', 10)
        for status, count in reservas_por_status:
            pdf.cell(0, 6, f"- {status}: {count}", ln=True)
        pdf.ln(2)

    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 7, "Metricas por recurso", ln=True)
    pdf.set_font('Helvetica', '', 9)
    if metricas_recursos:
        for r in metricas_recursos:
            pdf.multi_cell(
                0,
                5,
                f"- {r['nome']} | Solicitado: {r['total_solicitado']} | Concretizadas: {r['concretizadas']} | Aproveitamento: {r['aproveitamento']}% | Possib.: {r['possibilidade_agendamento']} | % Agend.: {r['pct_agendamento']}%"
            )
    else:
        pdf.cell(0, 6, "Sem dados no periodo.", ln=True)
    pdf.ln(2)

    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 7, "Professores mais ativos", ln=True)
    pdf.set_font('Helvetica', '', 9)
    if professores_top_com_pct:
        for p in professores_top_com_pct:
            pdf.multi_cell(0, 5, f"- {p['nome']} | Total: {p['total']} | % Geral: {p['pct']}%")
    else:
        pdf.cell(0, 6, "Sem dados no periodo.", ln=True)
    pdf.ln(2)

    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 7, "Turmas com mais reservas", ln=True)
    pdf.set_font('Helvetica', '', 9)
    if top_turmas_com_pct:
        for t in top_turmas_com_pct:
            pdf.multi_cell(0, 5, f"- {t['nome']} | Reservas: {t['total']} | %: {t['pct']}%")
    else:
        pdf.cell(0, 6, "Sem dados no periodo.", ln=True)
    pdf.ln(2)

    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 7, "Disciplinas com mais reservas", ln=True)
    pdf.set_font('Helvetica', '', 9)
    if disciplinas_stats_com_pct:
        for nome, total, pct in disciplinas_stats_com_pct:
            pdf.multi_cell(0, 5, f"- {nome} | Reservas: {total} | %: {pct}%")
    else:
        pdf.cell(0, 6, "Sem dados no periodo.", ln=True)

    safe_name = ''.join([c if c.isalnum() or c in ('_', '-') else '_' for c in escola.nome.replace(' ', '_')])
    filename = f"relatorio_{safe_name}.pdf"
    content = pdf.output(dest='S').encode('latin1', errors='replace')
    return send_file(BytesIO(content), mimetype='application/pdf', as_attachment=True, download_name=filename)


