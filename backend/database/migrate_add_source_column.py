"""
Migración: Agregar columna 'source' a la tabla items
"""
import sys
sys.path.insert(0, 'c:\\Users\\jhon-\\Desktop\\PowerBot')

from backend.database import get_connection


def migrate():
    print("🔄 Migrando base de datos...")
    
    conn = get_connection()
    try:
        # Verificar si la columna ya existe
        cursor = conn.execute("PRAGMA table_info(items)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "source" in columns:
            print("✅ La columna 'source' ya existe")
            return
        
        print("📝 Agregando columna 'source' a tabla items...")
        
        # SQLite no permite agregar columnas con NOT NULL y sin default
        # Tenemos que recrear la tabla
        
        # 1. Crear tabla temporal con nueva estructura
        conn.execute(
            """
            CREATE TABLE items_new (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_key TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL DEFAULT 'gacha',
                nombre TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                rareza TEXT NOT NULL,
                imagen_local TEXT,
                ataque INTEGER DEFAULT 0,
                defensa INTEGER DEFAULT 0,
                vida INTEGER DEFAULT 0,
                armadura INTEGER DEFAULT 0,
                mantenimiento INTEGER DEFAULT 0,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        
        # 2. Verificar si hay datos en la tabla vieja
        has_data = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] > 0
        
        if has_data:
            print("📋 Migrando datos existentes...")
            # Copiar datos (necesitamos crear item_key si no existe)
            conn.execute(
                """
                INSERT INTO items_new 
                    (item_id, item_key, source, nombre, descripcion, rareza, 
                     imagen_local, ataque, defensa, vida, armadura, mantenimiento, 
                     metadata, created_at, updated_at)
                SELECT 
                    item_id,
                    'item_' || CAST(item_id AS TEXT) as item_key,
                    'gacha' as source,
                    nombre, descripcion, rareza,
                    NULL as imagen_local,
                    ataque, defensa, vida, armadura, mantenimiento,
                    NULL as metadata,
                    created_at, updated_at
                FROM items
                """
            )
        
        # 3. Eliminar tabla vieja
        conn.execute("DROP TABLE items")
        
        # 4. Renombrar tabla nueva
        conn.execute("ALTER TABLE items_new RENAME TO items")
        
        # 5. Crear índices
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_source ON items(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_rareza ON items(rareza)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_key ON items(item_key)")
        
        conn.commit()
        
        print("✅ Migración completada exitosamente")
        print("⚠️ IMPORTANTE: Los items existentes tienen keys generados automáticamente")
        print("   Considera reimportar los items desde assets/ si es necesario")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error durante la migración: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
