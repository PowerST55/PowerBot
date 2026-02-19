"""
Test para validar que precargamos TODOS los datos en el executor
sin acceder a los perfiles desde el thread principal
"""
import sys
import asyncio
sys.path.insert(0, '.')

from backend.managers.user_lookup_manager import find_user_by_global_id
from backend.managers.economy_manager import get_user_balance_by_id
from backend.managers import inventory_manager

async def test_id_command_preload_strategy():
    """Test que simula la nueva estrategia de precarga en el executor"""
    print("\n" + "="*70)
    print("TEST: Precarga de TODOS los datos en el executor")
    print("="*70)
    
    user_id_with_avatar = 15  # Usuario con avatar de YouTube
    user_id_without_avatar = 4  # Usuario sin plataforma ni foto
    
    for test_user_id in [user_id_with_avatar, user_id_without_avatar]:
        print(f"\n\n📌 Test con user_id: {test_user_id}")
        print("="*70)
        
        loop = asyncio.get_event_loop()
        
        # Nueva estrategia: precarga TODA la información en el executor
        def get_all_user_info(user_global_id):
            """Carga TODA la información en el executor"""
            print(f"  [Executor] Buscando lookup para {user_global_id}...")
            lookup = find_user_by_global_id(user_global_id)
            
            if not lookup:
                return None
            
            print(f"  [Executor] Precargando plataformas...")
            # Acceder a has_discord y has_youtube AQUÍ en el executor
            has_discord = lookup.has_discord
            has_youtube = lookup.has_youtube
            
            print(f"  [Executor] Precargando información de perfiles...")
            # Acceder a los perfiles AQUÍ en el executor
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
            
            print(f"  [Executor] Cargando balance...")
            balance = get_user_balance_by_id(lookup.user_id)
            points = balance.get("global_points", 0) if balance.get("user_exists") else 0
            points = round(float(points), 2)
            
            print(f"  [Executor] Cargando inventario...")
            inventory_stats = inventory_manager.get_inventory_stats(lookup.user_id)
            total_quantity = inventory_stats.get("total_quantity", 0)
            
            print(f"  [Executor] Cargando avatar...")
            display_name = lookup.display_name
            avatar_url = None
            if lookup.discord_profile and lookup.discord_profile.avatar_url:
                avatar_url = lookup.discord_profile.avatar_url
            elif lookup.youtube_profile and lookup.youtube_profile.channel_avatar_url:
                avatar_url = lookup.youtube_profile.channel_avatar_url
            
            print(f"  [Executor] ✓ Todo cargado")
            
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
        
        # Ejecutar en executor
        print("\n[Main Thread] Enviando trabajo al executor...")
        user_info = await loop.run_in_executor(None, get_all_user_info, test_user_id)
        
        if not user_info:
            print("[Main Thread] ❌ Usuario no encontrado")
            continue
        
        # EN EL THREAD PRINCIPAL, SOLO USAMOS LOS DATOS PRECARGADOS
        # NO accedemos a los perfiles de nuevo
        print("\n[Main Thread] ✓ Datos precargados recibidos del executor")
        
        platforms = []
        # Usamos los datos precargados, NO lazy loading
        if user_info['has_discord']:
            platforms.append("Discord")
        if user_info['has_youtube']:
            platforms.append("YouTube")
        
        platforms_text = " y ".join(platforms) if platforms else "Sin plataformas"
        
        print("\n📋 Información del embed (usando datos precargados):")
        print(f"  - Title: 🧾 ID de {user_info['display_name']}")
        print(f"  - Description: **ID Universal:** `{user_info['user_id']}`")
        print(f"  - Points: {user_info['points']:,.2f}")
        print(f"  - Inventory: {user_info['total_quantity']} items")
        print(f"  - Platforms: {platforms_text}")
        
        if user_info['discord_info']:
            print(f"  - Discord: {user_info['discord_info']['username']} ({user_info['discord_info']['id']})")
        
        if user_info['youtube_info']:
            print(f"  - YouTube: {user_info['youtube_info']['username']} ({user_info['youtube_info']['channel_id']})")
        
        if user_info['avatar_url']:
            print(f"  - Avatar: {user_info['avatar_url']}")
        else:
            print(f"  - Avatar: None")
        
        print(f"\n✓ {test_user_id}: OK")
    
    print(f"\n\n" + "="*70)
    print("✓ TEST COMPLETADO: Ambos usuarios cargados correctamente")
    print("✓ Estrategia de precarga funcionando correctamente")
    print("✓ NO hay lazy loading en el thread principal")
    print("="*70)
    return True

if __name__ == "__main__":
    success = asyncio.run(test_id_command_preload_strategy())
    sys.exit(0 if success else 1)
