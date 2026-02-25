"""
Configuración de mina por servidor.
Guarda rate, canal y tabla de ítems con probabilidad/valor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MineConfig:
	"""Gestiona la configuración de mina para un servidor."""

	def __init__(self, guild_id: int, data_dir: Path | None = None):
		if data_dir is None:
			data_dir = Path(__file__).parent.parent.parent.parent / "data" / "discord_bot"

		self.guild_id = int(guild_id)
		self.data_dir = data_dir
		self.config_file = self.data_dir / f"guild_{self.guild_id}_mine.json"
		self._defaults: dict[str, Any] = {
			"rate_seconds": 300,
			"mine_channel_id": None,
			"items": [],
		}
		self._config = self._load()

	def _load(self) -> dict[str, Any]:
		if self.config_file.exists():
			try:
				with open(self.config_file, "r", encoding="utf-8") as file:
					loaded = json.load(file)
				if isinstance(loaded, dict):
					merged = {**self._defaults, **loaded}
					if not isinstance(merged.get("items"), list):
						merged["items"] = []
					return merged
			except Exception as exc:
				print(f"⚠️ Error cargando config de mina guild {self.guild_id}: {exc}")
		return dict(self._defaults)

	def _save(self) -> None:
		try:
			self.data_dir.mkdir(parents=True, exist_ok=True)
			with open(self.config_file, "w", encoding="utf-8") as file:
				json.dump(self._config, file, indent=2, ensure_ascii=False)
		except Exception as exc:
			print(f"❌ Error guardando config de mina guild {self.guild_id}: {exc}")

	def get_rate_seconds(self) -> int:
		return int(self._config.get("rate_seconds", 300))

	def set_rate_seconds(self, seconds: int) -> None:
		self._config["rate_seconds"] = max(1, int(seconds))
		self._save()

	def get_mine_channel_id(self) -> int | None:
		value = self._config.get("mine_channel_id")
		if value is None:
			return None
		try:
			return int(value)
		except Exception:
			return None

	def set_mine_channel_id(self, channel_id: int | None) -> None:
		self._config["mine_channel_id"] = int(channel_id) if channel_id is not None else None
		self._save()

	def list_items(self) -> list[dict[str, Any]]:
		items = self._config.get("items", [])
		if not isinstance(items, list):
			return []
		return [item for item in items if isinstance(item, dict)]

	def add_item(self, name: str, price: float, probability: int) -> bool:
		normalized_name = str(name).strip()
		if not normalized_name:
			return False

		items = self.list_items()
		lower_name = normalized_name.lower()
		for item in items:
			if str(item.get("name", "")).strip().lower() == lower_name:
				return False

		items.append(
			{
				"name": normalized_name,
				"price": float(price),
				"probability": int(probability),
			}
		)
		self._config["items"] = items
		self._save()
		return True

	def remove_item(self, name: str) -> bool:
		normalized_name = str(name).strip().lower()
		if not normalized_name:
			return False

		items = self.list_items()
		new_items = [
			item
			for item in items
			if str(item.get("name", "")).strip().lower() != normalized_name
		]
		if len(new_items) == len(items):
			return False

		self._config["items"] = new_items
		self._save()
		return True


class MineConfigManager:
	"""Cache en memoria por guild para config de mina."""

	def __init__(self):
		self._configs: dict[int, MineConfig] = {}

	def get_config(self, guild_id: int) -> MineConfig:
		guild_id = int(guild_id)
		if guild_id not in self._configs:
			self._configs[guild_id] = MineConfig(guild_id)
		return self._configs[guild_id]


_mine_config_manager: MineConfigManager | None = None


def get_mine_config(guild_id: int) -> MineConfig:
	global _mine_config_manager
	if _mine_config_manager is None:
		_mine_config_manager = MineConfigManager()
	return _mine_config_manager.get_config(guild_id)
