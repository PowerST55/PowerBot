"""
Gestión de whitelist para livefeed web.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


CONFIG_FILE = Path(__file__).resolve().parents[3] / "data" / "web" / "livefeed_ip_whitelist.json"


class LivefeedIPWhitelistManager:
	"""Maneja whitelist de IPs y última solicitud pendiente para livefeed."""

	def __init__(self, config_file: Path = CONFIG_FILE):
		self.config_file = config_file

	def _default(self) -> dict[str, Any]:
		return {
			"allowed_ips": [],
			"last_pending": None,
			"updated_at": datetime.utcnow().isoformat(),
		}

	def _load(self) -> dict[str, Any]:
		if self.config_file.exists():
			try:
				with self.config_file.open("r", encoding="utf-8") as handle:
					loaded = json.load(handle)
				cfg = self._default()
				cfg.update(loaded if isinstance(loaded, dict) else {})
				cfg["allowed_ips"] = [str(ip) for ip in cfg.get("allowed_ips", [])]
				return cfg
			except Exception:
				return self._default()
		return self._default()

	def _save(self, config: dict[str, Any]) -> None:
		self.config_file.parent.mkdir(parents=True, exist_ok=True)
		config["updated_at"] = datetime.utcnow().isoformat()
		with self.config_file.open("w", encoding="utf-8") as handle:
			json.dump(config, handle, indent=2, ensure_ascii=False)

	def is_allowed(self, ip: str) -> bool:
		cfg = self._load()
		return str(ip) in set(cfg.get("allowed_ips", []))

	def add_ip(self, ip: str) -> dict[str, Any]:
		cfg = self._load()
		allowed = set(cfg.get("allowed_ips", []))
		allowed.add(str(ip))
		cfg["allowed_ips"] = sorted(allowed)
		self._save(cfg)
		return cfg

	def remove_ip(self, ip: str) -> dict[str, Any]:
		cfg = self._load()
		allowed = set(cfg.get("allowed_ips", []))
		allowed.discard(str(ip))
		cfg["allowed_ips"] = sorted(allowed)
		self._save(cfg)
		return cfg

	def register_pending(self, ip: str, path: str) -> dict[str, Any]:
		cfg = self._load()
		cfg["last_pending"] = {
			"ip": str(ip),
			"path": str(path),
			"requested_at": datetime.utcnow().isoformat(),
		}
		self._save(cfg)
		return cfg

	def clear_pending(self) -> dict[str, Any]:
		cfg = self._load()
		cfg["last_pending"] = None
		self._save(cfg)
		return cfg

	def get_pending(self) -> Optional[dict[str, Any]]:
		cfg = self._load()
		pending = cfg.get("last_pending")
		return pending if isinstance(pending, dict) else None

	def allow_last_pending(self) -> Optional[dict[str, Any]]:
		cfg = self._load()
		pending = cfg.get("last_pending")
		if not isinstance(pending, dict):
			return None
		ip = str(pending.get("ip", "")).strip()
		if not ip:
			return None
		allowed = set(cfg.get("allowed_ips", []))
		allowed.add(ip)
		cfg["allowed_ips"] = sorted(allowed)
		cfg["last_pending"] = None
		self._save(cfg)
		return pending

	def deny_last_pending(self) -> Optional[dict[str, Any]]:
		cfg = self._load()
		pending = cfg.get("last_pending")
		if not isinstance(pending, dict):
			return None
		cfg["last_pending"] = None
		self._save(cfg)
		return pending

	def get_status(self) -> dict[str, Any]:
		cfg = self._load()
		return {
			"allowed_ips": list(cfg.get("allowed_ips", [])),
			"allowed_count": len(cfg.get("allowed_ips", [])),
			"last_pending": cfg.get("last_pending"),
			"config_file": str(self.config_file),
		}


_livefeed_ip_manager: LivefeedIPWhitelistManager | None = None


def create_livefeed_ip_manager() -> LivefeedIPWhitelistManager:
	global _livefeed_ip_manager
	if _livefeed_ip_manager is None:
		_livefeed_ip_manager = LivefeedIPWhitelistManager()
	return _livefeed_ip_manager

