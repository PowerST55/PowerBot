"""
Gestión persistida de autorun para el servidor WebSocket local.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any


CONFIG_FILE = Path(__file__).resolve().parents[3] / "data" / "events_websocket" / "settings.json"


DEFAULTS: Dict[str, Any] = {
	"enabled": False,
	"autorun": False,
	"host": "127.0.0.1",
	"port": 8765,
}


class WebSocketAutorunManager:
	"""Maneja configuración de inicio automático del websocket."""

	def __init__(self, config_file: Path = CONFIG_FILE):
		self.config_file = config_file

	def _load(self) -> Dict[str, Any]:
		if self.config_file.exists():
			try:
				with self.config_file.open("r", encoding="utf-8") as handle:
					loaded = json.load(handle)
				cfg = dict(DEFAULTS)
				cfg.update(loaded)
				return cfg
			except Exception:
				return dict(DEFAULTS)
		return dict(DEFAULTS)

	def _save(self, config: Dict[str, Any]) -> None:
		self.config_file.parent.mkdir(parents=True, exist_ok=True)
		with self.config_file.open("w", encoding="utf-8") as handle:
			json.dump(config, handle, indent=2, ensure_ascii=False)

	def is_enabled(self) -> bool:
		return bool(self._load().get("autorun", False))

	def set_enabled(self, enabled: bool) -> Dict[str, Any]:
		config = self._load()
		config["autorun"] = bool(enabled)
		self._save(config)
		return config

	def toggle(self) -> Dict[str, Any]:
		config = self._load()
		config["autorun"] = not bool(config.get("autorun", False))
		self._save(config)
		return config

	def get_status(self) -> Dict[str, Any]:
		config = self._load()
		return {
			"enabled": bool(config.get("enabled", False)),
			"autorun": bool(config.get("autorun", False)),
			"host": str(config.get("host", "127.0.0.1")),
			"port": int(config.get("port", 8765)),
			"config_file": str(self.config_file),
		}


_ws_autorun_manager: WebSocketAutorunManager | None = None


def create_websocket_autorun_manager() -> WebSocketAutorunManager:
	global _ws_autorun_manager
	if _ws_autorun_manager is None:
		_ws_autorun_manager = WebSocketAutorunManager()
	return _ws_autorun_manager

