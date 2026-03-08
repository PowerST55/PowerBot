"""Comandos de consola para probar notificaciones livefeed."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from backend.managers import store_manager
from backend.services.events_websocket import general as ws_general
from backend.services.events_websocket.livefeed import notifications as ws_notifications


def _normalize_store_identifier(raw: str) -> str:
	value = str(raw or "").strip()
	if not value:
		return ""
	if value.lower().startswith("id:"):
		value = value[3:]
	return value.strip()


def _normalize_store_category(item: Dict[str, Any]) -> str:
	metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
	raw = str(metadata.get("categoria") or metadata.get("category") or "sound").strip().lower()
	if raw in {"sound", "audio", "sfx"}:
		return "sound"
	if raw in {"card", "cards", "carrd"}:
		return "card"
	return raw


def _resolve_store_item_by_id(raw_identifier: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
	identifier = _normalize_store_identifier(raw_identifier)
	if not identifier:
		return None, "Debes indicar un ID de store. Ejemplo: ntf store s1"

	# Sincronizar primero para que pruebas reflejen el estado más reciente del catálogo.
	store_manager.refresh_store_items()
	items = store_manager.get_store_items()
	if not items:
		return None, "No hay items en store. Revisa assets/store y config.json"

	identifier_lower = identifier.lower()
	identifier_upper = identifier.upper()

	for item in items:
		item_internal_id = str(item.get("internal_id") or "").strip().upper()
		item_key = str(item.get("item_key") or "").strip().lower()
		if identifier_upper == item_internal_id or identifier_lower == item_key:
			return item, None

	return None, f"No existe item para '{identifier}'. Usa internal_id (S1) o item_key"


def _public_asset_url(asset_rel_or_abs: str | None) -> str:
	value = str(asset_rel_or_abs or "").strip()
	if not value:
		return ""

	lower = value.lower()
	if lower.startswith("http://") or lower.startswith("https://"):
		return value

	path = value.replace("\\", "/")
	if not path.startswith("/"):
		path = f"/{path}"

	host = os.getenv("WEB_HOST", "127.0.0.1").strip() or "127.0.0.1"
	if host in {"0.0.0.0", "::", "*"}:
		host = "127.0.0.1"
	port = os.getenv("WEB_PORT", "19131").strip() or "19131"
	scheme = os.getenv("WEB_SCHEME", "http").strip() or "http"
	return f"{scheme}://{host}:{port}{path}"


async def cmd_ntf(ctx: Any) -> None:
	"""
	Comandos para pruebas de notificaciones en livefeed.

	Uso:
	  ntf store <id>  -> simula compra de item sound y reproduce video en notifications.html
	"""
	action = str(ctx.args[0]).strip().lower() if ctx.args else "help"

	if action in {"help", "-h", "--help"}:
		ctx.print("Comandos ntf disponibles:")
		ctx.print("  ntf store <id> - Simula compra store (solo categoria sound)")
		ctx.print("                  ID puede ser internal_id (S1) o item_key")
		return

	if action != "store":
		ctx.error(f"Subcomando desconocido: 'ntf {action}'")
		ctx.print("Usa 'ntf help' para ver comandos disponibles")
		return

	if len(ctx.args) < 2:
		ctx.error("Uso: ntf store <id>")
		ctx.print("Ejemplo: ntf store s1")
		return

	if not ws_general.is_ws_endpoint_available():
		ctx.warning("WebSocket no disponible. Enciende primero con 'wsocket on' y verifica con 'wsocket status'.")
		return

	item, error = _resolve_store_item_by_id(ctx.args[1])
	if error:
		ctx.error(error)
		return

	assert item is not None
	item_key = str(item.get("item_key") or "").strip()
	internal_id = str(item.get("internal_id") or "").strip().upper()
	item_name = str(item.get("nombre") or item_key)
	category = _normalize_store_category(item)

	if category != "sound":
		ctx.warning(f"Item '{item_name}' ({internal_id or item_key}) no es categoria sound. Categoria detectada: {category}")
		ctx.print("Esta prueba solo admite items sound por ahora")
		return

	video_url = _public_asset_url(item.get("video"))
	audio_url = _public_asset_url(item.get("audio"))
	if not video_url:
		ctx.error(f"El item '{item_name}' no tiene video configurado")
		return

	ok = await ws_notifications.send_store_sound_notification(
		notification_id=item_key,
		internal_id=internal_id,
		item_name=item_name,
		video_path=video_url,
		audio_path=audio_url or None,
	)

	if not ok:
		ctx.error("No se pudo enviar la notificación por WebSocket")
		ctx.print("Verifica que el servidor web/livefeed este abierto y que /ws responda")
		return

	ctx.success(f"Notificación store simulada enviada: {internal_id or item_key} ({item_name})")
	ctx.print(f"Video enviado: {video_url}")
	if audio_url:
		ctx.print(f"Audio enviado: {audio_url}")
	ctx.print("Abre notifications.html en livefeed para ver la reproducción")
