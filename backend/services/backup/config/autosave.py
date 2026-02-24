"""
Backup autosave config manager.
Gestiona el intervalo y estado del autosave persistente.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class BackupAutosaveConfigManager:
	"""Persistencia de configuración de autosave en data/backup."""

	def __init__(self, data_dir: Optional[Path] = None):
		if data_dir is None:
			backend_dir = Path(__file__).resolve().parents[3]
			data_dir = backend_dir / "data" / "backup"

		self.data_dir = Path(data_dir)
		self.data_dir.mkdir(parents=True, exist_ok=True)
		self.config_file = self.data_dir / "autosave.json"

	def _default_config(self) -> dict:
		return {
			"enabled": False,
			"interval_seconds": 3600,
			"last_run_at": None,
			"last_updated": datetime.utcnow().isoformat(),
			"last_cleanup_at": None,
		}

	def load_config(self) -> dict:
		try:
			if self.config_file.exists():
				with open(self.config_file, "r", encoding="utf-8") as file:
					data = json.load(file)
					if isinstance(data, dict):
						cfg = self._default_config()
						cfg.update(data)
						cfg["enabled"] = bool(cfg.get("enabled", False))
						try:
							cfg["interval_seconds"] = max(30, int(cfg.get("interval_seconds", 3600)))
						except Exception:
							cfg["interval_seconds"] = 3600
						return cfg
		except Exception as exc:
			logger.error(f"Error cargando config autosave backup: {exc}")

		return self._default_config()

	def save_config(self, config: dict) -> None:
		payload = self._default_config()
		payload.update(config or {})
		payload["enabled"] = bool(payload.get("enabled", False))
		payload["interval_seconds"] = max(30, int(payload.get("interval_seconds", 3600)))
		payload["last_updated"] = datetime.utcnow().isoformat()

		try:
			with open(self.config_file, "w", encoding="utf-8") as file:
				json.dump(payload, file, indent=2, ensure_ascii=False)
		except Exception as exc:
			logger.error(f"Error guardando config autosave backup: {exc}")

	def set_interval(self, interval_seconds: int) -> dict:
		cfg = self.load_config()
		cfg["interval_seconds"] = max(30, int(interval_seconds))
		cfg["enabled"] = True
		self.save_config(cfg)
		return self.load_config()

	def set_enabled(self, enabled: bool) -> dict:
		cfg = self.load_config()
		cfg["enabled"] = bool(enabled)
		self.save_config(cfg)
		return self.load_config()

	def set_last_run_now(self) -> dict:
		cfg = self.load_config()
		cfg["last_run_at"] = datetime.utcnow().isoformat()
		self.save_config(cfg)
		return self.load_config()

	def set_last_cleanup_now(self) -> dict:
		cfg = self.load_config()
		cfg["last_cleanup_at"] = datetime.utcnow().isoformat()
		self.save_config(cfg)
		return self.load_config()

	def get_status(self) -> dict:
		cfg = self.load_config()
		cfg["config_file"] = str(self.config_file)
		return cfg


def create_backup_autosave_manager() -> BackupAutosaveConfigManager:
	return BackupAutosaveConfigManager()

