"""
Configuración de la tienda (canal foro) para PowerBot Discord.
Se almacena por servidor en data/discord_bot/.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any


class StoreConfig:
	"""Gestiona la configuración de la tienda (foro) por servidor."""

	def __init__(self, guild_id: int, data_dir: Optional[Path] = None):
		if data_dir is None:
			data_dir = Path(__file__).parent.parent.parent.parent / "data" / "discord_bot"

		self.guild_id = guild_id
		self.data_dir = data_dir
		self.config_file = self.data_dir / f"guild_{guild_id}_store.json"

		self._defaults = {
			"forum_channel": {
				"id": None,
				"name": None,
				"created_by": None,
				"created_at": None,
				"topic": None,
			},
			"purchase_buttons": {},
		}

		self._config = self._load()

	# ============================================================
	# Helpers
	# ============================================================

	def _defaults_copy(self) -> Dict[str, Any]:
		forum_defaults = self._defaults["forum_channel"].copy()
		return {
			"forum_channel": forum_defaults,
			"purchase_buttons": {},
		}

	def _merge_with_defaults(self, loaded: Dict[str, Any]) -> Dict[str, Any]:
		merged = self._defaults_copy()

		for key, value in loaded.items():
			if key == "forum_channel" and isinstance(value, dict):
				forum_data = merged["forum_channel"]
				forum_data.update(value)
				merged["forum_channel"] = forum_data
			else:
				merged[key] = value

		return merged

	def _load(self) -> Dict[str, Any]:
		"""Carga configuración desde JSON."""
		if self.config_file.exists():
			try:
				with open(self.config_file, "r", encoding="utf-8") as handle:
					loaded = json.load(handle)
				if isinstance(loaded, dict):
					return self._merge_with_defaults(loaded)
			except Exception as exc:
				print(f"⚠️ Error cargando store config del servidor {self.guild_id}: {exc}")
		return self._defaults_copy()

	def _save(self) -> None:
		"""Guarda configuración a disco."""
		try:
			self.data_dir.mkdir(parents=True, exist_ok=True)
			with open(self.config_file, "w", encoding="utf-8") as handle:
				json.dump(self._config, handle, indent=2, ensure_ascii=False)
		except Exception as exc:
			print(f"❌ Error guardando store config del servidor {self.guild_id}: {exc}")

	# ============================================================
	# API pública
	# ============================================================

	def get_forum_channel(self) -> Dict[str, Any]:
		"""Retorna la metadata del canal foro configurado (puede estar vacía)."""
		forum_data = self._config.get("forum_channel") or {}
		return forum_data.copy()

	def get_forum_channel_id(self) -> Optional[int]:
		"""Obtiene el ID del canal foro, si existe."""
		forum_data = self._config.get("forum_channel") or {}
		channel_id = forum_data.get("id")
		if channel_id is None:
			return None
		try:
			return int(channel_id)
		except (TypeError, ValueError):
			return None

	def set_forum_channel(
		self,
		channel_id: int,
		name: Optional[str],
		created_by: Optional[int] = None,
		topic: Optional[str] = None,
	) -> Dict[str, Any]:
		"""Guarda el canal foro en la configuración."""
		forum_data = {
			"id": int(channel_id),
			"name": name,
			"created_by": int(created_by) if created_by is not None else None,
			"created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
			"topic": topic,
		}
		self._config["forum_channel"] = forum_data
		self._save()
		return forum_data

	def clear_forum_channel(self) -> None:
		"""Reinicia la información del canal foro."""
		self._config["forum_channel"] = self._defaults["forum_channel"].copy()
		self._save()

	def list_purchase_buttons(self) -> Dict[str, Dict[str, Any]]:
		"""Retorna el índice de botones persistentes de compra por `custom_id`."""
		buttons = self._config.get("purchase_buttons")
		if not isinstance(buttons, dict):
			return {}
		return {str(custom_id): data for custom_id, data in buttons.items() if isinstance(data, dict)}

	def set_purchase_button(
		self,
		*,
		custom_id: str,
		item_key: str,
		thread_id: Optional[int] = None,
		message_id: Optional[int] = None,
	) -> Dict[str, Any]:
		"""Guarda o actualiza el registro de un botón de compra persistente."""
		buttons = self.list_purchase_buttons()
		buttons[custom_id] = {
			"item_key": str(item_key),
			"thread_id": int(thread_id) if thread_id is not None else None,
			"message_id": int(message_id) if message_id is not None else None,
			"updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
		}
		self._config["purchase_buttons"] = buttons
		self._save()
		return buttons[custom_id]

	def clear_purchase_buttons(self) -> None:
		"""Limpia todos los botones persistentes de compra."""
		self._config["purchase_buttons"] = {}
		self._save()


class StoreConfigManager:
	"""Mantiene las configs por guild en memoria."""

	def __init__(self):
		self._configs: Dict[int, StoreConfig] = {}

	def get_config(self, guild_id: int) -> StoreConfig:
		if guild_id not in self._configs:
			self._configs[guild_id] = StoreConfig(guild_id)
		return self._configs[guild_id]


_store_manager: Optional[StoreConfigManager] = None


def get_store_config(guild_id: int) -> StoreConfig:
	"""Obtiene la configuración de la tienda para un servidor."""
	global _store_manager
	if _store_manager is None:
		_store_manager = StoreConfigManager()
	return _store_manager.get_config(guild_id)


__all__ = ["StoreConfig", "get_store_config"]
