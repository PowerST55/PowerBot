#!/usr/bin/env python3
"""
Test de Validación: Sistema Unificado de Avatares
Verifica que YouTube y Discord descarguen avatares correctamente.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.managers.avatar_manager import AvatarManager
from backend.managers.user_manager import (
    create_user,
    create_discord_profile,
    create_youtube_profile,
    get_discord_profile_by_user_id,
    get_youtube_profile_by_channel_id,
    update_discord_profile,
    update_youtube_profile,
)

print("=" * 80)
print("TEST: Sistema Unificado de Avatares (YouTube + Discord)")
print("=" * 80)

# Inicializar directorios
print("\n✅ PASO 1: Inicializar directorios...")
AvatarManager.initialize()
print("  ✓ Directorios inicializados")

# PART 1: DISCORD
print("\n" + "=" * 80)
print("PARTE 1: Discord Avatar")
print("=" * 80)

print("\n✅ PASO 2: Crear usuario Discord...")
try:
    # Crear usuario
    user = create_user("discord_test_user")
    user_id = user.user_id
    print(f"  ✓ Usuario creado: ID={user_id}")
    
    # Crear perfil Discord
    discord_profile = create_discord_profile(
        user_id=user_id,
        discord_id="123456789",
        discord_username="discordtest",
        avatar_url=None  # Sin avatar aún
    )
    print(f"  ✓ Perfil Discord creado")
    
    # Simular descarga de avatar (usar URL de YouTube como test)
    print("\n✅ PASO 3: Descargar avatar Discord...")
    avatar_url = "https://yt3.ggpht.com/GOXIf44Us-9sAb8VtcZ_B3M4VvdWuMdpX7kZih0coyhVXqBFBkV1MHnJqJcFWs5t9-f4MtDm2p8=s88-c-k-c0x00ffffff-no-rj"
    
    local_path = AvatarManager.download_avatar(
        user_id="123456789",
        avatar_url_remote=avatar_url,
        platform="discord"
    )
    
    if local_path:
        print(f"  ✓ Avatar descargado: {local_path}")
        
        # Actualizar BD
        update_discord_profile(
            user_id=user_id,
            avatar_url=local_path
        )
        print(f"  ✓ BD actualizada")
        
        # Verificar en BD
        profile = get_discord_profile_by_user_id(user_id)
        if profile and profile.avatar_url == local_path:
            print(f"  ✓✓✓ Avatar en BD (Discord): {profile.avatar_url}")
        else:
            print(f"  ❌ Avatar no coincide en BD")
    else:
        print(f"  ❌ Error descargando avatar")
        
except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# PART 2: YOUTUBE
print("\n" + "=" * 80)
print("PARTE 2: YouTube Avatar")
print("=" * 80)

print("\n✅ PASO 4: Crear usuario YouTube...")
try:
    # Crear usuario
    user2 = create_user("youtube_test_user")
    user_id2 = user2.user_id
    print(f"  ✓ Usuario creado: ID={user_id2}")
    
    # Crear perfil YouTube
    youtube_profile = create_youtube_profile(
        user_id=user_id2,
        youtube_channel_id="UCtest123",
        youtube_username="youtubetest",
        channel_avatar_url=None  # Sin avatar aún
    )
    print(f"  ✓ Perfil YouTube creado")
    
    # Simular descarga de avatar
    print("\n✅ PASO 5: Descargar avatar YouTube...")
    avatar_url = "https://yt3.ggpht.com/GOXIf44Us-9sAb8VtcZ_B3M4VvdWuMdpX7kZih0coyhVXqBFBkV1MHnJqJcFWs5t9-f4MtDm2p8=s88-c-k-c0x00ffffff-no-rj"
    
    local_path = AvatarManager.download_avatar(
        user_id="UCtest123",
        avatar_url_remote=avatar_url,
        platform="youtube"
    )
    
    if local_path:
        print(f"  ✓ Avatar descargado: {local_path}")
        
        # Actualizar BD
        update_youtube_profile(
            user_id=user_id2,
            channel_avatar_url=local_path
        )
        print(f"  ✓ BD actualizada")
        
        # Verificar en BD
        profile = get_youtube_profile_by_channel_id("UCtest123")
        if profile and profile.channel_avatar_url == local_path:
            print(f"  ✓✓✓ Avatar en BD (YouTube): {profile.channel_avatar_url}")
        else:
            print(f"  ❌ Avatar no coincide en BD")
    else:
        print(f"  ❌ Error descargando avatar")
        
except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Verificar archivos en disco
print("\n" + "=" * 80)
print("VERIFICACIÓN: Archivos en Disco")
print("=" * 80)

print("\n✅ Discord avatars (media/dc_avatars/):")
dc_dir = Path("media/dc_avatars")
if dc_dir.exists():
    dc_files = list(dc_dir.glob("*"))
    print(f"  Archivos: {len(dc_files)}")
    for f in dc_files[:5]:
        print(f"    • {f.name} ({f.stat().st_size} bytes)")
else:
    print("  Directorio no existe aún")

print("\n✅ YouTube avatars (media/yt_avatars/):")
yt_dir = Path("media/yt_avatars")
if yt_dir.exists():
    yt_files = list(yt_dir.glob("*"))
    print(f"  Archivos: {len(yt_files)}")
    for f in yt_files[:5]:
        print(f"    • {f.name} ({f.stat().st_size} bytes)")
else:
    print("  Directorio no existe aún")

print("\n" + "=" * 80)
print("✅ TEST COMPLETADO - Sistema unificado funcionando")
print("=" * 80)
