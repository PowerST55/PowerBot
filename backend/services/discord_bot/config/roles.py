"""
Gestión centralizada de roles para el bot de Discord.
Almacena configuración de roles (DJ, MOD, etc) en JSON.
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any


class RolesConfig:
    """Gestiona la configuración de roles del bot"""
    
    def __init__(self, guild_id: int, data_dir: Path = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent.parent / "data" / "discord_bot"
        
        self.guild_id = guild_id
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.data_dir / f"guild_{guild_id}_roles.json"
        
        # Configuración por defecto
        self._defaults = {
            "dj": None,
            "mod": [],  # MOD es una lista porque puede haber múltiples
            # Rol usado para notificaciones (ej: streams en vivo)
            "notifications": None,
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
                print(f"⚠️ Error cargando roles: {e}")
                return self._defaults.copy()
        return self._defaults.copy()
    
    def _save(self):
        """Guarda la configuración en JSON"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Error guardando roles: {e}")
    
    def get_role(self, role_type: str) -> Optional[int]:
        """Obtiene el ID de un rol por tipo"""
        return self._config.get(role_type.lower())
    
    def set_role(self, role_type: str, role_id: int):
        """Establece el ID de un rol por tipo"""
        self._config[role_type.lower()] = role_id
        self._save()
    
    def add_mod_role(self, role_id: int) -> bool:
        """Agrega un rol MOD a la lista. Retorna False si ya existe"""
        if role_id not in self._config["mod"]:
            self._config["mod"].append(role_id)
            self._save()
            return True
        return False
    
    def remove_mod_role(self, role_id: int) -> bool:
        """Remueve un rol MOD de la lista. Retorna False si no existe"""
        if role_id in self._config["mod"]:
            self._config["mod"].remove(role_id)
            self._save()
            return True
        return False
    
    def get_mod_roles(self) -> list:
        """Obtiene todos los roles MOD"""
        return self._config.get("mod", [])
    
    def get_all(self) -> Dict[str, Any]:
        """Obtiene toda la configuración de roles"""
        return self._config


class RolesManager:
    """Gestiona roles de múltiples servidores"""
    
    def __init__(self):
        self._configs: Dict[int, RolesConfig] = {}
    
    def get_config(self, guild_id: int) -> RolesConfig:
        """Obtiene configuración de roles de un servidor"""
        if guild_id not in self._configs:
            self._configs[guild_id] = RolesConfig(guild_id)
        return self._configs[guild_id]


# Instancia global
_roles_manager = None


def get_roles_config(guild_id: int) -> RolesConfig:
    """Obtiene la configuración de roles de un servidor"""
    global _roles_manager
    if _roles_manager is None:
        _roles_manager = RolesManager()
    return _roles_manager.get_config(guild_id)
