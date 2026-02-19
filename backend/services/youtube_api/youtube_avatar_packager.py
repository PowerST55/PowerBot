"""
YouTube Avatar Manager
Descarga, almacena y gestiona avatares de usuarios de YouTube.

Características:
- Descarga avatares desde YouTube
- Detecta cambios en avatares (comparación de URLs)
- Almacena localmente en media/yt_avatars/
- Mantiene referencias en BD (URL local y remota)
- Limpia avatares no usados
"""
import logging
import hashlib
import requests
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Ruta base de almacenamiento
AVATARS_DIR = Path(__file__).parent.parent.parent.parent / "media" / "yt_avatars"


class AvatarManager:
    """Gestiona descargas y almacenamiento de avatares de YouTube."""
    
    # Extensiones permitidas
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    
    # Tamaño máximo en MB
    MAX_SIZE_MB = 10
    
    @staticmethod
    def initialize() -> bool:
        """
        Inicializa el directorio de almacenamiento.
        
        Returns:
            bool: True si fue exitoso
        """
        try:
            AVATARS_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"✅ Avatar directory initialized: {AVATARS_DIR}")
            return True
        except Exception as e:
            logger.error(f"❌ Error initializing avatar directory: {e}")
            return False
    
    @staticmethod
    def download_avatar(youtube_channel_id: str, avatar_url_remote: str = None) -> Optional[str]:
        """
        Descarga y almacena un avatar de YouTube.
        
        Args:
            youtube_channel_id: ID del canal de YouTube
            avatar_url_remote: URL remoto del avatar (de YouTube API)
            
        Returns:
            str: Ruta relativa al avatar almacenado, o None si falló
        """
        if not avatar_url_remote:
            logger.debug(
                f"No avatar URL provided for {youtube_channel_id}. "
                f"Cannot download."
            )
            return None
        
        try:
            # Descargar la imagen
            response = requests.get(avatar_url_remote, timeout=10)
            response.raise_for_status()
            
            # Validar tamaño
            content_length = len(response.content)
            if content_length > AvatarManager.MAX_SIZE_MB * 1024 * 1024:
                logger.warning(f"Avatar too large ({content_length} bytes) for {youtube_channel_id}")
                return None
            
            # Determinar extensión
            content_type = response.headers.get('content-type', 'image/jpeg')
            extension = AvatarManager._get_extension_from_content_type(content_type)
            
            if not extension:
                # Si no detecta extensión, usar jpg por defecto
                logger.warning(f"Unknown content type {content_type}, using .jpg")
                extension = '.jpg'
            
            # Generar nombre de archivo único basado en channel_id
            filename = f"{youtube_channel_id}{extension}"
            filepath = AVATARS_DIR / filename
            
            # Crear directorio si no existe
            AVATARS_DIR.mkdir(parents=True, exist_ok=True)
            
            # Guardar archivo
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            # Ruta relativa para almacenar en BD
            relative_path = f"media/yt_avatars/{filename}"
            
            logger.info(f"✅ Avatar descargado: {filename} ({content_length} bytes)")
            
            return relative_path
            
        except requests.RequestException as e:
            logger.error(f"❌ Error descargando avatar para {youtube_channel_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado guardando avatar {youtube_channel_id}: {e}")
            return None
    
    @staticmethod
    def detect_avatar_change(
        youtube_channel_id: str,
        new_avatar_url_remote: str,
        current_avatar_url_remote: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Detecta si el avatar de un usuario cambió.
        
        Args:
            youtube_channel_id: ID del canal
            new_avatar_url_remote: Nueva URL remota del avatar
            current_avatar_url_remote: URL remota anterior (guardada en BD)
            
        Returns:
            Tuple: (cambió_avatar, nueva_ruta_local)
                - cambió_avatar: True si detectó cambio
                - nueva_ruta_local: Ruta del nuevo avatar, o None
        """
        # Si no hay URL anterior o es diferente, hay cambio
        if not current_avatar_url_remote:
            # Primera vez viendo este avatar
            logger.debug(f"First avatar for {youtube_channel_id}")
            new_path = AvatarManager.download_avatar(youtube_channel_id, new_avatar_url_remote)
            return (True, new_path)
        
        if new_avatar_url_remote != current_avatar_url_remote:
            # URL cambió, descargar nuevo avatar
            logger.info(f"Avatar URL changed for {youtube_channel_id}")
            new_path = AvatarManager.download_avatar(youtube_channel_id, new_avatar_url_remote)
            return (True, new_path)
        
        # Avatar no cambió
        return (False, None)
    
    @staticmethod
    def get_avatar_local_path(youtube_channel_id: str) -> Optional[str]:
        """
        Obtiene la ruta local del avatar si existe.
        
        Args:
            youtube_channel_id: ID del canal
            
        Returns:
            Ruta del archivo si existe, None si no
        """
        for ext in AvatarManager.ALLOWED_EXTENSIONS:
            filepath = AVATARS_DIR / f"{youtube_channel_id}{ext}"
            if filepath.exists():
                return f"media/yt_avatars/{youtube_channel_id}{ext}"
        
        return None
    
    @staticmethod
    def _get_extension_from_content_type(content_type: str) -> Optional[str]:
        """
        Obtiene la extensión de archivo según el content-type.
        
        Args:
            content_type: Header Content-Type del servidor
            
        Returns:
            Extensión con punto (ej: '.jpg') o None
        """
        type_mapping = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
        }
        
        # Tomar el tipo principal (antes del ;)
        main_type = content_type.split(';')[0].strip().lower()
        
        return type_mapping.get(main_type)
    
    @staticmethod
    def cleanup_unused_avatars(active_channel_ids: list) -> int:
        """
        Limpia avatares de canales que ya no están activos.
        
        Args:
            active_channel_ids: Lista de IDs de canal activos
            
        Returns:
            Cantidad de archivos eliminados
        """
        deleted_count = 0
        
        try:
            for filepath in AVATARS_DIR.glob('*'):
                if not filepath.is_file():
                    continue
                
                # Extraer channel_id del nombre (eliminar extensión)
                channel_id = filepath.stem
                
                if channel_id not in active_channel_ids:
                    try:
                        filepath.unlink()
                        deleted_count += 1
                        logger.debug(f"Cleaned up avatar: {filepath.name}")
                    except Exception as e:
                        logger.error(f"Error deleting avatar {filepath.name}: {e}")
            
            if deleted_count > 0:
                logger.info(f"✅ Cleanup complete: {deleted_count} unused avatars removed")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")
            return 0
    
    @staticmethod
    def get_avatar_hash(youtube_channel_id: str) -> Optional[str]:
        """
        Obtiene el hash MD5 del archivo avatar local.
        Útil para detectar cambios sin depender de URLs.
        
        Args:
            youtube_channel_id: ID del canal
            
        Returns:
            Hash MD5 del archivo o None si no existe
        """
        local_path = AvatarManager.get_avatar_local_path(youtube_channel_id)
        
        if not local_path:
            return None
        
        try:
            filepath = AVATARS_DIR / Path(local_path).name
            
            md5_hash = hashlib.md5()
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    md5_hash.update(chunk)
            
            return md5_hash.hexdigest()
            
        except Exception as e:
            logger.error(f"Error computing hash for {youtube_channel_id}: {e}")
            return None
