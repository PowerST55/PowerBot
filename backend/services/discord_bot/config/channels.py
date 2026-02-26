"""
Gestión centralizada de canales para el bot de Discord.
Almacena configuración de canales (confesion, logs, etc) en JSON.
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any


class ChannelsConfig:
    """Gestiona la configuración de canales del bot"""
    
    def __init__(self, guild_id: int, data_dir: Path = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent.parent / "data" / "discord_bot"
        
        self.guild_id = guild_id
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.data_dir / f"guild_{guild_id}_channels.json"
        
        # Configuración por defecto
        self._defaults = {
            "confession_channel": None,
            "logs_channel": None,
            "economy_channel": None,
            "music_channel": None,
            "commands_channel": None,
            "afk_voice_channel": None,
            # Canal donde se anuncian directos de YouTube
            "livestream_channel": None,
        }
        
        self._config = self._load()
    
    def _load(self) -> Dict[str, Any]:
        """Carga la configuración desde JSON"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                return {**self._defaults, **loaded}
            except Exception as e:
                print(f"⚠️ Error cargando canales: {e}")
                return self._defaults.copy()
        return self._defaults.copy()
    
    def _save(self):
        """Guarda la configuración en JSON"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error guardando canales: {e}")
    
    def get_channel(self, channel_type: str) -> Optional[int]:
        """
        Obtiene el ID de un canal por tipo.
        
        Args:
            channel_type: Tipo de canal (ej: 'confession_channel', 'logs_channel')
        
        Returns:
            int: ID del canal o None si no está configurado
        """
        return self._config.get(channel_type)
    
    def set_channel(self, channel_type: str, channel_id: int):
        """
        Establece un canal por tipo.
        
        Args:
            channel_type: Tipo de canal (ej: 'confession_channel')
            channel_id: ID del canal
        """
        if channel_type in self._defaults:
            self._config[channel_type] = channel_id
            self._save()
            return True
        return False
    
    def remove_channel(self, channel_type: str):
        """Elimina un canal configurado"""
        if channel_type in self._defaults:
            self._config[channel_type] = None
            self._save()
            return True
        return False
    
    def get_all_channels(self) -> Dict[str, Optional[int]]:
        """Obtiene todos los canales configurados"""
        return self._config.copy()
    
    def reset(self):
        """Resetea toda la configuración de canales"""
        self._config = self._defaults.copy()
        self._save()


class ChannelsManager:
    """Gestiona configuraciones de canales para múltiples servidores"""
    
    def __init__(self):
        self._configs: Dict[int, ChannelsConfig] = {}
    
    def get_config(self, guild_id: int) -> ChannelsConfig:
        """Obtiene la configuración de canales de un servidor"""
        if guild_id not in self._configs:
            self._configs[guild_id] = ChannelsConfig(guild_id)
        return self._configs[guild_id]


# Instancia global
_channels_manager = None


def get_channels_config(guild_id: int) -> ChannelsConfig:
    """Obtiene la configuración de canales de un servidor"""
    global _channels_manager
    if _channels_manager is None:
        _channels_manager = ChannelsManager()
    return _channels_manager.get_config(guild_id)
