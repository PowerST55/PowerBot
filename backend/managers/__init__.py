"""
Managers centralizados para PowerBot.
Gestión de usuarios, economía, etc.
"""
from .user_manager import (
    User,
    DiscordProfile,
    YouTubeProfile,
    create_user,
    get_user_by_id,
    get_all_users,
    delete_user,
    create_discord_profile,
    get_discord_profile_by_discord_id,
    get_discord_profile_by_user_id,
    update_discord_profile,
    create_youtube_profile,
    get_youtube_profile_by_channel_id,
    get_or_create_discord_user,
    get_user_with_discord_profile,
    get_user_stats,
)

from .avatar_manager import AvatarManager

from .user_lookup_manager import (
    UserLookupResult,
    find_user_by_discord_id,
    find_user_by_youtube_channel_id,
    find_user_by_global_id,
    find_user,
    find_user_smart,
    user_exists,
    get_user_platform_ids,
)

__all__ = [
    # User Manager - CRUD básico
    'User',
    'DiscordProfile',
    'YouTubeProfile',
    'create_user',
    'get_user_by_id',
    'get_all_users',
    'delete_user',
    'create_discord_profile',
    'get_discord_profile_by_discord_id',
    'get_discord_profile_by_user_id',
    'update_discord_profile',
    'create_youtube_profile',
    'get_youtube_profile_by_channel_id',
    'get_or_create_discord_user',
    'get_user_with_discord_profile',
    'get_user_stats',
    
    # Avatar Manager - Gestión centralizada de avatares
    'AvatarManager',
    
    # User Lookup Manager - Búsqueda flexible
    'UserLookupResult',
    'find_user_by_discord_id',
    'find_user_by_youtube_channel_id',
    'find_user_by_global_id',
    'find_user',
    'find_user_smart',
    'user_exists',
    'get_user_platform_ids',
]
