"""
Discord Avatar Packager
Puente entre Discord Bot y AvatarManager centralizado.
Maneja descarga y persistencia de avatares para usuarios de Discord.
"""
import logging
from typing import Optional

from backend.managers.avatar_manager import AvatarManager
from backend.managers.user_manager import update_discord_profile

logger = logging.getLogger(__name__)


class DiscordAvatarPackager:
    """Packager de avatares para Discord."""
    
    @staticmethod
    def download_and_update_avatar(user_id: int, discord_id: str, avatar_url: str = None) -> bool:
        """
        Descarga avatar de Discord y actualiza BD.
        
        Args:
            user_id: ID universal del usuario
            discord_id: ID de Discord del usuario
            avatar_url: URL del avatar
            
        Returns:
            bool: True si se descargó exitosamente
        """
        try:
            if not avatar_url:
                logger.debug(f"No avatar URL for {discord_id}")
                return False
            
            # Usar AvatarManager centralizado
            local_path = AvatarManager.download_avatar(
                user_id=discord_id,
                avatar_url_remote=avatar_url,
                platform="discord"
            )
            
            if local_path:
                # Actualizar BD
                update_discord_profile(
                    user_id=user_id,
                    avatar_url=local_path,
                )
                
                logger.info(f"✅ Avatar updated (Discord): {discord_id} → {local_path}")
                return True
            else:
                logger.warning(f"⚠️  Failed to download avatar for {discord_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error downloading avatar for {discord_id}: {e}")
            return False
    
    @staticmethod
    def detect_and_update_avatar(
        user_id: int,
        discord_id: str,
        new_avatar_url: str = None,
        current_avatar_url: str = None
    ) -> bool:
        """
        Detecta cambios de avatar y actualiza si es necesario.
        
        Args:
            user_id: ID universal del usuario
            discord_id: ID de Discord
            new_avatar_url: Nueva URL del avatar
            current_avatar_url: URL actual guardada en BD
            
        Returns:
            bool: True si hubo cambio y se actualizó
        """
        try:
            changed, new_path = AvatarManager.detect_avatar_change(
                user_id=discord_id,
                new_avatar_url=new_avatar_url,
                current_avatar_url=current_avatar_url,
                platform="discord"
            )
            
            if changed and new_path:
                # Ya está descargado, solo actualizar BD
                update_discord_profile(
                    user_id=user_id,
                    avatar_url=new_path,
                )
                logger.info(f"✅ Avatar changed (Discord): {discord_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error detecting avatar change for {discord_id}: {e}")
            return False
