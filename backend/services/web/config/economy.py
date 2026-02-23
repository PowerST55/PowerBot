"""
Web economy config manager.
Gestiona configuración de moneda/símbolo para la web.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class WebEconomyConfigManager:
	"""Gestiona la persistencia de economía para el módulo web."""

	def __init__(self, data_dir: Optional[Path] = None):
		if data_dir is None:
			backend_dir = Path(__file__).resolve().parents[3]
			data_dir = backend_dir / "data" / "web"

		self.data_dir = Path(data_dir)
		self.data_dir.mkdir(parents=True, exist_ok=True)
		self.config_file = self.data_dir / "economy.json"

	def _default_config(self) -> dict:
		return {
			"currency": {
				"name": "pews",
				"symbol": "💎",
			}
		}

	def load_config(self) -> dict:
		"""Carga la configuración de economía con fallback por defecto."""
		try:
			if self.config_file.exists():
				with open(self.config_file, "r", encoding="utf-8") as file:
					loaded = json.load(file)

				if isinstance(loaded, dict):
					merged = self._default_config()
					if isinstance(loaded.get("currency"), dict):
						merged_currency = dict(merged["currency"])
						merged_currency.update(loaded.get("currency", {}))
						merged["currency"] = merged_currency
					return merged
		except Exception as exc:
			logger.error(f"Error cargando economy web: {exc}")

		return self._default_config()

	def save_config(self, payload: dict) -> None:
		"""Guarda configuración de economía web."""
		try:
			with open(self.config_file, "w", encoding="utf-8") as file:
				json.dump(payload, file, indent=2, ensure_ascii=False)
		except Exception as exc:
			logger.error(f"Error guardando economy web: {exc}")

	def get_currency_name(self) -> str:
		"""Obtiene el nombre de moneda configurado para web."""
		cfg = self.load_config()
		return str(cfg.get("currency", {}).get("name", "pews"))

	def get_currency_symbol(self) -> str:
		"""Obtiene el símbolo de moneda configurado para web."""
		cfg = self.load_config()
		return str(cfg.get("currency", {}).get("symbol", "💎"))

	def set_currency(self, name: str, symbol: str) -> None:
		"""Actualiza nombre y símbolo de moneda de la web."""
		name_value = str(name).strip()
		symbol_value = str(symbol).strip()

		if not name_value:
			name_value = "pews"
		if not symbol_value:
			symbol_value = "💎"

		payload = self.load_config()
		payload.setdefault("currency", {})
		payload["currency"]["name"] = name_value
		payload["currency"]["symbol"] = symbol_value
		self.save_config(payload)

	def get_currency(self) -> dict:
		"""Obtiene bloque completo de moneda web."""
		cfg = self.load_config()
		currency = cfg.get("currency", {})
		return {
			"name": str(currency.get("name", "pews")),
			"symbol": str(currency.get("symbol", "💎")),
			"config_file": str(self.config_file),
		}


def create_web_economy_manager() -> WebEconomyConfigManager:
	"""Factory de conveniencia para el manager de economía web."""
	return WebEconomyConfigManager()
