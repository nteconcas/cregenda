from app import create_app, db
from models import Usuario, Turma, Disciplina
import sys

app = create_app()
with app.app_context():
    try:
        print("Testing database connection...")
        # Get first professor
        professor = Usuario.query.filter_by(papel='professor').first()
        if not professor:
            print("No professor found.")
            sys.exit(0)
            
        print(f"Professor found: {professor.nome}")
        
        # Access turmas (trigger relationship)
        print("Accessing turmas...")
        turmas = professor.turmas
        print(f"Turmas count: {len(turmas)}")
        
        # Access disciplinas
        print("Accessing disciplinas...")
        disciplinas = professor.disciplinas
        print(f"Disciplinas count: {len(disciplinas)}")
        
        print("✅ Relationships are working correctly.")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
