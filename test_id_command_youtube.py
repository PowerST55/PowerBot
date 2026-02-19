"""
Test para verificar que el comando /id funciona correctamente con usuarios de YouTube.
"""
import sys
sys.path.insert(0, '.')

from backend.managers.user_lookup_manager import find_user_by_global_id

def test_youtube_user_lookup():
    """Test para buscar usuario de YouTube por ID global"""
    print("\n" + "="*70)
    print("TEST: Búsqueda de usuario de YouTube por ID global")
    print("="*70)
    
    # Buscar el primer usuario de YouTube en la base de datos
    # Vamos a consultar directamente la BD para encontrar usuarios de YouTube
    from backend.database.connection import get_connection
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Encontrar un usuario que tenga perfil de YouTube
    cursor.execute("""
        SELECT DISTINCT yp.user_id, yp.youtube_channel_id, yp.youtube_username, yp.channel_avatar_url
        FROM youtube_profile yp
        WHERE channel_avatar_url IS NOT NULL
        LIMIT 1
    """)
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print("❌ No se encontraron usuarios de YouTube con avatar en la BD")
        return False
    
    user_id, channel_id, username, avatar_url = result
    print(f"\n✓ Usuario encontrado en BD:")
    print(f"  - User ID: {user_id}")
    print(f"  - Channel ID: {channel_id}")
    print(f"  - Username: {username}")
    print(f"  - Avatar URL: {avatar_url}")
    
    # Ahora probar el lookup
    print(f"\n📌 Buscando por User ID {user_id}...")
    lookup = find_user_by_global_id(user_id)
    
    if not lookup:
        print(f"❌ find_user_by_global_id retornó None para user_id={user_id}")
        return False
    
    print(f"\n✓ Lookup exitoso:")
    print(f"  - Display Name: {lookup.display_name}")
    print(f"  - Platform: {lookup.platform}")
    print(f"  - ID Plataforma: {lookup.platform_id}")
    
    # Verificar has_youtube
    print(f"\n📋 Propiedades de plataforma:")
    print(f"  - has_discord: {lookup.has_discord}")
    print(f"  - has_youtube: {lookup.has_youtube}")
    
    if not lookup.has_youtube:
        print(f"❌ ERROR: has_youtube retornó False pero encontramos perfil de YouTube")
        return False
    
    print(f"✓ has_youtube = True (correcto)")
    
    # Verificar youtube_profile
    print(f"\n📺 Verificando youtube_profile:")
    if not lookup.youtube_profile:
        print(f"❌ ERROR: youtube_profile es None")
        return False
    
    print(f"  - youtube_username: {lookup.youtube_profile.youtube_username}")
    print(f"  - youtube_channel_id: {lookup.youtube_profile.youtube_channel_id}")
    print(f"  - channel_avatar_url: {lookup.youtube_profile.channel_avatar_url}")
    
    # Verificar que el avatar URL sea la ruta correcta
    if not lookup.youtube_profile.channel_avatar_url:
        print(f"❌ ERROR: channel_avatar_url es None")
        return False
    
    print(f"✓ channel_avatar_url está disponible")
    
    # Verificar avatar de Discord (si existe)
    print(f"\n🎭 Verificando discord_profile:")
    if lookup.discord_profile:
        print(f"  - discord_username: {lookup.discord_profile.discord_username}")
        print(f"  - avatar_url: {lookup.discord_profile.avatar_url}")
    else:
        print(f"  - No tiene perfil de Discord (esperado)")
    
    print(f"\n✓ TEST COMPLETADO SATISFACTORIAMENTE")
    return True

if __name__ == "__main__":
    success = test_youtube_user_lookup()
    sys.exit(0 if success else 1)
