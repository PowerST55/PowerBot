"""
Store manager para PowerBot.
Lee catálogo desde assets/store y calcula precios por usuario con impuesto al patrimonio (ip%).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.managers.economy_manager import get_user_balance_by_id


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_STORE = PROJECT_ROOT / "assets" / "store"


_STORE_ITEMS_BY_KEY: Dict[str, Dict[str, Any]] = {}
_LAST_SYNC_AT: Optional[str] = None
_LAST_SYNC_RESULT: Dict[str, Any] = {
	"total": 0,
	"loaded": 0,
	"invalid": 0,
	"errors": [],
}
_LOCK = threading.Lock()


def _normalize_item_key(item_folder: Path, cfg: Dict[str, Any]) -> str:
	raw_key = str(cfg.get("item_key") or item_folder.name).strip()
	if not raw_key:
		raw_key = item_folder.name
	return raw_key


def _parse_percent(raw: Any, default: float = 0.0) -> float:
	if raw is None:
		return float(default)

	if isinstance(raw, str):
		clean = raw.strip().replace("%", "")
		if not clean:
			return float(default)
		try:
			return float(clean)
		except ValueError:
			return float(default)

	try:
		return float(raw)
	except Exception:
		return float(default)


def _find_media_file(item_folder: Path, kind: str, cfg: Dict[str, Any]) -> Optional[Path]:
	configured = cfg.get(kind)
	if isinstance(configured, str) and configured.strip():
		candidate = item_folder / configured.strip()
		if candidate.exists() and candidate.is_file():
			return candidate

	search_map: Dict[str, tuple[List[str], List[str]]] = {
		"thumbnail": (
			["thumbnail", "thumb", "image", "icon"],
			[".png", ".jpg", ".jpeg", ".webp", ".gif"],
		),
		"video": (
			["video", "preview", "clip"],
			[".mp4", ".webm", ".mov", ".mkv"],
		),
		"audio": (
			["audio", "sound", "sfx", "preview"],
			[".mp3", ".wav", ".ogg", ".m4a", ".flac"],
		),
	}

	names, exts = search_map[kind]
	for name in names:
		for ext in exts:
			candidate = item_folder / f"{name}{ext}"
			if candidate.exists() and candidate.is_file():
				return candidate

	return None


def _to_rel(path: Path) -> str:
	try:
		return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
	except Exception:
		return str(path).replace("\\", "/")


def _load_item_config(item_folder: Path) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
	config_file = item_folder / "config.json"
	if not config_file.exists():
		return None, f"{item_folder.name}: falta config.json"

	try:
		with open(config_file, "r", encoding="utf-8") as file:
			cfg = json.load(file)
	except Exception as exc:
		return None, f"{item_folder.name}: JSON inválido ({exc})"

	if not isinstance(cfg, dict):
		return None, f"{item_folder.name}: config.json debe ser objeto"

	item_key = _normalize_item_key(item_folder, cfg)
	base_price = cfg.get("base_price", cfg.get("precio_base", 0))
	try:
		base_price = float(base_price)
	except Exception:
		return None, f"{item_key}: base_price inválido"

	if base_price < 0:
		return None, f"{item_key}: base_price no puede ser negativo"

	ip_percent = _parse_percent(cfg.get("ip%", cfg.get("ip_percent", 0.0)), default=0.0)
	if ip_percent < 0:
		return None, f"{item_key}: ip% no puede ser negativo"

	thumbnail_path = _find_media_file(item_folder, "thumbnail", cfg)
	video_path = _find_media_file(item_folder, "video", cfg)
	audio_path = _find_media_file(item_folder, "audio", cfg)

	if not thumbnail_path:
		return None, f"{item_key}: falta thumbnail"
	if not video_path:
		return None, f"{item_key}: falta video"
	if not audio_path:
		return None, f"{item_key}: falta audio"

	item: Dict[str, Any] = {
		"item_key": item_key,
		"nombre": str(cfg.get("nombre") or item_key),
		"descripcion": str(cfg.get("descripcion") or ""),
		"base_price": round(base_price, 2),
		"ip%": round(ip_percent, 4),
		"ip_percent": round(ip_percent, 4),
		"thumbnail": _to_rel(thumbnail_path),
		"video": _to_rel(video_path),
		"audio": _to_rel(audio_path),
		"asset_folder": _to_rel(item_folder),
		"config_file": _to_rel(config_file),
		"metadata": cfg.get("metadata") if isinstance(cfg.get("metadata"), dict) else {},
	}

	return item, None


def refresh_store_items() -> Dict[str, Any]:
	"""Sincroniza catálogo store desde assets/store y actualiza caché en memoria."""
	global _LAST_SYNC_AT, _LAST_SYNC_RESULT

	ASSETS_STORE.mkdir(parents=True, exist_ok=True)
	errors: List[str] = []
	loaded: Dict[str, Dict[str, Any]] = {}

	item_folders = [folder for folder in ASSETS_STORE.iterdir() if folder.is_dir()]
	for item_folder in item_folders:
		item, error = _load_item_config(item_folder)
		if error:
			errors.append(error)
			continue
		if item:
			loaded[item["item_key"]] = item

	result = {
		"total": len(item_folders),
		"loaded": len(loaded),
		"invalid": len(errors),
		"errors": errors,
	}

	with _LOCK:
		_STORE_ITEMS_BY_KEY.clear()
		_STORE_ITEMS_BY_KEY.update(loaded)
		_LAST_SYNC_AT = datetime.utcnow().isoformat()
		_LAST_SYNC_RESULT = result

	return result.copy()


def _ensure_cache() -> None:
	with _LOCK:
		is_empty = len(_STORE_ITEMS_BY_KEY) == 0
	if is_empty:
		refresh_store_items()


def get_store_item(item_key: str) -> Optional[Dict[str, Any]]:
	"""Retorna item de tienda por item_key."""
	_ensure_cache()
	with _LOCK:
		item = _STORE_ITEMS_BY_KEY.get(str(item_key).strip())
		return dict(item) if item else None


def get_store_items() -> List[Dict[str, Any]]:
	"""Retorna todos los items cargados en tienda."""
	_ensure_cache()
	with _LOCK:
		return [dict(item) for item in _STORE_ITEMS_BY_KEY.values()]


def calculate_user_price(item_key: str, user_id: int) -> Optional[Dict[str, Any]]:
	"""
	Calcula precio final de un item para un usuario.
	Regla: precio_final = base_price + (balance_usuario * ip% / 100).
	"""
	item = get_store_item(item_key)
	if not item:
		return None

	balance_info = get_user_balance_by_id(int(user_id))
	if not balance_info.get("user_exists"):
		user_balance = 0.0
	else:
		user_balance = float(balance_info.get("global_points", 0.0))

	base_price = float(item.get("base_price", 0.0))
	ip_percent = float(item.get("ip_percent", item.get("ip%", 0.0)))
	ip_amount = round(user_balance * (ip_percent / 100.0), 2)
	final_price = round(base_price + ip_amount, 2)

	return {
		"item_key": item.get("item_key"),
		"base_price": round(base_price, 2),
		"ip%": round(ip_percent, 4),
		"ip_percent": round(ip_percent, 4),
		"user_balance": round(user_balance, 2),
		"ip_amount": ip_amount,
		"final_price": final_price,
	}


def get_user_store_catalog(user_id: int) -> List[Dict[str, Any]]:
	"""Retorna catálogo store con precio final calculado por usuario."""
	items = get_store_items()
	catalog: List[Dict[str, Any]] = []
	for item in items:
		pricing = calculate_user_price(item["item_key"], user_id)
		if not pricing:
			continue
		merged = dict(item)
		merged.update(
			{
				"user_balance": pricing["user_balance"],
				"ip_amount": pricing["ip_amount"],
				"final_price": pricing["final_price"],
			}
		)
		catalog.append(merged)
	return catalog


def get_store_stats() -> Dict[str, Any]:
	"""Retorna estado de caché y último resultado de sincronización."""
	_ensure_cache()
	with _LOCK:
		return {
			"cached_items": len(_STORE_ITEMS_BY_KEY),
			"last_sync_at": _LAST_SYNC_AT,
			"last_sync_result": dict(_LAST_SYNC_RESULT),
		}

