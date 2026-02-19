"""
Gestor centralizado de usuarios para PowerBot.
Maneja usuarios de Discord y YouTube con ID único universal.

Estructura:
- users: Tabla principal con ID único global
- discord_profile: Perfil específico de Discord
- youtube_profile: Perfil específico de YouTube (futuro)
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from backend.database import get_connection


# ============================================================
# CLASES DE MODELO
# ============================================================

class User:
    """Modelo de usuario universal"""
    
    def __init__(self, user_id: int, username: str, created_at: datetime = None, updated_at: datetime = None):
        self.user_id = user_id
        self.username = username
        self.created_at = created_at
        self.updated_at = updated_at
    
    def __repr__(self):
        return f"<User {self.user_id}: {self.username}>"


class DiscordProfile:
    """Modelo de perfil Discord"""
    
    def __init__(self, id: int, user_id: int, discord_id: str, discord_username: str = None,
                 avatar_url: str = None, created_at: datetime = None, updated_at: datetime = None):
        self.id = id
        self.user_id = user_id
        self.discord_id = discord_id
        self.discord_username = discord_username
        self.avatar_url = avatar_url
        self.created_at = created_at
        self.updated_at = updated_at
    
    def __repr__(self):
        return f"<DiscordProfile user_id={self.user_id} discord_id={self.discord_id}>"


class YouTubeProfile:
    """Modelo de perfil YouTube (para uso futuro)"""
    
    def __init__(self, id: int, user_id: int, youtube_channel_id: str, youtube_username: str = None,
                 channel_avatar_url: str = None, subscribers: int = 0, user_type: str = "regular",
                 created_at: datetime = None, updated_at: datetime = None):
        self.id = id
        self.user_id = user_id
        self.youtube_channel_id = youtube_channel_id
        self.youtube_username = youtube_username
        self.channel_avatar_url = channel_avatar_url
        self.subscribers = subscribers
        self.user_type = user_type  # 'owner', 'moderator', 'member', 'regular'
        self.created_at = created_at
        self.updated_at = updated_at
    
    def __repr__(self):
        return f"<YouTubeProfile user_id={self.user_id} youtube_id={self.youtube_channel_id} type={self.user_type}>"


# ============================================================
# OPERACIONES CRUD - USUARIOS GENERALES
# ============================================================

def create_user(username: str) -> User:
    """
    Crea un nuevo usuario universal.
    
    Args:
        username: Nombre de usuario
        
    Returns:
        User: Usuario creado con ID único
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """INSERT INTO users (username, created_at, updated_at)
           VALUES (?, ?, ?)""",
        (username, datetime.now(), datetime.now())
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    
    return get_user_by_id(user_id)


def get_user_by_id(user_id: int) -> Optional[User]:
    """
    Obtiene un usuario por su ID único universal.
    
    Args:
        user_id: ID único del usuario
        
    Returns:
        User: Usuario encontrado o None
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return User(row['user_id'], row['username'], row['created_at'], row['updated_at'])
    return None


def get_all_users() -> List[User]:
    """
    Obtiene todos los usuarios.
    
    Returns:
        List[User]: Lista de todos los usuarios
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    conn.close()
    
    return [User(row['user_id'], row['username'], row['created_at'], row['updated_at']) for row in rows]


def delete_user(user_id: int) -> bool:
    """
    Elimina un usuario y todos sus perfiles asociados.
    
    Args:
        user_id: ID del usuario a eliminar
        
    Returns:
        bool: True si se eliminó, False si no existía
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    rows_deleted = cursor.rowcount
    conn.close()
    
    return rows_deleted > 0


# ============================================================
# OPERACIONES CRUD - PERFILES DISCORD
# ============================================================

def create_discord_profile(user_id: int, discord_id: str, discord_username: str = None, 
                          avatar_url: str = None) -> Optional[DiscordProfile]:
    """
    Crea un perfil Discord para un usuario.
    
    Args:
        user_id: ID único del usuario
        discord_id: Discord ID del usuario
        discord_username: Nombre de usuario en Discord
        avatar_url: URL del avatar
        
    Returns:
        DiscordProfile: Perfil Discord creado o None si falla
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """INSERT INTO discord_profile (user_id, discord_id, discord_username, avatar_url, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, discord_id, discord_username, avatar_url, datetime.now(), datetime.now())
        )
        conn.commit()
        profile_id = cursor.lastrowid
        conn.close()
        
        return get_discord_profile_by_id(profile_id)
    except Exception as e:
        print(f"❌ Error creando perfil Discord: {e}")
        return None


def get_discord_profile_by_discord_id(discord_id: str) -> Optional[DiscordProfile]:
    """
    Obtiene el perfil Discord por Discord ID.
    
    Args:
        discord_id: Discord ID del usuario
        
    Returns:
        DiscordProfile: Perfil encontrado o None
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM discord_profile WHERE discord_id = ?", (discord_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return DiscordProfile(
            row['id'], row['user_id'], row['discord_id'], row['discord_username'],
            row['avatar_url'], row['created_at'], row['updated_at']
        )
    return None


def get_discord_profile_by_user_id(user_id: int) -> Optional[DiscordProfile]:
    """
    Obtiene el perfil Discord por ID de usuario universal.
    
    Args:
        user_id: ID único del usuario
        
    Returns:
        DiscordProfile: Perfil encontrado o None
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM discord_profile WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return DiscordProfile(
            row['id'], row['user_id'], row['discord_id'], row['discord_username'],
            row['avatar_url'], row['created_at'], row['updated_at']
        )
    return None


def get_discord_profile_by_id(profile_id: int) -> Optional[DiscordProfile]:
    """
    Obtiene un perfil Discord por su ID de perfil.
    
    Args:
        profile_id: ID del perfil
        
    Returns:
        DiscordProfile: Perfil encontrado o None
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM discord_profile WHERE id = ?", (profile_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return DiscordProfile(
            row['id'], row['user_id'], row['discord_id'], row['discord_username'],
            row['avatar_url'], row['created_at'], row['updated_at']
        )
    return None


def update_discord_profile(user_id: int, discord_username: str = None, avatar_url: str = None) -> bool:
    """
    Actualiza información del perfil Discord.
    
    Args:
        user_id: ID único del usuario
        discord_username: Nuevo nombre de usuario Discord
        avatar_url: Nuevo URL del avatar
        
    Returns:
        bool: True si se actualizó
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    updates = ["updated_at = ?"]
    params = [datetime.now()]
    
    if discord_username:
        updates.append("discord_username = ?")
        params.append(discord_username)
    
    if avatar_url:
        updates.append("avatar_url = ?")
        params.append(avatar_url)
    
    params.append(user_id)
    
    query = f"UPDATE discord_profile SET {', '.join(updates)} WHERE user_id = ?"
    cursor.execute(query, params)
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    
    return success


# ============================================================
# OPERACIONES CRUD - PERFILES YOUTUBE (FUTURO)
# ============================================================

def create_youtube_profile(user_id: int, youtube_channel_id: str, youtube_username: str = None,
                          channel_avatar_url: str = None, user_type: str = "regular") -> Optional[YouTubeProfile]:
    """
    Crea un perfil YouTube para un usuario.
    
    Args:
        user_id: ID único del usuario
        youtube_channel_id: ID del canal de YouTube
        youtube_username: Nombre del canal
        channel_avatar_url: URL del avatar del canal
        user_type: Tipo de usuario ('owner', 'moderator', 'member', 'regular')
        
    Returns:
        YouTubeProfile: Perfil YouTube creado o None si falla
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """INSERT INTO youtube_profile (user_id, youtube_channel_id, youtube_username, channel_avatar_url, user_type, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, youtube_channel_id, youtube_username, channel_avatar_url, user_type, datetime.now(), datetime.now())
        )
        conn.commit()
        profile_id = cursor.lastrowid
        conn.close()
        
        return get_youtube_profile_by_id(profile_id)
    except Exception as e:
        print(f"❌ Error creando perfil YouTube: {e}")
        return None


def get_youtube_profile_by_channel_id(youtube_channel_id: str) -> Optional[YouTubeProfile]:
    """
    Obtiene el perfil YouTube por ID de canal.
    
    Args:
        youtube_channel_id: ID del canal de YouTube
        
    Returns:
        YouTubeProfile: Perfil encontrado o None
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM youtube_profile WHERE youtube_channel_id = ?", (youtube_channel_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        user_type = row.get('user_type', 'regular') if hasattr(row, 'get') else getattr(row, 'user_type', 'regular')
        return YouTubeProfile(
            row['id'], row['user_id'], row['youtube_channel_id'], row['youtube_username'],
            row['channel_avatar_url'], row['subscribers'], user_type, row['created_at'], row['updated_at']
        )
    return None


def get_youtube_profile_by_id(profile_id: int) -> Optional[YouTubeProfile]:
    """
    Obtiene un perfil YouTube por su ID de perfil.
    
    Args:
        profile_id: ID del perfil
        
    Returns:
        YouTubeProfile: Perfil encontrado o None
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM youtube_profile WHERE id = ?", (profile_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        user_type = row.get('user_type', 'regular') if hasattr(row, 'get') else getattr(row, 'user_type', 'regular')
        return YouTubeProfile(
            row['id'], row['user_id'], row['youtube_channel_id'], row['youtube_username'],
            row['channel_avatar_url'], row['subscribers'], user_type, row['created_at'], row['updated_at']
        )
    return None


def get_youtube_profile_by_user_id(user_id: int) -> Optional[YouTubeProfile]:
    """
    Obtiene el perfil YouTube por ID de usuario universal.
    
    Args:
        user_id: ID único del usuario
        
    Returns:
        YouTubeProfile: Perfil encontrado o None
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM youtube_profile WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        user_type = row.get('user_type', 'regular') if hasattr(row, 'get') else getattr(row, 'user_type', 'regular')
        return YouTubeProfile(
            row['id'], row['user_id'], row['youtube_channel_id'], row['youtube_username'],
            row['channel_avatar_url'], row['subscribers'], user_type, row['created_at'], row['updated_at']
        )
    return None


def update_youtube_profile(user_id: int, youtube_username: str = None, channel_avatar_url: str = None,
                          user_type: str = None, subscribers: int = None) -> bool:
    """
    Actualiza información del perfil YouTube.
    
    Args:
        user_id: ID único del usuario
        youtube_username: Nuevo nombre de usuario YouTube
        channel_avatar_url: Nuevo URL del avatar
        user_type: Nuevo tipo de usuario
        subscribers: Nuevo conteo de suscriptores
        
    Returns:
        bool: True si se actualizó
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    updates = ["updated_at = ?"]
    params = [datetime.now()]
    
    if youtube_username:
        updates.append("youtube_username = ?")
        params.append(youtube_username)
    
    if channel_avatar_url:
        updates.append("channel_avatar_url = ?")
        params.append(channel_avatar_url)
    
    if user_type:
        updates.append("user_type = ?")
        params.append(user_type)
    
    if subscribers is not None:
        updates.append("subscribers = ?")
        params.append(subscribers)
    
    params.append(user_id)
    
    query = f"UPDATE youtube_profile SET {', '.join(updates)} WHERE user_id = ?"
    cursor.execute(query, params)
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    
    return success


# ============================================================
# OPERACIONES COMBINADAS (HELPERS)
# ============================================================

def get_or_create_discord_user(discord_id: str, discord_username: str = None, avatar_url: str = None) -> tuple:
    """
    Obtiene o crea un usuario Discord.
    
    Args:
        discord_id: Discord ID
        discord_username: Nombre de usuario Discord
        avatar_url: URL del avatar
        
    Returns:
        tuple: (user: User, discord_profile: DiscordProfile, is_new: bool)
    """
    # Obtener perfil Discord si existe
    discord_profile = get_discord_profile_by_discord_id(discord_id)
    
    if discord_profile:
        # Usuario ya existe
        user = get_user_by_id(discord_profile.user_id)
        return (user, discord_profile, False)
    
    # Crear nuevo usuario y perfil
    user = create_user(discord_username or discord_id)
    discord_profile = create_discord_profile(user.user_id, discord_id, discord_username, avatar_url)
    
    return (user, discord_profile, True)


def get_user_with_discord_profile(discord_id: str) -> Optional[tuple]:
    """
    Obtiene un usuario completo con su perfil Discord.
    
    Args:
        discord_id: Discord ID
        
    Returns:
        tuple: (user: User, discord_profile: DiscordProfile) o None
    """
    discord_profile = get_discord_profile_by_discord_id(discord_id)
    
    if not discord_profile:
        return None
    
    user = get_user_by_id(discord_profile.user_id)
    return (user, discord_profile)


def get_user_stats(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Obtiene estadísticas completas de un usuario.
    
    Args:
        user_id: ID único del usuario
        
    Returns:
        dict: Estadísticas del usuario o None
    """
    user = get_user_by_id(user_id)
    if not user:
        return None
    
    discord_profile = get_discord_profile_by_user_id(user_id)
    youtube_profile = None  # Agregado cuando sea necesario

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM wallets WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    return {
        "user": user,
        "discord_profile": discord_profile,
        "youtube_profile": youtube_profile,
        "global_points": row["balance"] if row else 0,
    }
