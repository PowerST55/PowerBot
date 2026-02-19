"""
Test para simular el comando /id de forma asíncrona
"""
import sys
import asyncio
sys.path.insert(0, '.')

from backend.managers.user_lookup_manager import find_user_by_discord_id, find_user_by_global_id
from backend.managers.economy_manager import get_user_balance_by_id
from backend.managers import inventory_manager

async def simulate_id_command_async():
    """Simula el comando /id de forma asíncrona como lo hace Discord"""
    print("\n" + "="*70)
    print("TEST: Simulación asíncrona del comando /id")
    print("="*70)
    
    user_id = 15
    print(f"\n📌 Buscando usuario con ID: {user_id}")
    
    loop = asyncio.get_event_loop()
    
    # Simular el load_user_data
    def load_user_data():
        print("  → Cargando lookup...")
        return find_user_by_global_id(user_id)
    
    # Simular el get_user_info
    def get_user_info(lookup):
        print("  → Cargando información del usuario...")
        display_name = lookup.display_name
        avatar_url = None
        
        # Prioridad: Discord > YouTube para el avatar del embed
        if lookup.discord_profile and lookup.discord_profile.avatar_url:
            avatar_url = lookup.discord_profile.avatar_url
        elif lookup.youtube_profile and lookup.youtube_profile.channel_avatar_url:
            avatar_url = lookup.youtube_profile.channel_avatar_url
        
        balance = get_user_balance_by_id(lookup.user_id)
        points = balance.get("global_points", 0) if balance.get("user_exists") else 0
        points = round(float(points), 2)
        
        inventory_stats = inventory_manager.get_inventory_stats(lookup.user_id)
        total_quantity = inventory_stats.get("total_quantity", 0)
        
        return {
            'display_name': display_name,
            'avatar_url': avatar_url,
            'points': points,
            'total_quantity': total_quantity
        }
    
    # Ejecutar en executor como lo hace el comando
    print("\n📌 Ejecutando operaciones síncronas en thread...")
    lookup = await loop.run_in_executor(None, load_user_data)
    
    if not lookup:
        print("❌ Usuario no encontrado")
        return False
    
    print(f"✓ Lookup cargado: {lookup.display_name}")
    
    user_info = await loop.run_in_executor(None, get_user_info, lookup)
    print(f"✓ Información cargada:")
    print(f"  - Display Name: {user_info['display_name']}")
    print(f"  - Points: {user_info['points']}")
    print(f"  - Inventory: {user_info['total_quantity']}")
    print(f"  - Avatar: {user_info['avatar_url']}")
    
    # Construcción del embed
    platforms = []
    if lookup.has_discord:
        platforms.append("Discord")
    if lookup.has_youtube:
        platforms.append("YouTube")
    
    platforms_text = " y ".join(platforms) if platforms else "Sin plataformas"
    
    print(f"\n📋 Información del embed:")
    print(f"  - Title: 🧾 ID de {user_info['display_name']}")
    print(f"  - Description: **ID Universal:** `{lookup.user_id}`")
    print(f"  - Points: {user_info['points']:,.2f}")
    print(f"  - Inventory: {user_info['total_quantity']} items")
    print(f"  - Platforms: {platforms_text}")
    
    if lookup.discord_profile:
        discord_name = lookup.discord_profile.discord_username or "Desconocido"
        discord_id = lookup.discord_profile.discord_id
        print(f"  - Discord: {discord_name} ({discord_id})")
    
    if lookup.youtube_profile:
        youtube_name = lookup.youtube_profile.youtube_username or "Desconocido"
        youtube_channel = lookup.youtube_profile.youtube_channel_id or "Desconocido"
        print(f"  - YouTube: {youtube_name} ({youtube_channel})")
    
    if user_info['avatar_url']:
        print(f"  - Avatar: {user_info['avatar_url']}")
    else:
        print(f"  - Avatar: None")
    
    print(f"\n✓ TEST COMPLETADO SATISFACTORIAMENTE")
    return True

if __name__ == "__main__":
    success = asyncio.run(simulate_id_command_async())
    sys.exit(0 if success else 1)
