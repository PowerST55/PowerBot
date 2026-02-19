"""
Avatar Manager - Gestor Centralizado de Avatares
Maneja descargas y almacenamiento de avatares para múltiples plataformas (Discord, YouTube).

Responsabilidades:
- Descargar avatares desde URLs remotas
- Almacenar localmente con validaciones
- Soportar múltiples plataformas y directorios
- Detectar cambios de avatares
- Limpiar avatares no usados
"""
import logging
import hashlib
import requests
from pathlib import Path
from typing import Optional, Literal
from datetime import datetime

logger = logging.getLogger(__name__)

# Directorios de almacenamiento por plataforma
AVATARS_BASE = Path(__file__).parent.parent.parent / "media"
AVATARS_YOUTUBE = AVATARS_BASE / "yt_avatars"
AVATARS_DISCORD = AVATARS_BASE / "dc_avatars"


class AvatarManager:
    """Gestor centralizado de avatares para múltiples plataformas."""
    
    # Extensiones permitidas
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    
    # Tamaño máximo en MB
    MAX_SIZE_MB = 10
    
    @staticmethod
    def initialize(platform: Literal["youtube", "discord"] = None) -> bool:
        """
        Inicializa directorios de almacenamiento.
        
        Args:
            platform: Plataforma específica o None para todas
            
        Returns:
            bool: True si fue exitoso
        """
        try:
            if platform is None or platform == "youtube":
                AVATARS_YOUTUBE.mkdir(parents=True, exist_ok=True)
                logger.info(f"✅ YouTube avatar directory initialized: {AVATARS_YOUTUBE}")
            
            if platform is None or platform == "discord":
                AVATARS_DISCORD.mkdir(parents=True, exist_ok=True)
                logger.info(f"✅ Discord avatar directory initialized: {AVATARS_DISCORD}")
            
            return True
        except Exception as e:
            logger.error(f"❌ Error initializing avatar directories: {e}")
            return False
    
    @staticmethod
    def download_avatar(
        user_id: str,
        avatar_url_remote: str,
        platform: Literal["youtube", "discord"] = "youtube"
    ) -> Optional[str]:
        """
        Descarga y almacena un avatar.
        
        Ahora devuelve la URL remota directamente en lugar de ruta local.
        Esto es mejor para Discord embeds que necesitan URLs HTTP/HTTPS.
        Los archivos se guardan localmente como caché pero se devuelve la URL.
        
        Args:
            user_id: ID del usuario (channel_id para YouTube, discord_id para Discord)
            avatar_url_remote: URL remoto del avatar
            platform: Plataforma ("youtube" o "discord")
            
        Returns:
            str: URL remoto del avatar (para BD), o None si falló
        """
        if not avatar_url_remote:
            logger.debug(f"No avatar URL provided for {user_id} ({platform})")
            return None
        
        # Seleccionar directorio según plataforma
        if platform == "youtube":
            avatars_dir = AVATARS_YOUTUBE
            media_path = "media/yt_avatars"
        elif platform == "discord":
            avatars_dir = AVATARS_DISCORD
            media_path = "media/dc_avatars"
        else:
            logger.error(f"Unknown platform: {platform}")
            return None
        
        try:
            # Descargar imagen para validaciones locales
            response = requests.get(avatar_url_remote, timeout=10)
            response.raise_for_status()
            
            # Validar tamaño
            content_length = len(response.content)
            if content_length > AvatarManager.MAX_SIZE_MB * 1024 * 1024:
                logger.warning(f"Avatar too large ({content_length} bytes) for {user_id}")
                return None
            
            # Determinar extensión
            content_type = response.headers.get('content-type', 'image/jpeg')
            extension = AvatarManager._get_extension_from_content_type(content_type)
            
            if not extension:
                logger.warning(f"Unknown content type {content_type}, using .jpg")
                extension = '.jpg'
            
            # Crear directorio si no existe
            avatars_dir.mkdir(parents=True, exist_ok=True)
            
            # Generar nombre de archivo basado en user_id
            filename = f"{user_id}{extension}"
            filepath = avatars_dir / filename
            
            # Guardar archivo localmente como caché
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"✅ Avatar cached locally ({platform}): {filename} ({content_length} bytes)")
            
            # ⭐ DEVOLVER LA URL REMOTA EN LUGAR DE RUTA LOCAL
            # Discord y otros servicios necesitan URLs HTTP/HTTPS
            return avatar_url_remote
            
        except requests.RequestException as e:
            logger.error(f"❌ Error downloading avatar for {user_id} ({platform}): {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error saving avatar {user_id} ({platform}): {e}")
            return None
    
    @staticmethod
    def detect_avatar_change(
        user_id: str,
        new_avatar_url: str,
        current_avatar_url: str = None,
        platform: Literal["youtube", "discord"] = "youtube"
    ) -> tuple[bool, Optional[str]]:
        """
        Detecta si el avatar de un usuario cambió.
        
        Args:
            user_id: ID del usuario
            new_avatar_url: Nueva URL remota
            current_avatar_url: URL remota anterior
            platform: Plataforma
            
        Returns:
            Tuple: (cambió, nueva_ruta_local)
        """
        if not current_avatar_url:
            # Primera vez viendo este avatar
            new_path = AvatarManager.download_avatar(user_id, new_avatar_url, platform)
            return (True, new_path)
        
        if new_avatar_url != current_avatar_url:
            # URL cambió
            logger.info(f"Avatar changed for {user_id} ({platform})")
            new_path = AvatarManager.download_avatar(user_id, new_avatar_url, platform)
            return (True, new_path)
        
        # Avatar no cambió
        return (False, None)
    
    @staticmethod
    def get_avatar_local_path(
        user_id: str,
        platform: Literal["youtube", "discord"] = "youtube"
    ) -> Optional[str]:
        """
        Obtiene la ruta local del avatar si existe.
        
        Args:
            user_id: ID del usuario
            platform: Plataforma
            
        Returns:
            Ruta del archivo si existe, None si no
        """
        avatars_dir = AVATARS_YOUTUBE if platform == "youtube" else AVATARS_DISCORD
        media_path = "media/yt_avatars" if platform == "youtube" else "media/dc_avatars"
        
        for ext in AvatarManager.ALLOWED_EXTENSIONS:
            filepath = avatars_dir / f"{user_id}{ext}"
            if filepath.exists():
                return f"{media_path}/{user_id}{ext}"
        
        return None
    
    @staticmethod
    def _get_extension_from_content_type(content_type: str) -> Optional[str]:
        """
        Obtiene extensión según Content-Type.
        
        Args:
            content_type: Header Content-Type
            
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
        
        main_type = content_type.split(';')[0].strip().lower()
        return type_mapping.get(main_type)
    
    @staticmethod
    def cleanup_unused_avatars(
        active_user_ids: list,
        platform: Literal["youtube", "discord"] = "youtube"
    ) -> int:
        """
        Limpia avatares de usuarios no activos.
        
        Args:
            active_user_ids: Lista de IDs activos
            platform: Plataforma
            
        Returns:
            Cantidad de archivos eliminados
        """
        avatars_dir = AVATARS_YOUTUBE if platform == "youtube" else AVATARS_DISCORD
        deleted_count = 0
        
        try:
            for filepath in avatars_dir.glob('*'):
                if not filepath.is_file():
                    continue
                
                user_id = filepath.stem  # Nombre sin extensión
                
                if user_id not in active_user_ids:
                    try:
                        filepath.unlink()
                        deleted_count += 1
                        logger.debug(f"Cleaned up ({platform}): {filepath.name}")
                    except Exception as e:
                        logger.error(f"Error deleting avatar {filepath.name}: {e}")
            
            if deleted_count > 0:
                logger.info(f"✅ Cleanup ({platform}): {deleted_count} unused avatars removed")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup ({platform}): {e}")
            return 0
    
    @staticmethod
    def get_avatar_hash(
        user_id: str,
        platform: Literal["youtube", "discord"] = "youtube"
    ) -> Optional[str]:
        """
        Obtiene hash MD5 del avatar para detectar cambios.
        
        Args:
            user_id: ID del usuario
            platform: Plataforma
            
        Returns:
            Hash MD5 o None
        """
        local_path = AvatarManager.get_avatar_local_path(user_id, platform)
        
        if not local_path:
            return None
        
        try:
            avatars_dir = AVATARS_YOUTUBE if platform == "youtube" else AVATARS_DISCORD
            filename = Path(local_path).name
            filepath = avatars_dir / filename
            
            md5_hash = hashlib.md5()
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    md5_hash.update(chunk)
            
            return md5_hash.hexdigest()
            
        except Exception as e:
            logger.error(f"Error computing hash for {user_id} ({platform}): {e}")
            return None
