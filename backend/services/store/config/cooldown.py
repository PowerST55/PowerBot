"""Persistencia de cooldowns de tienda (por usuario y global por item)."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class StoreCooldownConfigManager:
	"""Gestiona cooldown por item para compras de tienda.

	- cooldown normal: por usuario + item.
	- cooldown global: por item para todos los usuarios.
	"""

	def __init__(self, data_dir: Optional[Path] = None):
		if data_dir is None:
			backend_dir = Path(__file__).resolve().parents[3]
			data_dir = backend_dir / "data" / "store"

		self.data_dir = Path(data_dir)
		self.data_dir.mkdir(parents=True, exist_ok=True)
		self.config_file = self.data_dir / "cooldown.json"
		self._lock = threading.Lock()

	def _default_config(self) -> Dict[str, Any]:
		return {
			"user_cooldowns": {},
			"global_cooldowns": {},
			"last_updated": datetime.utcnow().isoformat(),
		}

	def _load(self) -> Dict[str, Any]:
		if not self.config_file.exists():
			return self._default_config()

		try:
			with open(self.config_file, "r", encoding="utf-8") as file:
				data = json.load(file)
			if not isinstance(data, dict):
				return self._default_config()

			user_cooldowns = data.get("user_cooldowns") if isinstance(data.get("user_cooldowns"), dict) else {}
			global_cooldowns = data.get("global_cooldowns") if isinstance(data.get("global_cooldowns"), dict) else {}

			return {
				"user_cooldowns": user_cooldowns,
				"global_cooldowns": global_cooldowns,
				"last_updated": data.get("last_updated", datetime.utcnow().isoformat()),
			}
		except Exception as exc:
			logger.error(f"Error cargando cooldown store: {exc}")
			return self._default_config()

	def _save(self, payload: Dict[str, Any]) -> None:
		payload["last_updated"] = datetime.utcnow().isoformat()
		try:
			with open(self.config_file, "w", encoding="utf-8") as file:
				json.dump(payload, file, indent=2, ensure_ascii=False)
		except Exception as exc:
			logger.error(f"Error guardando cooldown store: {exc}")

	@staticmethod
	def _remaining_seconds(expires_at: float, now_ts: float) -> int:
		remaining = int(round(float(expires_at) - float(now_ts)))
		return max(0, remaining)

	def cleanup_expired(self, now_ts: Optional[float] = None) -> None:
		"""Limpia cooldowns vencidos para mantener el archivo compacto."""
		now = float(now_ts if now_ts is not None else datetime.utcnow().timestamp())

		with self._lock:
			data = self._load()
			changed = False

			user_cooldowns = data.get("user_cooldowns", {})
			for item_key in list(user_cooldowns.keys()):
				users_map = user_cooldowns.get(item_key)
				if not isinstance(users_map, dict):
					user_cooldowns.pop(item_key, None)
					changed = True
					continue

				for user_id in list(users_map.keys()):
					try:
						expires_at = float(users_map[user_id])
					except Exception:
						users_map.pop(user_id, None)
						changed = True
						continue
					if expires_at <= now:
						users_map.pop(user_id, None)
						changed = True

				if not users_map:
					user_cooldowns.pop(item_key, None)
					changed = True

			global_cooldowns = data.get("global_cooldowns", {})
			for item_key in list(global_cooldowns.keys()):
				try:
					expires_at = float(global_cooldowns[item_key])
				except Exception:
					global_cooldowns.pop(item_key, None)
					changed = True
					continue
				if expires_at <= now:
					global_cooldowns.pop(item_key, None)
					changed = True

			if changed:
				data["user_cooldowns"] = user_cooldowns
				data["global_cooldowns"] = global_cooldowns
				self._save(data)

	def get_cooldown_status(self, item_key: str, user_id: int, now_ts: Optional[float] = None) -> Dict[str, Any]:
		"""Retorna estado de cooldown por usuario+item y global por item."""
		now = float(now_ts if now_ts is not None else datetime.utcnow().timestamp())
		key = str(item_key or "").strip()
		uid = str(int(user_id))

		with self._lock:
			data = self._load()
			user_cooldowns = data.get("user_cooldowns", {})
			global_cooldowns = data.get("global_cooldowns", {})

			user_expires_at = 0.0
			item_users = user_cooldowns.get(key)
			if isinstance(item_users, dict):
				try:
					user_expires_at = float(item_users.get(uid, 0.0) or 0.0)
				except Exception:
					user_expires_at = 0.0

			try:
				global_expires_at = float(global_cooldowns.get(key, 0.0) or 0.0)
			except Exception:
				global_expires_at = 0.0

		user_remaining = self._remaining_seconds(user_expires_at, now)
		global_remaining = self._remaining_seconds(global_expires_at, now)

		return {
			"item_key": key,
			"user_id": int(user_id),
			"user_remaining": user_remaining,
			"global_remaining": global_remaining,
			"blocked": (user_remaining > 0 or global_remaining > 0),
		}

	def register_purchase(
		self,
		*,
		item_key: str,
		user_id: int,
		user_cooldown_seconds: int,
		global_cooldown_seconds: int,
		now_ts: Optional[float] = None,
	) -> Dict[str, Any]:
		"""Aplica cooldowns de una compra confirmada para un item."""
		now = float(now_ts if now_ts is not None else datetime.utcnow().timestamp())
		key = str(item_key or "").strip()
		uid = str(int(user_id))
		user_seconds = max(0, int(user_cooldown_seconds or 0))
		global_seconds = max(0, int(global_cooldown_seconds or 0))

		with self._lock:
			data = self._load()
			user_cooldowns = data.get("user_cooldowns", {}) if isinstance(data.get("user_cooldowns"), dict) else {}
			global_cooldowns = data.get("global_cooldowns", {}) if isinstance(data.get("global_cooldowns"), dict) else {}

			if user_seconds > 0:
				item_users = user_cooldowns.get(key) if isinstance(user_cooldowns.get(key), dict) else {}
				item_users[uid] = now + user_seconds
				user_cooldowns[key] = item_users
			else:
				item_users = user_cooldowns.get(key)
				if isinstance(item_users, dict):
					item_users.pop(uid, None)
					if not item_users:
						user_cooldowns.pop(key, None)

			if global_seconds > 0:
				global_cooldowns[key] = now + global_seconds
			else:
				global_cooldowns.pop(key, None)

			data["user_cooldowns"] = user_cooldowns
			data["global_cooldowns"] = global_cooldowns
			self._save(data)

		self.cleanup_expired(now_ts=now)
		return self.get_cooldown_status(item_key=key, user_id=int(user_id), now_ts=now)

	def get_status(self) -> Dict[str, Any]:
		data = self._load()
		user_cooldowns = data.get("user_cooldowns", {})
		global_cooldowns = data.get("global_cooldowns", {})

		active_user = 0
		for item_users in user_cooldowns.values():
			if isinstance(item_users, dict):
				active_user += len(item_users)

		active_global = len(global_cooldowns) if isinstance(global_cooldowns, dict) else 0
		return {
			"config_file": str(self.config_file),
			"active_user_cooldowns": active_user,
			"active_global_cooldowns": active_global,
			"last_updated": data.get("last_updated"),
		}


def create_store_cooldown_manager() -> StoreCooldownConfigManager:
	"""Factory para manager de cooldown de store."""
	return StoreCooldownConfigManager()

