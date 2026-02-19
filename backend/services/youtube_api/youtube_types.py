"""
YouTube API Types and Message Models
Define las estructuras de datos base para YouTube API.
Separado para evitar circular imports.
"""
from typing import Dict, Any
from datetime import datetime


class YouTubeMessage:
    """Representa un mensaje del chat de YouTube."""
    
    def __init__(self, data: Dict[str, Any]):
        """
        Inicializa un mensaje desde los datos de la API.
        
        Args:
            data: Datos del mensaje de la API de YouTube
        """
        snippet = data.get("snippet", {})
        author_details = data.get("authorDetails", {})
        
        self.id: str = data.get("id", "")
        self.message: str = snippet.get("textMessageDetails", {}).get("messageText", "")
        self.author_name: str = author_details.get("displayName", "Unknown")
        self.author_channel_id: str = author_details.get("channelId", "")
        self.is_moderator: bool = author_details.get("isChatModerator", False)
        self.is_owner: bool = author_details.get("isChatOwner", False)
        self.is_sponsor: bool = author_details.get("isChatSponsor", False)
        self.published_at: str = snippet.get("publishedAt", "")
        self.profile_image_url: str = author_details.get("profileImageUrl", "")  # Avatar URL del mensaje
        
        # Metadata adicional útil
        self.raw_data = data
    
    def __repr__(self) -> str:
        return f"YouTubeMessage(author='{self.author_name}', message='{self.message}')"
    
    def is_privileged(self) -> bool:
        """Verifica si el autor tiene privilegios (mod, owner, sponsor)."""
        return self.is_moderator or self.is_owner or self.is_sponsor
