"""
Store Core Service.
Contiene configuración on/off persistente y el servicio central de sincronización del catálogo store.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from backend.managers import store_manager

logger = logging.getLogger(__name__)


class StoreToggleConfigManager:
	"""Gestiona la persistencia del estado de encendido del servicio store."""

	def __init__(self, data_dir: Optional[Path] = None):
		if data_dir is None:
			backend_dir = Path(__file__).resolve().parents[2]
			data_dir = backend_dir / "data" / "store"

		self.data_dir = Path(data_dir)
		self.data_dir.mkdir(parents=True, exist_ok=True)
		self.config_file = self.data_dir / "toggle_on_off.json"

	def _default_config(self) -> dict:
		return {
			"store_enabled": False,
			"last_updated": datetime.utcnow().isoformat(),
			"status": "off",
		}

	def load_config(self) -> dict:
		"""Carga la configuración persistida, con fallback por defecto."""
		try:
			if self.config_file.exists():
				with open(self.config_file, "r", encoding="utf-8") as file:
					data = json.load(file)
					if isinstance(data, dict):
						enabled = bool(data.get("store_enabled", False))
						return {
							"store_enabled": enabled,
							"last_updated": data.get("last_updated", datetime.utcnow().isoformat()),
							"status": "on" if enabled else "off",
						}
		except Exception as exc:
			logger.error(f"Error cargando config store: {exc}")

		return self._default_config()

	def save_config(self, enabled: bool) -> None:
		"""Guarda el estado on/off del servicio store."""
		payload = {
			"store_enabled": bool(enabled),
			"last_updated": datetime.utcnow().isoformat(),
			"status": "on" if enabled else "off",
		}

		try:
			with open(self.config_file, "w", encoding="utf-8") as file:
				json.dump(payload, file, indent=2, ensure_ascii=False)
		except Exception as exc:
			logger.error(f"Error guardando config store: {exc}")

	def is_enabled(self) -> bool:
		"""Indica si la configuración persistida está en ON."""
		return bool(self.load_config().get("store_enabled", False))

	def set_enabled(self, enabled: bool) -> None:
		"""Actualiza y persiste el estado ON/OFF."""
		self.save_config(bool(enabled))

	def toggle(self) -> bool:
		"""Alterna y persiste el estado ON/OFF. Retorna el nuevo estado."""
		new_state = not self.is_enabled()
		self.set_enabled(new_state)
		return new_state

	def get_status(self) -> dict:
		"""Obtiene estado completo de la configuración store."""
		cfg = self.load_config()
		cfg["config_file"] = str(self.config_file)
		return cfg


def create_store_toggle_manager() -> StoreToggleConfigManager:
	"""Factory de conveniencia para el manager de toggle store."""
	return StoreToggleConfigManager()


class StoreService:
	"""Servicio central de store que sincroniza periódicamente el catálogo de assets."""

	def __init__(self, sync_interval_seconds: int = 120):
		self.sync_interval_seconds = max(10, int(sync_interval_seconds))
		self._running = False
		self._thread: threading.Thread | None = None
		self._stop_event = threading.Event()
		self._last_sync_at: Optional[str] = None
		self._last_sync_result: Dict[str, Any] = {
			"total": 0,
			"loaded": 0,
			"invalid": 0,
			"errors": [],
		}

	def _sync_once(self) -> Dict[str, Any]:
		result = store_manager.refresh_store_items()
		self._last_sync_result = result
		self._last_sync_at = datetime.utcnow().isoformat()
		return result

	def _loop(self) -> None:
		while not self._stop_event.is_set():
			try:
				self._sync_once()
			except Exception as exc:
				logger.error(f"StoreService sync error: {exc}")
			self._stop_event.wait(self.sync_interval_seconds)

	def start(self) -> tuple[bool, str]:
		if self._running:
			return True, "Store service ya está encendido"

		try:
			self._sync_once()
		except Exception as exc:
			self._running = False
			return False, f"Error sincronizando catálogo store: {exc}"

		self._stop_event.clear()
		self._thread = threading.Thread(target=self._loop, daemon=True, name="store-service-sync")
		self._thread.start()
		self._running = True
		return True, "Store service encendido"

	def stop(self) -> tuple[bool, str]:
		if not self._running:
			return True, "Store service ya está apagado"

		self._stop_event.set()
		if self._thread and self._thread.is_alive():
			self._thread.join(timeout=2)

		self._thread = None
		self._running = False
		return True, "Store service apagado"

	def force_sync(self) -> Dict[str, Any]:
		"""Ejecuta sincronización manual inmediata."""
		return self._sync_once()

	def is_running(self) -> bool:
		return bool(self._running)

	def get_status(self) -> Dict[str, Any]:
		stats = store_manager.get_store_stats()
		return {
			"running": self._running,
			"sync_interval_seconds": self.sync_interval_seconds,
			"last_sync_at": self._last_sync_at,
			"last_sync_result": self._last_sync_result,
			"manager_stats": stats,
		}


_store_service: StoreService | None = None


def get_store_service() -> StoreService:
	"""Obtiene singleton del servicio store."""
	global _store_service
	if _store_service is None:
		_store_service = StoreService()
	return _store_service


def start_store_service() -> tuple[bool, str]:
	"""Inicia el servicio store."""
	return get_store_service().start()


def stop_store_service() -> tuple[bool, str]:
	"""Detiene el servicio store."""
	return get_store_service().stop()

