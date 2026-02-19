"""
Test para verificar que los avatares con URLs remotas funcionan correctamente.
"""
import sys
import asyncio
sys.path.insert(0, '.')

from backend.managers.user_lookup_manager import find_user_by_global_id
from backend.managers.economy_manager import get_user_balance_by_id
from backend.managers import inventory_manager

async def test_avatars_with_urls():
    """Test que verifica que los avatares con URLs remotas funcionen"""
    print("\n" + "="*70)
    print("TEST: Avatares con URLs remotas (post-migración)")
    print("="*70)
    
    # Usuarios que tenían avatares
    test_users = [15, 16]  # YouTube users
    
    for user_id in test_users:
        print(f"\n\n📌 Testing user_id: {user_id}")
        print("="*70)
        
        loop = asyncio.get_event_loop()
        
        def get_all_user_info(user_global_id):
            lookup = find_user_by_global_id(user_global_id)
            
            if not lookup:
                return None
            
            display_name = lookup.display_name
            avatar_url = None
            
            if lookup.discord_profile and lookup.discord_profile.avatar_url:
                avatar_url = lookup.discord_profile.avatar_url
            elif lookup.youtube_profile and lookup.youtube_profile.channel_avatar_url:
                avatar_url = lookup.youtube_profile.channel_avatar_url
            
            balance = get_user_balance_by_id(lookup.user_id)
            points = balance.get("global_points", 0) if balance.get("user_exists") else 0
            points = round(float(points), 2)
            
            inventory_stats = inventory_manager.get_inventory_stats(lookup.user_id)
            total_quantity = inventory_stats.get("total_quantity", 0)
            
            has_discord = lookup.has_discord
            has_youtube = lookup.has_youtube
            
            discord_info = None
            if lookup.discord_profile:
                discord_info = {
                    'username': lookup.discord_profile.discord_username or "Desconocido",
                    'id': lookup.discord_profile.discord_id
                }
            
            youtube_info = None
            if lookup.youtube_profile:
                youtube_info = {
                    'username': lookup.youtube_profile.youtube_username or "Desconocido",
                    'channel_id': lookup.youtube_profile.youtube_channel_id or "Desconocido"
                }
            
            return {
                'user_id': lookup.user_id,
                'display_name': display_name,
                'avatar_url': avatar_url,
                'points': points,
                'total_quantity': total_quantity,
                'has_discord': has_discord,
                'has_youtube': has_youtube,
                'discord_info': discord_info,
                'youtube_info': youtube_info
            }
        
        user_info = await loop.run_in_executor(None, get_all_user_info, user_id)
        
        if not user_info:
            print("❌ Usuario no encontrado")
            continue
        
        print(f"\n📋 Información cargada:")
        print(f"  - Display Name: {user_info['display_name']}")
        print(f"  - Platforms: Discord={user_info['has_discord']}, YouTube={user_info['has_youtube']}")
        
        if user_info['avatar_url']:
            print(f"  - Avatar URL: {user_info['avatar_url']}")
            
            # Verificar que es una URL válida
            is_http = user_info['avatar_url'].startswith('http://') or user_info['avatar_url'].startswith('https://')
            if is_http:
                print(f"  ✓ Avatar URL es válida (HTTP/HTTPS)")
            else:
                print(f"  ❌ Avatar URL NO es válida")
        else:
            print(f"  - Avatar: None")
        
        if user_info['youtube_info']:
            print(f"  - YouTube: {user_info['youtube_info']['username']} ({user_info['youtube_info']['channel_id']})")
        
        if user_info['discord_info']:
            print(f"  - Discord: {user_info['discord_info']['username']} ({user_info['discord_info']['id']})")
    
    print(f"\n\n" + "="*70)
    print("✓ TEST COMPLETADO")
    print("="*70)
    return True

if __name__ == "__main__":
    success = asyncio.run(test_avatars_with_urls())
    sys.exit(0 if success else 1)
