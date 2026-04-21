"""
Gestión de configuración de economía para YouTube (PowerBot).
Almacena datos en backend/data/youtube_bot/economy.json
"""

from pathlib import Path
from typing import Any, Dict
import json


class YouTubeEconomyConfig:
	"""Gestiona configuración de economía de YouTube."""

	def __init__(self, data_dir: Path | None = None):
		if data_dir is None:
			data_dir = Path(__file__).resolve().parents[3] / "data" / "youtube_bot"

		self.data_dir = data_dir
		self.config_file = self.data_dir / "economy.json"

		self._defaults = {
			"currency": {
				"name": "pews",
				"symbol": "💎",
			},
			"points": {
				"amount": 10,
				"interval": 300,
			},
			"earning": {
				"enabled": False,
			},
			"sync_source_guild_id": None,
		}

		self._config = self._load()

	def _load(self) -> Dict[str, Any]:
		"""Carga configuración desde JSON."""
		if self.config_file.exists():
			try:
				with open(self.config_file, "r", encoding="utf-8") as config_fp:
					loaded = json.load(config_fp)

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
				merged["sync_source_guild_id"] = loaded.get("sync_source_guild_id")
				return merged
			except Exception:
				return self._defaults.copy()

		return self._defaults.copy()

	def _save(self) -> None:
		"""Guarda configuración a JSON."""
		self.data_dir.mkdir(parents=True, exist_ok=True)
		with open(self.config_file, "w", encoding="utf-8") as config_fp:
			json.dump(self._config, config_fp, indent=2, ensure_ascii=False)

	def get_currency_name(self) -> str:
		"""Obtiene el nombre de la moneda configurada."""
		return self._config["currency"]["name"]

	def get_currency_symbol(self) -> str:
		"""Obtiene el símbolo de la moneda configurada."""
		return self._config["currency"]["symbol"]

	def set_currency(self, name: str, symbol: str) -> None:
		"""Actualiza nombre y símbolo de la moneda."""
		self._config["currency"]["name"] = name
		self._config["currency"]["symbol"] = symbol
		self._save()

	def get_points_amount(self) -> int:
		"""Obtiene la cantidad de puntos configurada."""
		return int(self._config["points"]["amount"])

	def get_points_interval(self) -> int:
		"""Obtiene el intervalo (segundos) configurado."""
		return int(self._config["points"]["interval"])

	def set_points(self, amount: int, interval: int) -> None:
		"""Actualiza cantidad e intervalo de puntos."""
		self._config["points"]["amount"] = int(amount)
		self._config["points"]["interval"] = int(interval)
		self._save()

	def is_earning_enabled(self) -> bool:
		"""Indica si la ganancia de puntos por chat está activada."""
		return bool(self._config.get("earning", {}).get("enabled", False))

	def set_earning_enabled(self, enabled: bool) -> None:
		"""Activa o desactiva la ganancia de puntos por chat."""
		self._config.setdefault("earning", {})
		self._config["earning"]["enabled"] = bool(enabled)
		self._save()

	def get_sync_source_guild_id(self) -> int | None:
		"""Guild de Discord usada como fuente para syncing de earning."""
		value = self._config.get("sync_source_guild_id")
		if value in (None, "", 0):
			return None
		try:
			return int(value)
		except Exception:
			return None

	def set_sync_source_guild_id(self, guild_id: int | None) -> None:
		"""Define la guild de Discord que gobierna el earning de YouTube."""
		self._config["sync_source_guild_id"] = None if guild_id is None else int(guild_id)
		self._save()


_youtube_economy_config: YouTubeEconomyConfig | None = None


def get_youtube_economy_config() -> YouTubeEconomyConfig:
	"""Obtiene instancia singleton de configuración económica de YouTube."""
	global _youtube_economy_config
	if _youtube_economy_config is None:
		_youtube_economy_config = YouTubeEconomyConfig()
	return _youtube_economy_config

