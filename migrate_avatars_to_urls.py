"""
Script para migrar avatares existentes de rutas locales a URLs remotas.
Esto actualiza la BD con URLs HTTP/HTTPS en lugar de rutas locales.
"""
import sys
sys.path.insert(0, '.')

from backend.database.connection import get_connection

def migrate_avatars_to_urls():
    """Migra avatares de rutas locales a URLs remotas"""
    print("\n" + "="*70)
    print("MIGRACIÓN: Avatares de rutas locales a URLs remotas")
    print("="*70)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Buscar YouTube avatars con rutas locales
    print("\n📺 Buscando YouTube avatars con rutas locales...")
    cursor.execute("""
        SELECT id, user_id, youtube_channel_id, channel_avatar_url 
        FROM youtube_profile 
        WHERE channel_avatar_url IS NOT NULL 
        AND channel_avatar_url LIKE 'media/%'
    """)
    
    yt_rows = cursor.fetchall()
    print(f"Encontrados: {len(yt_rows)} YouTube avatars")
    
    updated_yt = 0
    for row in yt_rows:
        profile_id, user_id, channel_id, local_path = row
        print(f"\n  [YT] user_id={user_id}, channel_id={channel_id}")
        print(f"       local_path: {local_path}")
        
        # Construir URL remota de YouTube
        # YouTube CDN: https://yt.ggpht.com/CHANNEL_ID=s48-c
        yt_url = f"https://yt.ggpht.com/{channel_id}=s88-c"
        print(f"       nueva URL: {yt_url}")
        
        # Actualizar BD
        cursor.execute("""
            UPDATE youtube_profile 
            SET channel_avatar_url = ? 
            WHERE id = ?
        """, (yt_url, profile_id))
        updated_yt += 1
        print(f"       ✓ Actualizado")
    
    # Buscar Discord avatars con rutas locales
    print("\n\n🎭 Buscando Discord avatars con rutas locales...")
    cursor.execute("""
        SELECT id, user_id, discord_id, avatar_url 
        FROM discord_profile 
        WHERE avatar_url IS NOT NULL 
        AND avatar_url LIKE 'media/%'
    """)
    
    dc_rows = cursor.fetchall()
    print(f"Encontrados: {len(dc_rows)} Discord avatars")
    
    # Para Discord, necesitamos la URL del CDN que se obtiene de discord.py
    # Pero no la tenemos aquí. Vamos a dejarlas vacías para que se recolecten
    # la próxima vez que el usuario se registre.
    
    updated_dc = 0
    for row in dc_rows:
        profile_id, user_id, discord_id, local_path = row
        print(f"\n  [DC] user_id={user_id}, discord_id={discord_id}")
        print(f"       local_path: {local_path}")
        print(f"       ⚠️  No se puede recuperar URL de Discord CDN automáticamente")
        print(f"       Se recolectará cuando el usuario interactúe nuevamente")
        
        # Establecer a None para que se recolecte la próxima vez
        cursor.execute("""
            UPDATE discord_profile 
            SET avatar_url = NULL 
            WHERE id = ?
        """, (profile_id,))
        updated_dc += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n\n" + "="*70)
    print(f"✓ MIGRACIÓN COMPLETADA")
    print(f"  - YouTube avatars actualizados: {updated_yt}")
    print(f"  - Discord avatars reseteados: {updated_dc} (se recolectarán automáticamente)")
    print("="*70)
    
    return True

if __name__ == "__main__":
    try:
        migrate_avatars_to_urls()
        print("\n✓ Migración exitosa")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error en migración: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
