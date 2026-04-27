"""
Sistema de códigos recompensables para YouTube live.

- Lee catálogo de códigos desde JSON.
- Muestra códigos por WebSocket en notifications.html.
- Gestiona pendientes con expiración.
- Permite canje por comando !code en chat de YouTube.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from backend.managers.economy_manager import award_youtube_bonus_points
from backend.managers.economy_manager import get_common_fund_balance
from backend.services.events_websocket.general import send_update


logger = logging.getLogger(__name__)


DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "activities"
CODES_FILE = DATA_DIR / "codes_catalog.json"
CONFIG_FILE = DATA_DIR / "codes_config.json"
PENDING_FILE = DATA_DIR / "codes_pending.json"


DEFAULT_CODES = [
	{"code": "pow3r5t", "points": 15, "enabled": True},
	{"code": "dnsgaming", "points": 20, "enabled": True},
	{"code": "botb0t", "points": 25, "enabled": True},
]

DEFAULT_CONFIG = {
	"spawn_interval_seconds": 600,
	"display_duration_seconds": 90,
	"redeem_ttl_seconds": 120,
	"blink_start_seconds": 30,
	"frontend_style": {
		"font_size_px": 34,
		"opacity": 0.72,
	},
}

_state_lock = asyncio.Lock()
_scheduler_task: asyncio.Task | None = None
_scheduler_stop_event: asyncio.Event | None = None
_scheduler_live_chat_id: str | None = None


def _utcnow() -> datetime:
	return datetime.now(timezone.utc)


def _to_iso(value: datetime) -> str:
	return value.astimezone(timezone.utc).isoformat()


def _from_iso(value: str | None) -> datetime | None:
	if not value:
		return None
	try:
		parsed = datetime.fromisoformat(str(value))
		if parsed.tzinfo is None:
			parsed = parsed.replace(tzinfo=timezone.utc)
		return parsed.astimezone(timezone.utc)
	except Exception:
		return None


def _normalize_code(value: str) -> str:
	return str(value or "").strip().lower()


def _read_json(path: Path, fallback: Any) -> Any:
	try:
		with path.open("r", encoding="utf-8") as handle:
			return json.load(handle)
	except Exception:
		return fallback


def _write_json(path: Path, payload: Any) -> None:
	DATA_DIR.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8") as handle:
		json.dump(payload, handle, ensure_ascii=False, indent=2)


def _ensure_files() -> None:
	DATA_DIR.mkdir(parents=True, exist_ok=True)

	if not CODES_FILE.exists():
		_write_json(CODES_FILE, {"codes": DEFAULT_CODES})

	if not CONFIG_FILE.exists():
		_write_json(CONFIG_FILE, DEFAULT_CONFIG)

	if not PENDING_FILE.exists():
		_write_json(PENDING_FILE, {"last_spawn_at": None, "items": []})


def _load_config() -> Dict[str, Any]:
	_ensure_files()
	raw = _read_json(CONFIG_FILE, {}) or {}
	config = {
		**DEFAULT_CONFIG,
		**raw,
	}
	style = {
		**DEFAULT_CONFIG.get("frontend_style", {}),
		**(raw.get("frontend_style", {}) if isinstance(raw, dict) else {}),
	}
	config["frontend_style"] = style

	config["spawn_interval_seconds"] = max(30, int(config.get("spawn_interval_seconds", 600) or 600))
	config["display_duration_seconds"] = max(10, int(config.get("display_duration_seconds", 90) or 90))
	config["redeem_ttl_seconds"] = max(
		config["display_duration_seconds"],
		int(config.get("redeem_ttl_seconds", 120) or 120),
	)
	config["blink_start_seconds"] = max(5, int(config.get("blink_start_seconds", 30) or 30))
	style["font_size_px"] = max(18, int(style.get("font_size_px", 34) or 34))
	style["opacity"] = max(0.2, min(float(style.get("opacity", 0.72) or 0.72), 1.0))
	return config


def _load_catalog() -> List[Dict[str, Any]]:
	_ensure_files()
	raw = _read_json(CODES_FILE, {}) or {}
	entries = raw.get("codes", []) if isinstance(raw, dict) else []
	clean: List[Dict[str, Any]] = []

	for entry in entries:
		if isinstance(entry, list) and len(entry) >= 2:
			entry = {"code": entry[0], "points": entry[1]}
		if not isinstance(entry, dict):
			continue

		code = _normalize_code(entry.get("code"))
		if not code:
			continue

		try:
			points = int(entry.get("points", 0))
		except Exception:
			points = 0

		if points <= 0:
			continue

		enabled = bool(entry.get("enabled", True))
		if not enabled:
			continue

		clean.append({"code": code, "points": points, "enabled": True})

	return clean


def _load_pending_state() -> Dict[str, Any]:
	_ensure_files()
	raw = _read_json(PENDING_FILE, {}) or {}
	items = raw.get("items", []) if isinstance(raw, dict) else []
	if not isinstance(items, list):
		items = []
	return {
		"last_spawn_at": raw.get("last_spawn_at") if isinstance(raw, dict) else None,
		"items": items,
	}


def _save_pending_state(state: Dict[str, Any]) -> None:
	_write_json(PENDING_FILE, state)


def _prune_expired_items(state: Dict[str, Any], now: datetime) -> bool:
	items = state.get("items", [])
	kept = []
	changed = False
	for item in items:
		expires_at = _from_iso(item.get("expires_at"))
		if expires_at and expires_at > now:
			kept.append(item)
		else:
			changed = True
	state["items"] = kept
	return changed


async def _emit_show_code(code: str, config: Dict[str, Any]) -> bool:
	payload = {
		"type": "show_code",
		"code": code,
		"duration": int(config.get("display_duration_seconds", 90)),
		"blink_start": int(config.get("blink_start_seconds", 30)),
		"style": config.get("frontend_style", {}),
	}
	return await send_update(payload)


def _build_pending_entry(selected: Dict[str, Any], config: Dict[str, Any], now: datetime, live_chat_id: str) -> Dict[str, Any]:
	display_seconds = int(config.get("display_duration_seconds", 90))
	ttl_seconds = int(config.get("redeem_ttl_seconds", 120))
	entry_id = str(uuid4())
	return {
		"id": entry_id,
		"code": selected["code"],
		"points": int(selected["points"]),
		"created_at": _to_iso(now),
		"visible_until": _to_iso(now + timedelta(seconds=display_seconds)),
		"expires_at": _to_iso(now + timedelta(seconds=ttl_seconds)),
		"live_chat_id": str(live_chat_id),
	}


async def _spawn_random_code_internal(live_chat_id: str, force: bool = False) -> Dict[str, Any]:
	now = _utcnow()
	entry: Dict[str, Any] | None = None
	config: Dict[str, Any] | None = None

	async with _state_lock:
		config = _load_config()
		catalog = _load_catalog()
		if not catalog:
			return {"status": "skipped", "reason": "empty_catalog"}

		common_fund_balance = float(get_common_fund_balance() or 0.0)
		if common_fund_balance <= 0:
			return {
				"status": "skipped",
				"reason": "common_fund_empty",
				"common_fund_balance": common_fund_balance,
			}

		state = _load_pending_state()
		state_changed = _prune_expired_items(state, now)
		pending_items = state.get("items", [])
		if pending_items:
			if state_changed:
				_save_pending_state(state)
			return {
				"status": "skipped",
				"reason": "pending_exists",
				"pending_code": pending_items[0].get("code"),
			}

		last_spawn_at = _from_iso(state.get("last_spawn_at"))
		interval_seconds = int(config.get("spawn_interval_seconds", 600))
		if not force and last_spawn_at and (now - last_spawn_at).total_seconds() < interval_seconds:
			if state_changed:
				_save_pending_state(state)
			return {"status": "skipped", "reason": "interval_not_elapsed"}

		selected = random.choice(catalog)
		entry = _build_pending_entry(selected, config, now, live_chat_id)
		state["items"] = [entry]
		state["last_spawn_at"] = _to_iso(now)
		_save_pending_state(state)

	assert entry is not None
	assert config is not None
	await _emit_show_code(entry["code"], config)
	logger.info("🎁 Código publicado: %s (%s puntos)", entry["code"], entry["points"])
	return {
		"status": "spawned",
		"code": entry["code"],
		"points": entry["points"],
		"expires_at": entry["expires_at"],
	}


async def _maybe_spawn_code(live_chat_id: str) -> None:
	await _spawn_random_code_internal(live_chat_id, force=False)


async def spawn_random_code_now(live_chat_id: str) -> Dict[str, Any]:
	"""Publica un código random manualmente usando la misma lógica de generación.

	- Usa el mismo catálogo/config/persistencia que el scheduler.
	- Respeta que solo exista un pendiente activo al mismo tiempo.
	- Fuerza spawn inmediato (sin esperar intervalo de 10 minutos).
	"""
	return await _spawn_random_code_internal(live_chat_id, force=True)


async def start_codes_scheduler(live_chat_id: str) -> None:
	"""Inicia el scheduler de códigos para el live chat activo."""
	global _scheduler_task, _scheduler_stop_event, _scheduler_live_chat_id

	if _scheduler_task and not _scheduler_task.done():
		if _scheduler_live_chat_id == str(live_chat_id):
			return
		await stop_codes_scheduler()

	_scheduler_live_chat_id = str(live_chat_id)
	_scheduler_stop_event = asyncio.Event()

	async def _runner() -> None:
		assert _scheduler_stop_event is not None
		while not _scheduler_stop_event.is_set():
			try:
				await _maybe_spawn_code(_scheduler_live_chat_id or "")
			except Exception as exc:
				logger.error("Error en scheduler de códigos: %s", exc)

			try:
				await asyncio.wait_for(_scheduler_stop_event.wait(), timeout=5.0)
			except asyncio.TimeoutError:
				continue

	_scheduler_task = asyncio.create_task(_runner())
	logger.info("✅ Scheduler de códigos iniciado para chat %s", _scheduler_live_chat_id)


async def stop_codes_scheduler() -> None:
	"""Detiene el scheduler de códigos activo."""
	global _scheduler_task, _scheduler_stop_event, _scheduler_live_chat_id

	if _scheduler_stop_event is not None:
		_scheduler_stop_event.set()

	if _scheduler_task is not None:
		try:
			await _scheduler_task
		except Exception:
			pass

	_scheduler_task = None
	_scheduler_stop_event = None
	_scheduler_live_chat_id = None


async def redeem_code(
	code_input: str,
	youtube_channel_id: str,
	live_chat_id: str,
	message_id: str | None = None,
) -> Dict[str, Any]:
	"""Intenta canjear un código activo.

	Retorna:
	- status=invalid: código no existe/expiró
	- status=redeemed: canje exitoso
	- status=error: hubo fallo al otorgar puntos
	"""
	now = _utcnow()
	provided = _normalize_code(code_input)
	if not provided:
		return {"status": "invalid"}

	async with _state_lock:
		state = _load_pending_state()
		changed = _prune_expired_items(state, now)
		items = state.get("items", [])

		match_index = -1
		matched_item: Dict[str, Any] | None = None
		for index, item in enumerate(items):
			if _normalize_code(item.get("code")) == provided:
				match_index = index
				matched_item = item
				break

		if not matched_item:
			if changed:
				_save_pending_state(state)
			return {"status": "invalid"}

		reward_points = int(matched_item.get("points") or 0)
		if reward_points <= 0:
			return {"status": "invalid"}

		source_id = f"redeem_code:{matched_item.get('id')}:{message_id or provided}"
		award_result = award_youtube_bonus_points(
			youtube_channel_id=str(youtube_channel_id),
			chat_id=str(live_chat_id),
			amount=float(reward_points),
			source_id=source_id,
			reason="code_redeem",
		)

		if not award_result.get("awarded"):
			return {
				"status": "error",
				"reason": award_result.get("reason", "award_failed"),
			}

		items.pop(match_index)
		state["items"] = items
		_save_pending_state(state)

	await send_update({"type": "code_redeemed", "code": provided})
	return {
		"status": "redeemed",
		"code": provided,
		"points": reward_points,
		"global_points": award_result.get("global_points"),
	}
