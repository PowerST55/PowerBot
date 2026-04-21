"""Configuracion global de recargas automaticas para casino y mina.

Se almacena en data/activities/recharge_config.json para poder ajustar
montos, ratios y tiempos sin tocar el codigo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "activities"
CONFIG_FILE = DATA_DIR / "recharge_config.json"


DEFAULT_CONFIG = {
	"casino": {
		"reload_interval_seconds": 12 * 60 * 60,
		"reload_target": 2500.0,
		"partial_reload_ratio": 0.15,
	},
	"mine": {
		"reload_interval_seconds": 12 * 60 * 60,
		"reload_target": 2500.0,
		"partial_reload_ratio": 0.15,
	},
}


def _normalize_section(data: Any, defaults: dict[str, float]) -> dict[str, float]:
	section = data if isinstance(data, dict) else {}
	return {
		"reload_interval_seconds": max(
			0,
			int(section.get("reload_interval_seconds", defaults["reload_interval_seconds"]) or defaults["reload_interval_seconds"]),
		),
		"reload_target": max(
			0.0,
			float(section.get("reload_target", defaults["reload_target"]) or defaults["reload_target"]),
		),
		"partial_reload_ratio": max(
			0.0,
			float(section.get("partial_reload_ratio", defaults["partial_reload_ratio"]) or defaults["partial_reload_ratio"]),
		),
	}


def _default_config() -> dict[str, dict[str, float]]:
	return {
		"casino": DEFAULT_CONFIG["casino"].copy(),
		"mine": DEFAULT_CONFIG["mine"].copy(),
	}


def _save_config(config: dict[str, dict[str, float]]) -> None:
	DATA_DIR.mkdir(parents=True, exist_ok=True)
	with CONFIG_FILE.open("w", encoding="utf-8") as handle:
		json.dump(config, handle, indent=2, ensure_ascii=False)


def _load_config() -> dict[str, dict[str, float]]:
	default_config = _default_config()
	if not CONFIG_FILE.exists():
		_save_config(default_config)
		return default_config

	try:
		with CONFIG_FILE.open("r", encoding="utf-8") as handle:
			data = json.load(handle)
		if not isinstance(data, dict):
			data = {}
		normalized = {
			"casino": _normalize_section(data.get("casino"), default_config["casino"]),
			"mine": _normalize_section(data.get("mine"), default_config["mine"]),
		}
		normalized_changed = normalized != data
		if normalized_changed:
			_save_config(normalized)
		return normalized
	except (OSError, json.JSONDecodeError, TypeError, ValueError):
		_save_config(default_config)
		return default_config


def ensure_recharge_config_file() -> Path:
	"""Garantiza que exista el JSON editable y devuelve su ruta."""
	_load_config()
	return CONFIG_FILE


def get_casino_recharge_config() -> dict[str, float]:
	return _load_config()["casino"].copy()


def get_mine_recharge_config() -> dict[str, float]:
	return _load_config()["mine"].copy()


def get_reload_interval_seconds(target: str) -> int:
	config = get_casino_recharge_config() if str(target).strip().lower() == "casino" else get_mine_recharge_config()
	return int(config["reload_interval_seconds"])


def calculate_reload_amount(target: str, common_fund_balance: float) -> float:
	config = get_casino_recharge_config() if str(target).strip().lower() == "casino" else get_mine_recharge_config()
	common_fund_value = float(common_fund_balance or 0.0)
	if common_fund_value <= 0:
		return 0.0
	if common_fund_value >= float(config["reload_target"]):
		return float(config["reload_target"])
	return round(common_fund_value * float(config["partial_reload_ratio"]), 2)
