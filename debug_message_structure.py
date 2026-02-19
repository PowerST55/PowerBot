#!/usr/bin/env python3
"""
Script para obtener la estructura completa de un mensaje del chat de YouTube.
Muestra qué datos están disponibles en authorDetails.
"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent))

from backend.services.youtube_api.youtube_core import YouTubeAPI

print("=" * 80)
print("Debug: Estructura de mensajes del chat de YouTube")  
print("=" * 80)

try:
    yt_api = YouTubeAPI()
    yt_api.connect()
    client = yt_api.client
    
    # Obtener live chat del canal autenticado
    print("\n✅ Obteniendo live chat...")
    live_chat_request = client.service.liveBroadcasts().list(
        part='snippet',
        broadcastStatus='active',
        maxResults=1
    )
    live_response = live_chat_request.execute()
    
    if not live_response.get('items'):
        print("⚠️  No hay transmisión en vivo activa")
        print("\nProbando con datos ficticios...")
        
        # Mostrar estructura esperada
        sample_message = {
            "id": "msg123",
            "snippet": {
                "createdAt": "2026-02-18T...",
                "publishedAt": "2026-02-18T...",
                "type": "textMessageEvent",
                "liveChatId": "chat123",
                "textMessageDetails": {
                    "messageText": "Hola!"
                }
            },
            "authorDetails": {
                "channelId": "UC_example",
                "displayName": "Usuario",
                "profileImageUrl": "https://yt3.ggpht.com/...",
                "isVerified": False,
                "isChatOwner": False,
                "isChatModerator": False, 
                "isChatSponsor": False
            }
        }
        print("\nEstructura esperada de mensaje:")
        print(json.dumps(sample_message, indent=2))
        
    else:
        live_chat_id = live_response['items'][0]['snippet']['liveChatId']
        print(f"✓ Live chat encontrado: {live_chat_id}")
        
        print("\n✅ Obteniendo uno mensajes de chat...")
        msg_request = client.service.liveChatMessages().list(
            liveChatId=live_chat_id,
            part='snippet,authorDetails',
            maxResults=1
        )
        msg_response = msg_request.execute()
        
        if msg_response.get('items'):
            message = msg_response['items'][0]
            print("\n📨 Datos completos del primer mensaje:")
            print(json.dumps(message, indent=2))
            
            # Extraer datos clave
            auth = message.get('authorDetails', {})
            print("\n✅ Datos del autor:")
            print(f"  - channelId: {auth.get('channelId')}")
            print(f"  - displayName: {auth.get('displayName')}")
            print(f"  - profileImageUrl: {auth.get('profileImageUrl')}")
            print(f"  - isChatOwner: {auth.get('isChatOwner')}")
            print(f"  - isChatModerator: {auth.get('isChatModerator')}")
            print(f"  - isChatSponsor: {auth.get('isChatSponsor')}")
        else:
            print("❌ No hay mensajes en el chat")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
