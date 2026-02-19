#!/usr/bin/env python3
"""
Test REAL: Descarga avatares del live chat.
Simula exactamente lo que hace el YouTubeListener con mensajes reales.
"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent))

from backend.services.youtube_api.youtube_core import YouTubeAPI
from backend.services.youtube_api.youtube_types import YouTubeMessage
from backend.services.youtube_api.youtube_user_packager import UserPackager
from backend.managers.user_manager import get_youtube_profile_by_channel_id

print("=" * 80)
print("TEST: Avatares desde Live Chat Real")
print("=" * 80)

try:
    # 1. Conectar a YouTube
    print("\n✅ PASO 1: Conectar a YouTube API...")
    yt_api = YouTubeAPI()
    if not yt_api.connect():
        print("❌ No se pudo conectar")
        sys.exit(1)
    print("  ✓ Conectado")
    
    # 2. Obtener live chat
    print("\n✅ PASO 2: Obtener live chat activo...")
    live_chat_request = yt_api.client.service.liveBroadcasts().list(
        part='snippet',
        broadcastStatus='active',
        maxResults=1
    )
    live_response = live_chat_request.execute()
    
    if not live_response.get('items'):
        print("⚠️  No hay transmisión activa ahora")
        print("  Simulando con datos de prueba...")
        
        # Datos ficticios
        sample_message_data = {
            "id": "test123",
            "snippet": {
                "type": "textMessageEvent",
                "liveChatId": "test",
                "publishedAt": "2026-02-18T22:00:00Z",
                "textMessageDetails": {
                    "messageText": "Test message"
                }
            },
            "authorDetails": {
                "channelId": "UCtest123",
                "displayName": "Test User",
                "profileImageUrl": "https://yt3.ggpht.com/GOXIf44Us-9sAb8VtcZ_B3M4VvdWuMdpX7kZih0coyhVXqBFBkV1MHnJqJcFWs5t9-f4MtDm2p8=s88-c-k-c0x00ffffff-no-rj",
                "isChatOwner": False,
                "isChatModerator": False,
                "isChatSponsor": False
            }
        }
        messages = [sample_message_data]
        
        print("  Usando mensajes de prueba")
    else:
        # 3. Obtener mensajes del chat
        print("\n✅ PASO 3: Obtener mensajes del chat...")
        live_chat_id = live_response['items'][0]['snippet']['liveChatId']
        print(f"  Live chat: {live_chat_id}")
        
        msg_request = yt_api.client.service.liveChatMessages().list(
            liveChatId=live_chat_id,
            part='snippet,authorDetails',
            maxResults=5
        )
        msg_response = msg_request.execute()
        messages = msg_response.get('items', [])
        print(f"  ✓ {len(messages)} mensajes obtenidos")
    
    if not messages:
        print("❌ No hay mensajes para procesar")
        sys.exit(1)
    
    # 4. Procesar mensajes
    print("\n✅ PASO 4: Procesar mensajes y descargar avatares...")
    print("-" * 80)
    
    for i, msg_data in enumerate(messages, 1):
        print(f"\n📨 Mensaje {i}:")
        
        try:
            # Crear YouTubeMessage
            message = YouTubeMessage(msg_data)
            print(f"  - Usuario: {message.author_name}")
            print(f"  - Canal: {message.author_channel_id}")
            print(f"  - Avatar URL: {message.profile_image_url[:50]}...")
            
            # Empaquetar
            packed = UserPackager.pack_youtube(message)
            print(f"  - Avatar en packed_data: {'✓' if packed.get('avatar_url_remote') else '❌'}")
            
            # Persistir (sin client, usa avatar_url de packed_data)
            user_id, is_new = UserPackager.persist_youtube_user(packed, client=None)
            
            if user_id:
                print(f"  ✓ Usuario persistido: ID={user_id} (is_new={is_new})")
                
                # Verificar en BD
                profile = get_youtube_profile_by_channel_id(message.author_channel_id)
                if profile:
                    avatar_url = profile.channel_avatar_url
                    if avatar_url:
                        print(f"  ✓✓ Avatar en BD: {avatar_url[:60]}...")
                        # Verificar que el archivo existe
                        if Path(avatar_url).exists():
                            size = Path(avatar_url).stat().st_size
                            print(f"  ✓✓✓ Archivo existe: {size} bytes")
                        else:
                            print(f"  ⚠️  Archivo no existe: {avatar_url}")
                    else:
                        print(f"  ❌ Avatar NULL en BD")
                else:
                    print(f"  ❌ Perfil no encontrado en BD")
            else:
                print(f"  ❌ Error persistiendo usuario")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("✅ TEST COMPLETO")
    print("=" * 80)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
