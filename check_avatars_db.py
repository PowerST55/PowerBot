#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backend.database import get_connection

conn = get_connection()
cursor = conn.cursor()

cursor.execute('''SELECT user_id, youtube_channel_id, youtube_username, channel_avatar_url, user_type 
                  FROM youtube_profile 
                  WHERE channel_avatar_url IS NOT NULL 
                  ORDER BY user_id DESC 
                  LIMIT 10''')
rows = cursor.fetchall()
print(f'Perfiles con avatar en BD: {len(rows)} registros')
for row in rows:
    user_id, channel, username, avatar_url, user_type = row
    exists = Path(avatar_url).exists() if avatar_url else False
    print(f'\nID={user_id}, Usuario={username}, Avatar={avatar_url}, Existe={exists}')
