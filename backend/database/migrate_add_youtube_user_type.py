"""
Migración: Agregar campo user_type a youtube_profile
Categoriza el tipo de usuario: owner, moderator, member, regular
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "powerbot.db"


def migrate():
    """Agrega el campo user_type a youtube_profile si no existe."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    try:
        # Verificar si la columna ya existe
        cursor.execute("PRAGMA table_info(youtube_profile)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "user_type" not in columns:
            print("✅ Agregando columna 'user_type' a youtube_profile...")
            cursor.execute("""
                ALTER TABLE youtube_profile 
                ADD COLUMN user_type TEXT DEFAULT 'regular'
            """)
            conn.commit()
            print("✅ Migración completada: user_type agregado")
        else:
            print("ℹ️  Columna 'user_type' ya existe")
            
    except sqlite3.OperationalError as e:
        print(f"❌ Error en migración: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
