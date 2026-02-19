#!/usr/bin/env python3
"""
Debug para ver qué devuelve YouTube API exactamente.
"""
import sys
from pathlib import Path
import json
import logging

logging.basicConfig(level=logging.WARNING)

sys.path.insert(0, str(Path(__file__).parent))

from backend.services.youtube_api.youtube_core import YouTubeAPI

print("=" * 80)
print("Debug: Qué devuelve YouTube API para thumbnails")
print("=" * 80)

try:
    yt_api = YouTubeAPI()
    yt_api.connect()
    client = yt_api.client
    
    # Primero, obtener el canal del usuario autenticado
    print("\n📺 Obteniendo canal autenticado...")
    print("-" * 50)
    
    try:
        request = client.service.channels().list(
            part='snippet,statistics',
            mine=True,
            maxResults=1
        )
        response = request.execute()
        
        if response.get('items'):
            channel = response['items'][0]
            channel_id = channel['id']
            name = channel['snippet']['title']
            print(f"✓ Canal encontrado: {name} ({channel_id})")
            
            # Ahora traer thumbnails
            request = client.service.channels().list(
                part='snippet',
                id=channel_id,
                fields='items(id,snippet(title,thumbnails))'
            )
            response = request.execute()
            
            if response.get('items'):
                channel = response['items'][0]
                thumbnails = channel['snippet'].get('thumbnails', {})
                print(f"\n📸 Thumbnails disponibles: {list(thumbnails.keys())}")
                for key, val in thumbnails.items():
                    print(f"  {key}: {val}")
                    
                # Probar descargar thumbnail
                if 'default' in thumbnails:
                    print(f"\n✅ Thumbnail 'default' disponible: {thumbnails['default']['url']}")
                elif 'medium' in thumbnails:
                    print(f"\n✅ Thumbnail 'medium' disponible: {thumbnails['medium']['url']}")
                else:
                    print(f"\n⚠️  No hay thumbnails en keys esperadas")
        else:
            print("❌ No se encontró canal autenticado")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

except Exception as e:
    print(f"Error de conexión: {e}")
    import traceback
    traceback.print_exc()
