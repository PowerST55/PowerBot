"""
Gestión de configuración de economía para PowerBot Discord.
Almacena: nombre de moneda, símbolo, límites, tasas, etc.
"""
from pathlib import Path
from typing import Optional, Dict, Any
import json


class EconomyConfig:
    """Gestiona configuración de economía del servidor"""
    
    def __init__(self, guild_id: int, data_dir: Path = None):
        if data_dir is None:
            # Calcula la ruta a backend/data/discord_bot/
            data_dir = Path(__file__).parent.parent.parent.parent / "data" / "discord_bot"
        
        self.guild_id = guild_id
        self.data_dir = data_dir
        self.config_file = self.data_dir / f"guild_{guild_id}_economy.json"
        
        self._defaults = {
            "currency": {
                "name": "pews",              # Nombre de la moneda
                "symbol": "💎",             # Símbolo
            },
            "points": {
                "amount": 10,               # Cantidad de puntos que da el bot
                "interval": 300,            # Intervalo en segundos (300 = 5 min)
            },
            "earning": {
                "enabled": True,
            },
            "earning_channels": []          # Canales donde se ganan puntos
        }
        
        self._config = self._load()
    
    def _load(self) -> Dict[str, Any]:
        """Carga configuración desde JSON"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)

                merged = self._defaults.copy()
                merged_currency = dict(self._defaults["currency"])
                merged_currency.update(loaded.get("currency", {}))
                merged["currency"] = merged_currency

                merged_points = dict(self._defaults["points"])
                merged_points.update(loaded.get("points", {}))
                merged["points"] = merged_points

                merged_earning = dict(self._defaults["earning"])
                merged_earning.update(loaded.get("earning", {}))
                merged["earning"] = merged_earning

                merged["earning_channels"] = loaded.get(
                    "earning_channels",
                    self._defaults["earning_channels"],
                )
                return merged
            except Exception as e:
                print(f"⚠️ Error cargando economía del servidor {self.guild_id}: {e}")
                return self._defaults.copy()
        return self._defaults.copy()
    
    def _save(self):
        """Guarda configuración a JSON"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error guardando economía del servidor {self.guild_id}: {e}")
    
    def get_currency_name(self) -> str:
        """Obtiene el nombre de la moneda"""
        return self._config["currency"]["name"]
    
    def get_currency_symbol(self) -> str:
        """Obtiene el símbolo de la moneda"""
        return self._config["currency"]["symbol"]
    
    def set_currency(self, name: str, symbol: str):
        """Actualiza el nombre y símbolo de la moneda"""
        self._config["currency"]["name"] = name
        self._config["currency"]["symbol"] = symbol
        self._save()
    
    def get_points_amount(self) -> int:
        """Obtiene la cantidad de puntos que da el bot"""
        return self._config["points"]["amount"]
    
    def get_points_interval(self) -> int:
        """Obtiene el intervalo de puntos en segundos"""
        return self._config["points"]["interval"]
    
    def set_points_amount(self, amount: int):
        """Actualiza la cantidad de puntos"""
        self._config["points"]["amount"] = amount
        self._save()
    
    def set_points_interval(self, interval: int):
        """Actualiza el intervalo de puntos en segundos"""
        self._config["points"]["interval"] = interval
        self._save()
    
    def set_points(self, amount: int, interval: int):
        """Actualiza cantidad e intervalo de puntos"""
        self._config["points"]["amount"] = amount
        self._config["points"]["interval"] = interval
        self._save()

    def is_earning_enabled(self) -> bool:
        """Indica si el earning global está activado."""
        return bool(self._config.get("earning", {}).get("enabled", True))

    def set_earning_enabled(self, enabled: bool):
        """Activa o desactiva earning global para mensajes y voz."""
        self._config.setdefault("earning", {})
        self._config["earning"]["enabled"] = bool(enabled)
        self._save()
    
    # === MÉTODOS PARA CANALES DE GANANCIAS ===
    
    def get_earning_channels(self) -> list:
        """
        Obtiene la lista de canales donde se ganan puntos.
        
        Returns:
            list: Lista de IDs de canales
        """
        return self._config.get("earning_channels", [])
    
    def add_earning_channel(self, channel_id: int) -> bool:
        """
        Agrega un canal a la lista de canales de ganancias.
        
        Args:
            channel_id: ID del canal de Discord
            
        Returns:
            bool: True si se agregó, False si ya existía
        """
        earning_channels = self._config.get("earning_channels", [])
        
        if channel_id in earning_channels:
            return False
        
        earning_channels.append(channel_id)
        self._config["earning_channels"] = earning_channels
        self._save()
        return True
    
    def remove_earning_channel(self, channel_id: int) -> bool:
        """
        Elimina un canal de la lista de canales de ganancias.
        
        Args:
            channel_id: ID del canal de Discord
            
        Returns:
            bool: True si se eliminó, False si no existía
        """
        earning_channels = self._config.get("earning_channels", [])
        
        if channel_id not in earning_channels:
            return False
        
        earning_channels.remove(channel_id)
        self._config["earning_channels"] = earning_channels
        self._save()
        return True
    
    def is_earning_channel(self, channel_id: int) -> bool:
        """
        Verifica si un canal da puntos por hablar.
        
        Args:
            channel_id: ID del canal de Discord
            
        Returns:
            bool: True si es un canal de ganancias
        """
        earning_channels = self._config.get("earning_channels", [])
        return channel_id in earning_channels
    
    def clear_earning_channels(self):
        """Elimina todos los canales de ganancias configurados"""
        self._config["earning_channels"] = []
        self._save()

    def prune_deleted_earning_channels(self, valid_channel_ids: list[int] | set[int]) -> int:
        """
        Elimina de data los earning_channels que ya no existen en el servidor.

        Args:
            valid_channel_ids: IDs de canales válidos actualmente en Discord.

        Returns:
            int: cantidad de canales eliminados de la configuración.
        """
        valid_ids = {int(channel_id) for channel_id in valid_channel_ids}
        current_channels = self._config.get("earning_channels", [])
        normalized_current: list[int] = []

        for channel_id in current_channels:
            try:
                normalized_current.append(int(channel_id))
            except Exception:
                continue

        filtered_channels = [channel_id for channel_id in normalized_current if channel_id in valid_ids]
        removed_count = len(normalized_current) - len(filtered_channels)

        if removed_count > 0:
            self._config["earning_channels"] = filtered_channels
            self._save()

        return removed_count


class EconomyManager:
    """Gestiona economía de múltiples servidores"""
    
    def __init__(self):
        self._configs: Dict[int, EconomyConfig] = {}
    
    def get_config(self, guild_id: int) -> EconomyConfig:
        """Obtiene configuración de economía de un servidor"""
        if guild_id not in self._configs:
            self._configs[guild_id] = EconomyConfig(guild_id)
        return self._configs[guild_id]


# Instancia global
_economy_manager = None


def get_economy_config(guild_id: int) -> EconomyConfig:
    """Obtiene la configuración de economía de un servidor"""
    global _economy_manager
    if _economy_manager is None:
        _economy_manager = EconomyManager()
    return _economy_manager.get_config(guild_id)


def list_configured_economy_guild_ids(data_dir: Path | None = None) -> list[int]:
    """Lista guilds con archivo de economía persistido."""
    if data_dir is None:
        data_dir = Path(__file__).parent.parent.parent.parent / "data" / "discord_bot"

    guild_ids: list[int] = []
    for path in sorted(data_dir.glob("guild_*_economy.json")):
        try:
            guild_ids.append(int(path.stem.split("_")[1]))
        except Exception:
            continue
    return guild_ids
