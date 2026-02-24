"""
Comandos de vinculación de cuentas para chat de YouTube.
"""

from __future__ import annotations

from typing import List

from backend.managers.link_manager import consume_youtube_link_code, unlink_from_youtube
from ..send_message import send_chat_message
from ..youtube_core import YouTubeClient
from ..youtube_listener import YouTubeMessage


async def process_link_command(
	command: str,
	args: List[str],
	message: YouTubeMessage,
	client: YouTubeClient,
	live_chat_id: str,
) -> bool:
	"""Procesa !vincular desde YouTube."""
	if command not in {"vincular", "desvincular"}:
		return False

	if command == "desvincular":
		result = unlink_from_youtube(str(message.author_channel_id))
		if not result.success:
			await send_chat_message(client, live_chat_id, f"❌ {result.message}")
			return True

		await send_chat_message(
			client,
			live_chat_id,
			"🔓 Cuenta desvinculada. YouTube conserva el saldo total acumulado y Discord quedó en 0.",
		)
		return True

	if not args:
		await send_chat_message(
			client,
			live_chat_id,
			"Para vincular tu cuenta primero usa /vincular en Discord y luego pega aquí: !vincular <codigo>",
		)
		return True

	code = str(args[0]).strip()
	if not code:
		await send_chat_message(
			client,
			live_chat_id,
			"Código inválido. Uso correcto: !vincular <codigo>",
		)
		return True

	result = consume_youtube_link_code(
		code=code,
		youtube_channel_id=str(message.author_channel_id),
		youtube_username=str(message.author_name),
		channel_avatar_url=message.profile_image_url,
	)

	if not result.success:
		await send_chat_message(client, live_chat_id, f"❌ {result.message}")
		return True

	await send_chat_message(
		client,
		live_chat_id,
		"✅ Cuenta vinculada correctamente con Discord. Tu saldo e inventario ya están unificados.",
	)
	return True
