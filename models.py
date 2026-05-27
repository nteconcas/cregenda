# models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(200), nullable=False)
    papel = db.Column(db.String(20), nullable=False)
    telefone = db.Column(db.String(20), nullable=True)
    ativo = db.Column(db.Boolean, default=True)

    regiao_id = db.Column(db.Integer, db.ForeignKey('regioes.id'), nullable=True)
    escola_id = db.Column(db.Integer, db.ForeignKey('escolas.id'), nullable=True)
    
    # Relacionamentos
    regiao = db.relationship('Regiao', backref='usuarios')
    escola = db.relationship('Escola', backref='usuarios')
    
    disciplinas = db.relationship('Disciplina', secondary='professor_disciplina', backref=db.backref('professores', lazy='dynamic'))
    turmas = db.relationship('Turma', secondary='professor_turma', backref=db.backref('professores', lazy='dynamic'))

    @property
    def is_active(self):
        return self.ativo

class Regiao(db.Model):
    __tablename__ = 'regioes'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)

class Escola(db.Model):
    __tablename__ = 'escolas'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    regiao_id = db.Column(db.Integer, db.ForeignKey('regioes.id'), nullable=False)
    
    regiao = db.relationship('Regiao', backref='escolas')

class Disciplina(db.Model):
    __tablename__ = 'disciplinas'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    escola_id = db.Column(db.Integer, db.ForeignKey('escolas.id'), nullable=False)

# Tabela de Associação Professor <-> Disciplina
professor_disciplina = db.Table('professor_disciplina',
    db.Column('professor_id', db.Integer, db.ForeignKey('usuarios.id'), primary_key=True),
    db.Column('disciplina_id', db.Integer, db.ForeignKey('disciplinas.id'), primary_key=True)
)

class Turma(db.Model):
    __tablename__ = 'turmas'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)  # ex: "6ºA"
    turno = db.Column(db.String(20), nullable=False)  # 'Matutino', 'Vespertino', 'Noturno'
    escola_id = db.Column(db.Integer, db.ForeignKey('escolas.id'), nullable=False)

# Tabela de Associação Professor <-> Turma
professor_turma = db.Table('professor_turma',
    db.Column('professor_id', db.Integer, db.ForeignKey('usuarios.id'), primary_key=True),
    db.Column('turma_id', db.Integer, db.ForeignKey('turmas.id'), primary_key=True)
)

class Recurso(db.Model):
    __tablename__ = 'recursos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    escola_id = db.Column(db.Integer, db.ForeignKey('escolas.id'), nullable=False)

class BlocoAula(db.Model):
    __tablename__ = 'blocos_aula'
    id = db.Column(db.Integer, primary_key=True)
    dia_semana = db.Column(db.Integer, nullable=False)  # 0=Segunda, 6=Domingo
    periodo = db.Column(db.String(50), nullable=False)  # ex: "Matutino - Aula 1"
    escola_id = db.Column(db.Integer, db.ForeignKey('escolas.id'), nullable=False)

class Reserva(db.Model):
    __tablename__ = 'reservas'
    id = db.Column(db.Integer, primary_key=True)
    recurso_id = db.Column(db.Integer, db.ForeignKey('recursos.id'), nullable=False)
    professor_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    turma_id = db.Column(db.Integer, db.ForeignKey('turmas.id'), nullable=True)
    bloco_aula_id = db.Column(db.Integer, db.ForeignKey('blocos_aula.id'), nullable=False)
    disciplina_id = db.Column(db.Integer, db.ForeignKey('disciplinas.id'), nullable=True)
    data = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='confirmada')
    descricao_pedagogica = db.Column(db.String(255), nullable=True) # Torne obrigatório via código, nullable=True para migração
    motivo_nao_realizacao = db.Column(db.String(255), nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    recurso = db.relationship('Recurso', backref='reservas')
    professor = db.relationship('Usuario', backref='reservas')
    turma = db.relationship('Turma', backref='reservas')
    bloco = db.relationship('BlocoAula', backref='reservas')
    disciplina = db.relationship('Disciplina', backref='reservas')

class Bloqueio(db.Model):
    __tablename__ = 'bloqueios'
    id = db.Column(db.Integer, primary_key=True)
    recurso_id = db.Column(db.Integer, db.ForeignKey('recursos.id'), nullable=False)
    bloco_aula_id = db.Column(db.Integer, db.ForeignKey('blocos_aula.id'), nullable=True)
    data = db.Column(db.Date, nullable=True)
    tipo = db.Column(db.String(20), nullable=False)  # 'dia_completo' ou 'bloco_especifico'
    justificativa = db.Column(db.String(200), nullable=False)
    escola_id = db.Column(db.Integer, db.ForeignKey('escolas.id'), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacionamentos
    recurso = db.relationship('Recurso', backref='bloqueios')
    bloco = db.relationship('BlocoAula', backref='bloqueios')

class Vinculo(db.Model):
    __tablename__ = 'vinculos'
    id = db.Column(db.Integer, primary_key=True)
    professor_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    escola_id = db.Column(db.Integer, db.ForeignKey('escolas.id'), nullable=False)
    status = db.Column(db.String(20), default='pendente') # pendente, aprovado, recusado
    data_solicitacao = db.Column(db.DateTime, default=datetime.utcnow)

    professor = db.relationship('Usuario', backref='vinculos')
    escola = db.relationship('Escola', backref='vinculos')