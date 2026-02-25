"""
Configuracion local para juegos (limites y cooldowns).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "activities"
CONFIG_FILE = DATA_DIR / "games_config.json"


DEFAULT_CONFIG = {
	"gamble": {"min_limit": 0.0, "max_limit": 0.0, "cooldown": 0},
	"slots": {"min_limit": 0.0, "max_limit": 0.0, "cooldown": 0},
}


def _load_config() -> Dict[str, Dict[str, float]]:
	if not CONFIG_FILE.exists():
		return DEFAULT_CONFIG.copy()
	try:
		with CONFIG_FILE.open("r", encoding="utf-8") as handle:
			data = json.load(handle)
		return {**DEFAULT_CONFIG, **data}
	except (json.JSONDecodeError, OSError):
		return DEFAULT_CONFIG.copy()


def _save_config(config: Dict[str, Dict[str, float]]) -> None:
	DATA_DIR.mkdir(parents=True, exist_ok=True)
	with CONFIG_FILE.open("w", encoding="utf-8") as handle:
		json.dump(config, handle, indent=2, ensure_ascii=False)


def set_gamble_config(min_limit: float, max_limit: float, cooldown: int) -> Dict[str, float]:
	config = _load_config()
	config["gamble"] = {
		"min_limit": float(min_limit or 0.0),
		"max_limit": float(max_limit or 0.0),
		"cooldown": int(cooldown),
	}
	_save_config(config)
	return config["gamble"].copy()


def set_slots_config(min_limit: float, max_limit: float, cooldown: int) -> Dict[str, float]:
	config = _load_config()
	config["slots"] = {
		"min_limit": float(min_limit or 0.0),
		"max_limit": float(max_limit or 0.0),
		"cooldown": int(cooldown),
	}
	_save_config(config)
	return config["slots"].copy()


def get_gamble_config() -> Dict[str, float]:
	config = _load_config().get("gamble", DEFAULT_CONFIG["gamble"]).copy()
	# Compatibilidad con formato antiguo donde solo existia "limit"
	if "limit" in config and "max_limit" not in config:
		config["max_limit"] = float(config.pop("limit") or 0.0)
	if "min_limit" not in config:
		config["min_limit"] = 0.0
	if "cooldown" not in config:
		config["cooldown"] = 0
	return config


def get_slots_config() -> Dict[str, float]:
	config = _load_config().get("slots", DEFAULT_CONFIG["slots"]).copy()
	# Compatibilidad con formato antiguo donde solo existia "limit"
	if "limit" in config and "max_limit" not in config:
		config["max_limit"] = float(config.pop("limit") or 0.0)
	if "min_limit" not in config:
		config["min_limit"] = 0.0
	if "cooldown" not in config:
		config["cooldown"] = 0
	return config
