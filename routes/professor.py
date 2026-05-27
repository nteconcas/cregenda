from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from models import db, Reserva, Recurso, BlocoAula, Turma, Bloqueio, Escola, Vinculo
from datetime import datetime, date, timedelta
from sqlalchemy.orm import joinedload

professor = Blueprint('professor', __name__)

def get_escolas_professor(user):
    escolas = []
    # Home school
    if user.escola_id:
        home = Escola.query.get(user.escola_id)
        if home:
            escolas.append(home)
    # Linked schools
    for v in user.vinculos:
        if v.status == 'aprovado':
            escolas.append(v.escola)
    # Remove duplicates and return sorted by name
    unique_escolas = list({e.id: e for e in escolas}.values())
    unique_escolas.sort(key=lambda x: x.nome)
    return unique_escolas

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

@professor.route('/dashboard')
@login_required
@papel_requerido('professor')
def dashboard():
    return render_template('professor/dashboard.html', usuario=current_user)

@professor.route('/minhas_reservas')
@login_required
@papel_requerido('professor')
def minhas_reservas():
    # Parâmetro opcional de data para filtro
    data_str = request.args.get('data')
    
    # Se não houver data, usa a data de hoje
    if data_str:
        try:
            data_filtro = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data_filtro = date.today()
    else:
        data_filtro = date.today()
    
    # Escolas do professor
    escolas = get_escolas_professor(current_user)
    escola_id = request.args.get('escola_id', type=int)
    
    if not escola_id and escolas:
        escola_id = escolas[0].id
    
    # Sempre filtra pela data selecionada (vinculada à navegação)
    query = Reserva.query.options(joinedload(Reserva.disciplina), joinedload(Reserva.turma), joinedload(Reserva.recurso)).join(Recurso).filter(
        Reserva.professor_id == current_user.id, 
        Reserva.data == data_filtro
    )
    
    if escola_id:
        query = query.filter(Recurso.escola_id == escola_id)
            
    reservas = query.order_by(Reserva.bloco_aula_id).all()
    
    # Lógica de navegação
    base_date = data_filtro
    data_anterior = base_date - timedelta(days=1)
    data_proxima = base_date + timedelta(days=1)
    
    return render_template('professor/reservas.html', 
                           usuario=current_user, 
                           reservas=reservas,
                           data_filtro=data_filtro,
                           data_anterior=data_anterior,
                           data_proxima=data_proxima,
                           today_date=date.today(),
                           escolas=escolas,
                           escola_selecionada_id=escola_id)

@professor.route('/nova_reserva', methods=['GET', 'POST'])
@login_required
@papel_requerido('professor')
def nova_reserva():
    # 1. Processar a data selecionada (ou usar hoje como padrão)
    data_str = request.args.get('data')
    if data_str:
        try:
            data_selecionada = datetime.strptime(data_str, '%Y-%m-%d').date()
        except ValueError:
            data_selecionada = date.today()
    else:
        data_selecionada = date.today()

    # Escolas do professor
    escolas = get_escolas_professor(current_user)
    # Tenta pegar escola_id do args (GET) ou form (POST)
    escola_id = request.values.get('escola_id', type=int)
    
    if not escola_id and escolas:
        escola_id = escolas[0].id
        
    # Validar se o professor tem acesso a essa escola
    if escola_id and escola_id not in [e.id for e in escolas]:
        flash('Você não tem acesso a esta escola.', 'error')
        return redirect(url_for('professor.dashboard'))

    # Se for POST, processar a reserva
    if request.method == 'POST':
        # Verificar se é uma reserva em lote (JSON ou múltiplos campos)
        # O formulário pode enviar listas, mas como estamos usando AJAX/JS para selecionar múltiplos,
        # vamos usar um campo hidden 'itens_reserva' que contém JSON string, ou simplesmente iterar sobre os dados.
        # Vamos assumir que a UI enviará um JSON string no campo 'itens_reserva'
        
        import json
        itens_reserva_str = request.form.get('itens_reserva')
        turma_id = request.form.get('turma_id')
        data_reserva_str = request.form.get('data_reserva')
        descricao_pedagogica = request.form.get('descricao_pedagogica')
        disciplina_id_form = request.form.get('disciplina_id_select') # Pega do formulário
        
        # Validação de campos obrigatórios
        campos_obrigatorios = [itens_reserva_str, turma_id, data_reserva_str, descricao_pedagogica]
        if not all(campos_obrigatorios):
             flash('Preencha todos os campos obrigatórios (Itens, Turma, Data, Descrição).', 'error')
             return redirect(url_for('professor.nova_reserva', data=data_reserva_str, escola_id=escola_id))

        try:
            itens_reserva = json.loads(itens_reserva_str)
        except:
            flash('Erro ao processar itens da reserva.', 'error')
            return redirect(url_for('professor.nova_reserva', data=data_reserva_str, escola_id=escola_id))

        data_reserva = datetime.strptime(data_reserva_str, '%Y-%m-%d').date()

        if data_reserva < date.today():
            flash('Não é possível reservar datas passadas.', 'error')
            return redirect(url_for('professor.nova_reserva', data=data_reserva_str, escola_id=escola_id))
            
        # Validar e Criar Reservas (Transação Atômica)
        reservas_criadas = []
        try:
            # 1. Validar limite de aulas consecutivas (máximo 2)
            # Buscar todos os blocos do dia para estabelecer a ordem
            dia_semana = data_reserva.weekday()
            todos_blocos = BlocoAula.query.filter_by(
                escola_id=escola_id,
                dia_semana=dia_semana
            ).order_by(BlocoAula.periodo).all()
            
            # Mapa: bloco_id -> indice (ordem)
            bloco_indices = {b.id: i for i, b in enumerate(todos_blocos)}
            
            # Buscar reservas JÁ existentes para este professor + turma + data
            reservas_existentes_turma = Reserva.query.filter_by(
                professor_id=current_user.id,
                turma_id=turma_id,
                data=data_reserva,
                status='confirmada'
            ).all()
            
            # Conjunto de índices de blocos ocupados (existentes + novos)
            indices_ocupados = {bloco_indices[r.bloco_aula_id] for r in reservas_existentes_turma if r.bloco_aula_id in bloco_indices}
            
            # Adicionar os novos blocos solicitados
            for item in itens_reserva:
                bid = int(item.get('bloco_id'))
                if bid in bloco_indices:
                    indices_ocupados.add(bloco_indices[bid])
            
            # Verificar consecutividade
            if indices_ocupados:
                sorted_indices = sorted(list(indices_ocupados))
                max_consecutivos = 1
                current_consecutivos = 1
                
                for i in range(1, len(sorted_indices)):
                    if sorted_indices[i] == sorted_indices[i-1] + 1:
                        current_consecutivos += 1
                    else:
                        current_consecutivos = 1
                    max_consecutivos = max(max_consecutivos, current_consecutivos)
                
                if max_consecutivos > 2:
                    raise Exception("Permitido reservar no máximo 2 aulas consecutivas para a mesma turma.")

            for item in itens_reserva:
                recurso_id = item.get('recurso_id')
                bloco_id = item.get('bloco_id')
                
                # Verificar conflito
                conflito = Reserva.query.filter_by(
                    recurso_id=recurso_id,
                    data=data_reserva,
                    bloco_aula_id=bloco_id,
                    status='confirmada'
                ).first()

                if conflito:
                    raise Exception(f"Conflito de horário detectado para um dos itens.")

                # Verificar bloqueio
                bloqueio = Bloqueio.query.filter(
                    Bloqueio.escola_id == escola_id,
                    Bloqueio.data == data_reserva,
                    Bloqueio.recurso_id == recurso_id,
                    ((Bloqueio.tipo == 'dia_completo') | 
                     ((Bloqueio.tipo == 'bloco_especifico') & (Bloqueio.bloco_aula_id == bloco_id)))
                ).first()

                if bloqueio:
                    raise Exception(f"Um dos horários selecionados está bloqueado pelo gestor.")
                
                disciplina_id = item.get('disciplina_id')
                if not disciplina_id and disciplina_id_form:
                    disciplina_id = int(disciplina_id_form)

                nova_reserva = Reserva(
                    recurso_id=recurso_id,
                    professor_id=current_user.id,
                    turma_id=turma_id,
                    bloco_aula_id=bloco_id,
                    data=data_reserva,
                    status='confirmada',
                    descricao_pedagogica=descricao_pedagogica,
                    disciplina_id=disciplina_id
                )
                db.session.add(nova_reserva)
                reservas_criadas.append(nova_reserva)
            
            db.session.commit()
            flash(f'{len(reservas_criadas)} reserva(s) realizada(s) com sucesso!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(str(e), 'error')
            
        return redirect(url_for('professor.nova_reserva', data=data_reserva_str, escola_id=escola_id))

    # GET: Preparar dados para a Grid
    recursos = Recurso.query.filter_by(escola_id=escola_id).all()
    
    # Filtrar turmas atribuídas ao professor nesta escola
    turmas_atribuidas = [t for t in current_user.turmas if t.escola_id == escola_id]
    if turmas_atribuidas:
        turmas = turmas_atribuidas
    else:
        turmas = Turma.query.filter_by(escola_id=escola_id).all()
    
    # Buscar blocos do dia da semana correspondente
    dia_semana = data_selecionada.weekday()
    blocos = BlocoAula.query.filter_by(
        escola_id=escola_id,
        dia_semana=dia_semana
    ).order_by(BlocoAula.periodo).all()

    # Buscar reservas já existentes para esta data
    reservas_existentes = Reserva.query.filter_by(
        data=data_selecionada,
        status='confirmada'
    ).all()

    # Buscar bloqueios
    bloqueios = Bloqueio.query.filter_by(
        escola_id=escola_id,
        data=data_selecionada
    ).all()

    # Mapear disponibilidade: availability[bloco_id][recurso_id] = dict info
    availability = {}
    
    # Inicializar com status 'livre'
    for bloco in blocos:
        availability[bloco.id] = {}
        for recurso in recursos:
            availability[bloco.id][recurso.id] = {'status': 'livre', 'obj': None}

    # Preencher com as reservas
    for r in reservas_existentes:
        if r.bloco_aula_id in availability and r.recurso_id in availability[r.bloco_aula_id]:
            availability[r.bloco_aula_id][r.recurso_id] = {
                'status': 'reservado',
                'obj': r,
                'is_mine': (r.professor_id == current_user.id)
            }
            
    # Preencher com bloqueios
    for b in bloqueios:
        if b.tipo == 'dia_completo':
             for bl_id in availability:
                 if b.recurso_id in availability[bl_id]:
                     availability[bl_id][b.recurso_id] = {
                         'status': 'bloqueado',
                         'obj': b
                     }
        elif b.tipo == 'bloco_especifico':
             if b.bloco_aula_id in availability and b.recurso_id in availability[b.bloco_aula_id]:
                 availability[b.bloco_aula_id][b.recurso_id] = {
                     'status': 'bloqueado',
                     'obj': b
                 }
            
    # Agrupar blocos por turno (extraindo do nome do bloco, ex: "Matutino - Aula 1")
    # Assumindo que o nome do bloco começa com o turno (implementado em configurar_grade)
    blocos_por_turno = {}
    turnos_ordem = ['Matutino', 'Vespertino', 'Noturno'] # Ordem de exibição
    
    for bloco in blocos:
        # Tenta extrair o turno da string "Turno - Periodo"
        parts = bloco.periodo.split(' - ')
        turno_nome = parts[0] if len(parts) > 0 else 'Outros'
        
        if turno_nome not in blocos_por_turno:
            blocos_por_turno[turno_nome] = []
        blocos_por_turno[turno_nome].append(bloco)

    # Reordenar dicionário baseado na ordem padrão
    blocos_por_turno_ordenados = {}
    for t in turnos_ordem:
        if t in blocos_por_turno:
            blocos_por_turno_ordenados[t] = blocos_por_turno[t]
    
    # Adicionar turnos que não estão na lista padrão (caso existam)
    for t in blocos_por_turno:
        if t not in turnos_ordem:
            blocos_por_turno_ordenados[t] = blocos_por_turno[t]

    # Lista ordenada de IDs de blocos para validação no frontend
    blocos_ids_ordenados = [b.id for b in blocos]

    # Calcular datas anterior e próxima
    data_anterior = data_selecionada - timedelta(days=1)
    data_proxima = data_selecionada + timedelta(days=1)
    # Se anterior for menor que hoje, não permitir (opcional, mas bom UX)
    # Na verdade, professor pode querer ver o que passou, mas não reservar. 
    # A validação de reserva futura já existe no POST.

    return render_template('professor/nova_reserva.html',
                           usuario=current_user,
                           data_selecionada=data_selecionada,
                           data_anterior=data_anterior,
                           data_proxima=data_proxima,
                           recursos=recursos,
                           turmas=turmas,
                           availability=availability,
                           blocos_por_turno=blocos_por_turno_ordenados,
                           blocos_ids_ordenados=blocos_ids_ordenados,
                           escolas=escolas,
                           escola_selecionada_id=escola_id)

@professor.route('/cancelar_reserva/<int:id>', methods=['POST'])
@login_required
@papel_requerido('professor')
def cancelar_reserva(id):
    reserva = Reserva.query.filter_by(id=id, professor_id=current_user.id).first_or_404()
    # Remove a reserva permanentemente para liberar o horário
    db.session.delete(reserva)
    db.session.commit()
    flash('Reserva cancelada com sucesso.', 'success')
    return redirect(url_for('professor.minhas_reservas'))

@professor.route('/solicitar_vinculo', methods=['GET', 'POST'])
@login_required
@papel_requerido('professor')
def solicitar_vinculo():
    if request.method == 'POST':
        escola_id = request.form.get('escola_id')
        if not escola_id:
            flash('Selecione uma escola.', 'error')
            return redirect(url_for('professor.solicitar_vinculo'))
            
        # Verificar se já existe vínculo ou solicitação
        # Check home school
        if current_user.escola_id and current_user.escola_id == int(escola_id):
             flash('Você já pertence a esta escola.', 'warning')
             return redirect(url_for('professor.solicitar_vinculo'))
             
        v = Vinculo.query.filter_by(professor_id=current_user.id, escola_id=escola_id).first()
        if v:
            flash('Já existe uma solicitação ou vínculo para esta escola.', 'warning')
        else:
            v = Vinculo(professor_id=current_user.id, escola_id=escola_id, status='pendente')
            db.session.add(v)
            db.session.commit()
            flash('Solicitação enviada com sucesso! Aguarde a aprovação do gestor.', 'success')
            
        return redirect(url_for('professor.solicitar_vinculo'))
        
    # GET
    # Escolas disponíveis (não home, não vinculadas)
    exclude_ids = set()
    if current_user.escola_id:
        exclude_ids.add(current_user.escola_id)
        
    for v in current_user.vinculos:
        exclude_ids.add(v.escola_id)
        
    if exclude_ids:
        escolas_disponiveis = Escola.query.filter(Escola.id.notin_(exclude_ids)).order_by(Escola.nome).all()
    else:
        escolas_disponiveis = Escola.query.order_by(Escola.nome).all()
    
    # Minhas solicitações (pendentes, aprovadas, recusadas)
    solicitacoes = Vinculo.query.filter_by(professor_id=current_user.id).order_by(Vinculo.data_solicitacao.desc()).all()
    
    return render_template('professor/solicitar_vinculo.html', 
                           escolas=escolas_disponiveis, 
                           solicitacoes=solicitacoes,
                           usuario=current_user)
