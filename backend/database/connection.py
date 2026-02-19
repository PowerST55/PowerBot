"""
Sistema de base de datos SQLite para PowerBot.
Gestión centralizada de conexiones y operaciones.
"""
import sqlite3
from pathlib import Path

# Ruta de la base de datos
DB_PATH = Path(__file__).parent.parent / "data" / "powerbot.db"


def get_connection() -> sqlite3.Connection:
    """
    Obtiene una conexión a la base de datos SQLite.
    
    Returns:
        sqlite3.Connection: Conexión a la base de datos
    """
    # Asegurar que el directorio data existe
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Crear conexión con row_factory para acceso por nombre
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    return conn


def init_database():
    """
    Inicializa la base de datos creando todas las tablas necesarias.
    Se ejecuta automáticamente al importar el módulo.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabla principal de usuarios con ID único
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabla de perfiles Discord
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS discord_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            discord_id TEXT NOT NULL UNIQUE,
            discord_username TEXT,
            avatar_url TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)
    
    # Tabla de perfiles YouTube (lista para usar en el futuro)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS youtube_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            youtube_channel_id TEXT NOT NULL UNIQUE,
            youtube_username TEXT,
            channel_avatar_url TEXT,
            user_type TEXT DEFAULT 'regular',
            subscribers INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)

    # Wallet global por usuario (balance unificado)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            balance INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)

    # Ledger de movimientos (auditoria de puntos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallet_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            platform TEXT,
            guild_id TEXT,
            channel_id TEXT,
            source_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            UNIQUE(user_id, source_id)
        )
    """)

    # Idempotencia de eventos (para evitar doble sumatoria)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS earning_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            source_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            UNIQUE(platform, source_id)
        )
    """)
    
    # Tabla de historial de cambios (auditoría)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
        )
    """)
    
    conn.commit()
    conn.close()
    
    print(f"✅ Base de datos inicializada: {DB_PATH}")


# Inicializar automáticamente al importar
init_database()
