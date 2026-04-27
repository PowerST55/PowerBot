"""Comando !code para canjear códigos recompensables en YouTube."""

from __future__ import annotations

from typing import List

from backend.services.activities.codes_master import redeem_code
from ...send_message import send_chat_message
from ...youtube_core import YouTubeClient
from ...youtube_listener import YouTubeMessage


CODE_COMMAND_ALIASES = {"code", "codigo"}


async def process_code_command(
	command: str,
	args: List[str],
	message: YouTubeMessage,
	client: YouTubeClient,
	live_chat_id: str,
) -> bool:
	"""Procesa !code <codigo>. Los intentos inválidos se ignoran sin respuesta."""
	if command not in CODE_COMMAND_ALIASES:
		return False

	if not args:
		# Silencioso para ahorrar cuota/API.
		return True

	code_input = " ".join(args).strip()
	if not code_input:
		return True

	result = await redeem_code(
		code_input=code_input,
		youtube_channel_id=message.author_channel_id,
		live_chat_id=live_chat_id,
		message_id=message.id,
	)

	status = result.get("status")
	if status == "redeemed":
		points = int(result.get("points") or 0)
		await send_chat_message(
			client,
			live_chat_id,
			f"✅ @{message.author_name} canjeó el código y ganó {points} puntos.",
		)
		return True

	if status == "error":
		reason = str(result.get("reason") or "").lower()
		if reason == "youtube_profile_not_found":
			await send_chat_message(
				client,
				live_chat_id,
				f"@{message.author_name}, primero vincula tu cuenta para recibir recompensas.",
			)
		elif reason == "common_fund_insufficient":
			await send_chat_message(
				client,
				live_chat_id,
				"⚠ No hay fondos suficientes en este momento para canjear el código.",
			)

	# Código inválido/expirado: no responder para ahorrar API.
	return True
