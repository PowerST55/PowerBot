#!/usr/bin/env python3
"""
Debug script para verificar avatar download en vivo.
Simula exactamente lo que hace el YouTubeListener sin dependencias externas.
"""
import sys
import logging
from pathlib import Path
from datetime import datetime

# Configurar logging para ver TODO
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

logger = logging.getLogger(__name__)

# Agregar backend al path
sys.path.insert(0, str(Path(__file__).parent))

from backend.services.youtube_api.youtube_user_packager import UserPackager
from backend.services.youtube_api.youtube_avatar_packager import AvatarManager
from backend.services.youtube_api.youtube_types import YouTubeMessage
from backend.managers.user_manager import get_youtube_profile_by_channel_id, get_user_by_id

print("=" * 80)
print("DEBUG: AVATAR DOWNLOAD SYSTEM")
print("=" * 80)

# Paso 1: Crear mensaje fake de YouTube
print("\n✅ PASO 1: Crear mensaje fake de YouTube")
message_data = {
    "id": "debug123",
    "snippet": {
        "textMessageDetails": {
            "messageText": "hola"
        },
        "publishedAt": datetime.now().isoformat()
    },
    "authorDetails": {
        "displayName": "Test User",
        "channelId": "UC2C_jShtEh6QI2_GWUt8W2g",  # Veritasium
        "isChatOwner": False,
        "isChatModerator": False,
        "isChatSponsor": False,
    }
}
fake_message = YouTubeMessage(message_data)
print(f"  - Mensaje creado: {fake_message.author_name} ({fake_message.author_channel_id})")

# Paso 2: Empaquetar datos
print("\n✅ PASO 2: Empaquetar datos de YouTube")
packed_data = UserPackager.pack_youtube(fake_message)
print(f"  - Datos empaquetados:")
for key, val in packed_data.items():
    if key != 'timestamp':
        print(f"    • {key}: {val}")

# Paso 3: Persistir sin client (por ahora)
print("\n✅ PASO 3: Persistir usuario (sin client/avatar)")
user_id, is_new = UserPackager.persist_youtube_user(packed_data, client=None)
print(f"  - Usuario: ID={user_id}, Is_new={is_new}")

# Paso 4: Verificar en BD
print("\n✅ PASO 4: Verificar datos en BD")
if user_id:
    user = get_user_by_id(user_id)
    profile = get_youtube_profile_by_channel_id(fake_message.author_channel_id)
    
    if profile:
        print(f"  - Usuario encontrado en BD:")
        print(f"    • ID universal: {profile.user_id}")
        print(f"    • Canal YOUTUBE: {profile.youtube_channel_id}")
        print(f"    • Nombre: {profile.youtube_username}")
        print(f"    • Avatar URL: {profile.channel_avatar_url}")  # ← ESTO DEBE ESTAR NULL
        print(f"    • Tipo: {profile.user_type}")
    else:
        print(f"  - ❌ Perfil NO encontrado en BD")
else:
    print(f"  - ❌ User ID es None")

# Paso 5: Probar función de avatar sin client
print("\n✅ PASO 5: Prueba directo de YouTube API (sin client)")
print("  - Intentando obtener avatar URL...")

# Crear un mock client para simular
class MockClient:
    class MockYouTube:
        def channels(self):
            # Simular que falla porque no hay API key real
            class MockChannels:
                def list(self, **kwargs):
                    logger.debug(f"Mock channels().list() called with: {kwargs}")
                    raise Exception("API call would fail - no real credentials")
            return MockChannels()
    
    youtube_api = MockYouTube()

mock_client = MockClient()
logger.info("Mock client creado para testing")

# Paso 6: Intentar obtener avatar
print("\n✅ PASO 6: Intentar get_avatar_url_from_youtube")
try:
    avatar_url = UserPackager._get_avatar_url_from_youtube(fake_message.author_channel_id, mock_client)
    print(f"  - Avatar URL obtenido: {avatar_url}")
except Exception as e:
    print(f"  - ❌ Error al obtener URL: {e}")

# Paso 7: Verificar directorio de avatares
print("\n✅ PASO 7: Verificar directorio de avatares")
avatar_dir = Path("media/yt_avatars")
if avatar_dir.exists():
    files = list(avatar_dir.glob("*"))
    print(f"  - Directorio existe: {avatar_dir}")
    print(f"  - Archivos dentro: {len(files)}")
    for f in files[:5]:  # Mostrar primeros 5
        print(f"    • {f.name} ({f.stat().st_size} bytes)")
    if len(files) > 5:
        print(f"    ... y {len(files)-5} más")
else:
    print(f"  - ❌ Directorio NO existe: {avatar_dir}")

print("\n" + "=" * 80)
print("FIN DEBUG")
print("=" * 80)
