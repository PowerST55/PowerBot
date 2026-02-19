#!/usr/bin/env python3
"""
Test real de descargar avatares con YouTubeClient autenticado.
"""
import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from backend.services.youtube_api.youtube_core import YouTubeAPI, YouTubeClient
from backend.services.youtube_api.youtube_user_packager import UserPackager
from backend.services.youtube_api.youtube_avatar_manager import AvatarManager

print("=" * 80)
print("TEST REAL: Avatar Download conYouTubeAPI autenticada")
print("=" * 80)

# Paso 1: Cargar cliente YouTube
print("\n✅ PASO 1: Crear YouTubeAPI desde credenciales...")
try:
    yt_api = YouTubeAPI()
    if not yt_api.connect():
        print(f"  ❌ No se pudo conectar a YouTube API")
        sys.exit(1)
    
    client = yt_api.client
    print(f"  ✓ Cliente creado exitosamente")
    print(f"  - Tiene service: {hasattr(client, 'service')}")
    print(f"  - service type: {type(client.service)}")
except Exception as e:
    print(f"  ❌ Error creando cliente: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Paso 2: Obtener avatar URL desde API real
print("\n✅ PASO 2: Obtener avatar URL de Veritasium (UC2C_jShtEh6QI2_GWUt8W2g)...")
channel_id = "UC2C_jShtEh6QI2_GWUt8W2g"

try:
    avatar_url = UserPackager._get_avatar_url_from_youtube(channel_id, client)
    print(f"  ✓ Avatar URL obtenido: {avatar_url}")
    
    if not avatar_url:
        print(f"  ⚠️  Avatar URL es None/empty")
        sys.exit(1)
        
except Exception as e:
    print(f"  ❌ Error obteniendo avatar: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Paso 3: Descargar el avatar
print("\n✅ PASO 3: Descargar imagen del avatar...")
try:
    local_path = AvatarManager.download_avatar(channel_id, avatar_url)
    print(f"  ✓ Avatar descargado a: {local_path}")
    
    if not local_path:
        print(f"  ❌ Descarga retornó None")
        sys.exit(1)
    
    # Verificar que existe
    import os
    if os.path.exists(local_path):
        size = os.path.getsize(local_path)
        print(f"  ✓ Archivo existe: {size} bytes")
    else:
        print(f"  ❌ Archivo no existe: {local_path}")
        sys.exit(1)
        
except Exception as e:
    print(f"  ❌ Error descargando: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Paso 4: Actualizar BD
print("\n✅ PASO 4: Actualizar BD con avatar URL...")
try:
    from backend.managers.user_manager import (
        create_user, 
        create_youtube_profile,
        get_youtube_profile_by_channel_id,
        update_youtube_profile
    )
    
    # Crear usuario de prueba
    user = create_user("veritasium_test")
    user_id = user.user_id
    print(f"  ✓ Usuario creado: ID={user_id}")
    
    # Crear perfil YouTube SIN avatar
    profile = create_youtube_profile(
        user_id=user_id,
        youtube_channel_id=channel_id,
        youtube_username="veritasium_test",
        user_type="regular"
    )
    print(f"  ✓ Perfil YouTube creado sin avatar")
    
    # Actualizar con avatar
    updated = update_youtube_profile(
        user_id=user_id,
        channel_avatar_url=local_path
    )
    print(f"  ✓ Perfil actualizado: {updated}")
    
    # Verificar en BD
    profile_updated = get_youtube_profile_by_channel_id(channel_id)
    print(f"  ✓ Avatar en BD: {profile_updated.channel_avatar_url}")
    
    if profile_updated.channel_avatar_url == local_path:
        print(f"  ✓✓✓ AVATAR GUARDADO CORRECTAMENTE EN BD ✓✓✓")
    else:
        print(f"  ❌ Avatar en BD no coincide")
        print(f"     Esperado: {local_path}")
        print(f"     Obtenido: {profile_updated.channel_avatar_url}")
        
except Exception as e:
    print(f"  ❌ Error en BD: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ TODO FUNCIONÓ - Sistema de avatares está correcto")
print("=" * 80)
