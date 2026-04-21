"""Toggle global para comandos administrativos de economía visibles al público."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _config_file() -> Path:
	backend_dir = Path(__file__).resolve().parents[3]
	return backend_dir / "data" / "common" / "admin_economy_toggle.json"


def _default_payload() -> dict:
	return {
		"admin_aps_enabled": True,
		"last_updated": datetime.utcnow().isoformat(),
	}


def load_admin_economy_toggle() -> dict:
	file_path = _config_file()
	if file_path.exists():
		try:
			with open(file_path, "r", encoding="utf-8") as file:
				data = json.load(file)
				if isinstance(data, dict):
					return {
						"admin_aps_enabled": bool(data.get("admin_aps_enabled", True)),
						"last_updated": str(data.get("last_updated") or datetime.utcnow().isoformat()),
					}
		except Exception:
			pass
	return _default_payload()


def save_admin_economy_toggle(enabled: bool) -> None:
	file_path = _config_file()
	file_path.parent.mkdir(parents=True, exist_ok=True)
	payload = {
		"admin_aps_enabled": bool(enabled),
		"last_updated": datetime.utcnow().isoformat(),
	}
	with open(file_path, "w", encoding="utf-8") as file:
		json.dump(payload, file, indent=2, ensure_ascii=False)


def is_admin_aps_enabled() -> bool:
	return bool(load_admin_economy_toggle().get("admin_aps_enabled", True))


def set_admin_aps_enabled(enabled: bool) -> None:
	save_admin_economy_toggle(bool(enabled))