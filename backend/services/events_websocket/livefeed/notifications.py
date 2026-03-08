from __future__ import annotations

from typing import Any, Dict

from ..general import send_update


async def send_notification(payload: Dict[str, Any], timeout: float = 3) -> bool:
	"""Envía un evento genérico de notificación al livefeed."""
	data = dict(payload or {})
	data.setdefault("type", "notification")
	return await send_update(data, timeout=timeout)


async def send_store_sound_notification(
	*,
	notification_id: str,
	internal_id: str | None = None,
	item_name: str | None = None,
	video_path: str,
	audio_path: str | None = None,
	title_text: str | None = None,
	message_text: str | None = None,
	simulation: bool = True,
	source: str = "console_ntf_store",
	timeout: float = 3,
) -> bool:
	"""Envía una notificación de compra/simulación para items store categoría sound."""
	payload: Dict[str, Any] = {
		"type": "notification",
		"notificationId": str(notification_id),
		"titleText": str(title_text or "Compra simulada"),
		"messageText": str(message_text or item_name or notification_id),
		"videoPath": str(video_path),
		"simulation": bool(simulation),
		"source": str(source),
	}

	if internal_id:
		payload["storeInternalId"] = str(internal_id)

	if audio_path:
		payload["audioPath"] = str(audio_path)

	return await send_update(payload, timeout=timeout)
