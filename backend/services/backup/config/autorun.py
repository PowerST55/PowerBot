"""
Backup autorun config manager.
Gestiona el arranque automático persistente del servicio backup.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class BackupAutorunConfigManager:
	"""Gestiona la persistencia de autorun del servicio backup."""

	def __init__(self, data_dir: Optional[Path] = None):
		if data_dir is None:
			backend_dir = Path(__file__).resolve().parents[3]
			data_dir = backend_dir / "data" / "backup"

		self.data_dir = Path(data_dir)
		self.data_dir.mkdir(parents=True, exist_ok=True)
		self.config_file = self.data_dir / "autorun.json"

	def _default_config(self) -> dict:
		return {
			"autorun": False,
			"last_updated": datetime.utcnow().isoformat(),
		}

	def load_config(self) -> dict:
		"""Carga configuración persistida, con fallback por defecto."""
		try:
			if self.config_file.exists():
				with open(self.config_file, "r", encoding="utf-8") as file:
					data = json.load(file)
					if isinstance(data, dict):
						return {
							"autorun": bool(data.get("autorun", False)),
							"last_updated": data.get("last_updated", datetime.utcnow().isoformat()),
						}
		except Exception as exc:
			logger.error(f"Error cargando autorun backup: {exc}")

		return self._default_config()

	def save_config(self, autorun: bool) -> None:
		"""Guarda el estado de autorun del servicio backup."""
		payload = {
			"autorun": bool(autorun),
			"last_updated": datetime.utcnow().isoformat(),
		}

		try:
			with open(self.config_file, "w", encoding="utf-8") as file:
				json.dump(payload, file, indent=2, ensure_ascii=False)
		except Exception as exc:
			logger.error(f"Error guardando autorun backup: {exc}")

	def is_enabled(self) -> bool:
		"""Indica si autorun está en ON."""
		return bool(self.load_config().get("autorun", False))

	def set_enabled(self, enabled: bool) -> None:
		"""Actualiza y persiste el estado de autorun."""
		self.save_config(bool(enabled))

	def toggle(self) -> bool:
		"""Alterna y persiste autorun. Retorna el nuevo estado."""
		new_state = not self.is_enabled()
		self.set_enabled(new_state)
		return new_state

	def get_status(self) -> dict:
		cfg = self.load_config()
		cfg["config_file"] = str(self.config_file)
		return cfg


def create_backup_autorun_manager() -> BackupAutorunConfigManager:
	"""Factory de conveniencia para manager de autorun backup."""
	return BackupAutorunConfigManager()

