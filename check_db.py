import os
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv

load_dotenv()

db_url = os.environ.get('DATABASE_URL')
print(f"Connecting to: {db_url}")

try:
    engine = create_engine(db_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print("Tables in database:")
    for table in tables:
        print(f"- {table}")
        
    if 'professor_turma' in tables:
        print("\n✅ Table 'professor_turma' exists.")
        columns = inspector.get_columns('professor_turma')
        for col in columns:
            print(f"  - {col['name']} ({col['type']})")
    else:
        print("\n❌ Table 'professor_turma' DOES NOT exist.")
        
except Exception as e:
    print(f"\nError: {e}")
