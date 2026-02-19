"""
Helper de búsqueda universal de usuarios en todas las plataformas.

Este módulo proporciona utilidades para buscar usuarios de forma flexible
a través de diferentes plataformas (Discord, YouTube, ID global) sin
necesidad de duplicar lógica en cada comando.

Uso básico:
    from backend.managers.user_lookup_manager import find_user_by_discord_id
    
    user = find_user_by_discord_id("123456789")
    if user:
        print(f"Usuario: {user.display_name}")
        print(f"Puntos: {user.global_points}")
"""
from typing import Optional, Dict, Any, Literal
from backend.managers.user_manager import (
    get_discord_profile_by_discord_id,
    get_youtube_profile_by_channel_id,
    get_user_by_id,
    get_user_stats,
    DiscordProfile,
    YouTubeProfile,
    User
)

Platform = Literal["discord", "youtube", "global"]


class UserLookupResult:
    """
    Resultado de búsqueda de usuario con toda la información necesaria.
    
    Esta clase actúa como un wrapper que proporciona acceso fácil a toda
    la información del usuario, independientemente de la plataforma.
    
    Attributes:
        user_id: ID único global del usuario
        platform: Plataforma desde donde se encontró el usuario
        platform_id: ID del usuario en la plataforma específica
    
    Example:
        user = find_user_by_discord_id("123456789")
        print(user.display_name)      # Nombre para mostrar
        print(user.global_points)     # Puntos globales
        print(user.stats)             # Estadísticas completas
    """
    
    def __init__(self, user_id: int, platform: Platform, platform_id: str):
        self.user_id = user_id
        self.platform = platform
        self.platform_id = platform_id
        
        # Cache interno para evitar consultas repetidas
        self._cached_stats = None
        self._cached_user = None
        self._cached_discord_profile = None
        self._cached_youtube_profile = None
    
    @property
    def user(self) -> Optional[User]:
        """Obtiene el objeto User principal (lazy loading)"""
        if self._cached_user is None:
            self._cached_user = get_user_by_id(self.user_id)
        return self._cached_user
    
    @property
    def stats(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene estadísticas completas del usuario (lazy loading).
        
        Returns:
            dict con: user, discord_profile, youtube_profile, global_points
        """
        if self._cached_stats is None:
            self._cached_stats = get_user_stats(self.user_id)
        return self._cached_stats
    
    @property
    def discord_profile(self) -> Optional[DiscordProfile]:
        """Obtiene perfil de Discord si existe"""
        if self._cached_discord_profile is None:
            from backend.managers.user_manager import get_discord_profile_by_user_id
            self._cached_discord_profile = get_discord_profile_by_user_id(self.user_id)
        return self._cached_discord_profile
    
    @property
    def youtube_profile(self) -> Optional[YouTubeProfile]:
        """Obtiene perfil de YouTube si existe"""
        if self._cached_youtube_profile is None:
            from backend.managers.user_manager import get_youtube_profile_by_user_id
            self._cached_youtube_profile = get_youtube_profile_by_user_id(self.user_id)
        return self._cached_youtube_profile
    
    @property
    def display_name(self) -> str:
        """
        Nombre para mostrar según la plataforma disponible.
        
        Prioridad:
        1. Nombre de la plataforma de origen
        2. Nombre de Discord si existe
        3. Nombre de YouTube si existe
        4. Username general
        5. Fallback a "User #{user_id}"
        """
        # Intentar desde la plataforma de origen
        if self.platform == "discord" and self.discord_profile:
            return self.discord_profile.discord_username or f"User #{self.user_id}"
        elif self.platform == "youtube" and self.youtube_profile:
            return self.youtube_profile.youtube_username or f"User #{self.user_id}"
        
        # Intentar desde Discord si no fue la plataforma de origen
        if self.discord_profile and self.discord_profile.discord_username:
            return self.discord_profile.discord_username
        
        # Intentar desde YouTube
        if self.youtube_profile and self.youtube_profile.youtube_username:
            return self.youtube_profile.youtube_username
        
        # Usar username general
        if self.user and self.user.username:
            return self.user.username
        
        # Fallback
        return f"User #{self.user_id}"
    
    @property
    def global_points(self) -> int:
        """
        Puntos globales del usuario en todas las plataformas.
        
        Returns:
            int: Total de puntos globales (0 si no hay datos)
        """
        stats = self.stats
        return stats.get('global_points', 0) if stats else 0
    
    @property
    def has_discord(self) -> bool:
        """Verifica si el usuario tiene perfil de Discord"""
        return self.discord_profile is not None
    
    @property
    def has_youtube(self) -> bool:
        """Verifica si el usuario tiene perfil de YouTube"""
        return self.youtube_profile is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convierte el resultado a diccionario para serialización.
        
        Returns:
            dict con toda la información del usuario
        """
        return {
            "user_id": self.user_id,
            "platform": self.platform,
            "platform_id": self.platform_id,
            "display_name": self.display_name,
            "global_points": self.global_points,
            "has_discord": self.has_discord,
            "has_youtube": self.has_youtube,
            "stats": self.stats
        }
    
    def __repr__(self):
        return f"<UserLookupResult user_id={self.user_id} platform={self.platform} name='{self.display_name}'>"
    
    def __bool__(self):
        """Permite usar if user: en lugar de if user is not None:"""
        return True


# ============================================================
# FUNCIONES DE BÚSQUEDA POR PLATAFORMA
# ============================================================

def find_user_by_discord_id(discord_id: str) -> Optional[UserLookupResult]:
    """
    Busca un usuario por su Discord ID.
    
    Args:
        discord_id: Discord ID del usuario (string numérico)
        
    Returns:
        UserLookupResult si el usuario existe, None si no
        
    Example:
        >>> user = find_user_by_discord_id("123456789012345678")
        >>> if user:
        ...     print(f"Usuario: {user.display_name}")
        ...     print(f"Puntos: {user.global_points}")
    """
    profile = get_discord_profile_by_discord_id(str(discord_id))
    if profile:
        return UserLookupResult(
            user_id=profile.user_id,
            platform="discord",
            platform_id=str(discord_id)
        )
    return None


def find_user_by_youtube_channel_id(youtube_channel_id: str) -> Optional[UserLookupResult]:
    """
    Busca un usuario por su YouTube Channel ID.
    
    Args:
        youtube_channel_id: YouTube Channel ID (generalmente empieza con "UC")
        
    Returns:
        UserLookupResult si el usuario existe, None si no
        
    Example:
        >>> user = find_user_by_youtube_channel_id("UCxxxxxxxxxxxxxxxxxx")
        >>> if user:
        ...     print(f"Canal: {user.display_name}")
    """
    profile = get_youtube_profile_by_channel_id(youtube_channel_id)
    if profile:
        return UserLookupResult(
            user_id=profile.user_id,
            platform="youtube",
            platform_id=youtube_channel_id
        )
    return None


def find_user_by_global_id(user_id: int) -> Optional[UserLookupResult]:
    """
    Busca un usuario por su ID global universal.
    
    Este es el ID único que identifica al usuario en todas las plataformas.
    
    Args:
        user_id: ID único universal del usuario
        
    Returns:
        UserLookupResult si el usuario existe, None si no
        
    Example:
        >>> user = find_user_by_global_id(42)
        >>> if user:
        ...     print(f"Usuario ID 42: {user.display_name}")
    """
    user = get_user_by_id(user_id)
    if user:
        return UserLookupResult(
            user_id=user_id,
            platform="global",
            platform_id=str(user_id)
        )
    return None


# ============================================================
# FUNCIÓN DE BÚSQUEDA UNIFICADA
# ============================================================

def find_user(platform: Platform, platform_id: str) -> Optional[UserLookupResult]:
    """
    Busca un usuario en cualquier plataforma de forma unificada.
    
    Esta es la función principal que debes usar cuando conoces la plataforma.
    
    Args:
        platform: Plataforma donde buscar ("discord", "youtube", "global")
        platform_id: ID del usuario en esa plataforma
        
    Returns:
        UserLookupResult si el usuario existe, None si no
        
    Example:
        >>> # Buscar en Discord
        >>> user = find_user("discord", "123456789012345678")
        >>> 
        >>> # Buscar en YouTube
        >>> user = find_user("youtube", "UCxxxxxxxxxxxxxxxxxx")
        >>> 
        >>> # Buscar por ID global
        >>> user = find_user("global", "42")
    """
    if platform == "discord":
        return find_user_by_discord_id(platform_id)
    elif platform == "youtube":
        return find_user_by_youtube_channel_id(platform_id)
    elif platform == "global":
        try:
            return find_user_by_global_id(int(platform_id))
        except (ValueError, TypeError):
            return None
    return None


# ============================================================
# BÚSQUEDA INTELIGENTE (AUTO-DETECCIÓN)
# ============================================================

def find_user_smart(identifier: str, prefer_platform: Optional[Platform] = None) -> Optional[UserLookupResult]:
    """
    Búsqueda inteligente que intenta detectar automáticamente la plataforma.
    
    Esta función analiza el formato del identificador y prueba diferentes
    plataformas en orden de probabilidad.
    
    Heurísticas:
    - Numérico corto (< 10 dígitos) → ID global
    - Empieza con "UC" → YouTube Channel ID
    - Numérico largo (≥ 10) → Discord ID
    - Otro formato → Intenta prefer_platform
    
    Args:
        identifier: ID del usuario en cualquier formato
        prefer_platform: Plataforma preferida si hay ambigüedad
        
    Returns:
        UserLookupResult si encuentra el usuario, None si no
        
    Example:
        >>> # Detecta automáticamente que es un ID corto (global)
        >>> user = find_user_smart("42")
        >>> 
        >>> # Detecta automáticamente que es YouTube
        >>> user = find_user_smart("UCxxxxxxxxxxxxxxxxxx")
        >>> 
        >>> # Detecta Discord ID (largo numérico)
        >>> user = find_user_smart("123456789012345678")
        >>> 
        >>> # Con preferencia si es ambiguo
        >>> user = find_user_smart("12345", prefer_platform="discord")
    """
    identifier = str(identifier).strip()
    
    # 1. Intentar ID global primero si es numérico corto
    if identifier.isdigit() and len(identifier) < 10:
        try:
            result = find_user_by_global_id(int(identifier))
            if result:
                return result
        except ValueError:
            pass
    
    # 2. Intentar YouTube si empieza con UC (patrón de YouTube Channel ID)
    if identifier.startswith("UC") and len(identifier) > 10:
        result = find_user_by_youtube_channel_id(identifier)
        if result:
            return result
    
    # 3. Intentar Discord si es numérico largo (Discord IDs son 17-19 dígitos)
    if identifier.isdigit() and len(identifier) >= 10:
        result = find_user_by_discord_id(identifier)
        if result:
            return result
    
    # 4. Intentar plataforma preferida como último recurso
    if prefer_platform:
        result = find_user(prefer_platform, identifier)
        if result:
            return result
    
    return None


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def user_exists(platform: Platform, platform_id: str) -> bool:
    """
    Verifica rápidamente si un usuario existe sin crear objeto completo.
    
    Args:
        platform: Plataforma donde buscar
        platform_id: ID del usuario
        
    Returns:
        bool: True si existe, False si no
        
    Example:
        >>> if user_exists("discord", "123456789012345678"):
        ...     print("Usuario existe en Discord")
    """
    return find_user(platform, platform_id) is not None


def get_user_platform_ids(user_id: int) -> Dict[str, Optional[str]]:
    """
    Obtiene todos los IDs de plataforma de un usuario.
    
    Args:
        user_id: ID global del usuario
        
    Returns:
        dict con IDs de cada plataforma (None si no tiene perfil)
        
    Example:
        >>> ids = get_user_platform_ids(42)
        >>> print(ids)
        {
            'discord': '123456789012345678',
            'youtube': 'UCxxxxxxxxxxxxxxxxxx',
            'global': '42'
        }
    """
    from backend.managers.user_manager import (
        get_discord_profile_by_user_id,
        # get_youtube_profile_by_user_id  # Agregar esta función si no existe
    )
    
    discord_profile = get_discord_profile_by_user_id(user_id)
    # youtube_profile = get_youtube_profile_by_user_id(user_id)
    
    return {
        'discord': discord_profile.discord_id if discord_profile else None,
        'youtube': None,  # youtube_profile.youtube_channel_id if youtube_profile else None
        'global': str(user_id)
    }


# ============================================================
# EXPORTACIONES
# ============================================================

__all__ = [
    # Clase principal
    'UserLookupResult',
    
    # Búsqueda por plataforma específica
    'find_user_by_discord_id',
    'find_user_by_youtube_channel_id',
    'find_user_by_global_id',
    
    # Búsqueda unificada
    'find_user',
    'find_user_smart',
    
    # Utilidades
    'user_exists',
    'get_user_platform_ids',
    
    # Tipos
    'Platform',
]
