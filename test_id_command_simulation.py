"""
Test completo para simular el comando /id con usuarios de YouTube.
"""
import sys
sys.path.insert(0, '.')

from backend.managers.user_lookup_manager import find_user_by_global_id
from backend.managers.economy_manager import get_user_balance_by_id
from backend.managers import inventory_manager

def test_id_command_logic():
    """Simula la lógica del comando /id para usuarios de YouTube"""
    print("\n" + "="*70)
    print("TEST: Simular comando /id con usuario de YouTube")
    print("="*70)
    
    # Buscar un usuario de YouTube
    from backend.database.connection import get_connection
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT yp.user_id
        FROM youtube_profile yp
        WHERE channel_avatar_url IS NOT NULL
        LIMIT 1
    """)
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print("❌ No se encontraron usuarios de YouTube")
        return False
    
    user_id = result[0]
    print(f"\n📌 Testing con user_id: {user_id}")
    
    # Simular búsqueda por user_id (como hace el comando /id)
    lookup = find_user_by_global_id(user_id)
    
    if not lookup:
        print(f"❌ find_user_by_global_id retornó None")
        return False
    
    print(f"\n✓ Lookup exitoso")
    
    # Simular construcción del embed (igual que en general.py)
    display_name = lookup.display_name
    avatar_url = None
    
    # Prioridad: Discord > YouTube para el avatar del embed
    if lookup.discord_profile and lookup.discord_profile.avatar_url:
        avatar_url = lookup.discord_profile.avatar_url
        print(f"  - Avatar fuente: Discord")
    elif lookup.youtube_profile and lookup.youtube_profile.channel_avatar_url:
        avatar_url = lookup.youtube_profile.channel_avatar_url
        print(f"  - Avatar fuente: YouTube")
    else:
        print(f"  - Sin avatar")
    
    if not avatar_url:
        print(f"❌ ERROR: No se encontró avatar para el embed")
        return False
    
    print(f"  - Avatar URL: {avatar_url}")
    
    # Obtener balance
    balance = get_user_balance_by_id(lookup.user_id)
    points = balance.get("global_points", 0) if balance.get("user_exists") else 0
    points = round(float(points), 2)
    print(f"\n💰 Puntos: {points:,.2f}")
    
    # Obtener inventario
    inventory_stats = inventory_manager.get_inventory_stats(lookup.user_id)
    total_quantity = inventory_stats.get("total_quantity", 0)
    print(f"🎒 Inventario: {total_quantity} items")
    
    # Construir lista de plataformas
    platforms = []
    if lookup.has_discord:
        platforms.append("Discord")
    if lookup.has_youtube:
        platforms.append("YouTube")
    
    platforms_text = " y ".join(platforms) if platforms else "Sin plataformas"
    print(f"🔗 Plataformas: {platforms_text}")
    
    # Verificar que YouTube está en la lista de plataformas
    if "YouTube" not in platforms:
        print(f"❌ ERROR: YouTube no está en la lista de plataformas")
        return False
    
    print(f"✓ YouTube correctly detected")
    
    # Verificar información de YouTube
    print(f"\n📺 Información de YouTube:")
    if lookup.youtube_profile:
        youtube_name = lookup.youtube_profile.youtube_username or "Desconocido"
        youtube_channel = lookup.youtube_profile.youtube_channel_id or "Desconocido"
        print(f"  - Nombre: {youtube_name}")
        print(f"  - Canal: {youtube_channel}")
        print(f"✓ Información de YouTube disponible")
    else:
        print(f"❌ ERROR: youtube_profile es None")
        return False
    
    # Verificar información de Discord (si existe)
    print(f"\n🎭 Información de Discord:")
    if lookup.discord_profile:
        discord_name = lookup.discord_profile.discord_username or "Desconocido"
        discord_id = lookup.discord_profile.discord_id or "Desconocido"
        print(f"  - Nombre: {discord_name}")
        print(f"  - ID: {discord_id}")
    else:
        print(f"  - No tiene perfil de Discord")
    
    print(f"\n✓ TEST COMPLETADO SATISFACTORIAMENTE")
    print(f"\n📋 Resumen del embed JSON (para referencia):")
    print(f"  title: 🧾 ID de {display_name}")
    print(f"  description: **ID Universal:** `{lookup.user_id}`")
    print(f"  color: blue")
    print(f"  fields:")
    print(f"    - Puntos: {points:,.2f}")
    print(f"    - Inventario: {total_quantity} items")
    print(f"    - Plataformas: {platforms_text}")
    if lookup.youtube_profile:
        youtube_name = lookup.youtube_profile.youtube_username or "Desconocido"
        youtube_channel = lookup.youtube_profile.youtube_channel_id or "Desconocido"
        print(f"    - YouTube: {youtube_name} (`{youtube_channel}`)")
    if lookup.discord_profile:
        discord_name = lookup.discord_profile.discord_username or "Desconocido"
        discord_id = lookup.discord_profile.discord_id or "Desconocido"
        print(f"    - Discord: {discord_name} (`{discord_id}`)")
    if avatar_url:
        print(f"  thumbnail: {avatar_url}")
    
    return True

if __name__ == "__main__":
    success = test_id_command_logic()
    sys.exit(0 if success else 1)
