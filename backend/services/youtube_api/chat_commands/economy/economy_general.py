"""
Comandos de economía del chat de YouTube.
"""

import logging
from typing import List

from backend.managers.economy_manager import (
	get_user_balance_by_id,
	get_user_balance_by_youtube_id,
	transfer_points,
)
from backend.managers.user_lookup_manager import (
	find_user_by_global_id,
	find_user_by_youtube_channel_id,
	find_user_by_youtube_username,
)
from .economy_admin import process_admin_economy_command
from ...config.economy import get_youtube_economy_config
from ...send_message import send_chat_message
from ...youtube_core import YouTubeClient
from ...youtube_listener import YouTubeMessage

logger = logging.getLogger(__name__)


ECONOMY_COMMAND_ALIASES = {"puntos", "pews", "points", "balance", "pew"}
TRANSFER_COMMAND_ALIASES = {"dar", "depositar", "transferir", "give"}


def _format_points(points: float) -> str:
	config = get_youtube_economy_config()
	currency_name = config.get_currency_name()
	currency_symbol = config.get_currency_symbol()
	return f"{float(points):,.2f} {currency_symbol} {currency_name}".strip()


async def process_economy_command(
	command: str,
	args: List[str],
	message: YouTubeMessage,
	client: YouTubeClient,
	live_chat_id: str,
) -> bool:
	"""Procesa comandos de economía. Retorna True si se manejó el comando."""
	if await process_admin_economy_command(command, args, message, client, live_chat_id):
		return True

	if command in TRANSFER_COMMAND_ALIASES:
		if len(args) < 2:
			await send_chat_message(client, live_chat_id, "Uso: !dar <usuario o id> <cantidad>")
			return True

		sender = find_user_by_youtube_channel_id(message.author_channel_id)
		if not sender:
			await send_chat_message(
				client,
				live_chat_id,
				f"No encontré usuario vinculado para {message.author_name}.",
			)
			return True

		amount_raw = args[-1].strip()
		target_query = " ".join(args[:-1]).strip()

		if not target_query:
			await send_chat_message(client, live_chat_id, "Uso: !dar <usuario o id> <cantidad>")
			return True

		try:
			amount = round(float(amount_raw.replace(",", ".")), 2)
		except Exception:
			amount = 0

		if amount <= 0:
			await send_chat_message(client, live_chat_id, "La cantidad debe ser un número mayor a 0 (hasta 2 decimales).")
			return True

		if target_query.isdigit():
			target = find_user_by_global_id(int(target_query))
		else:
			target = find_user_by_youtube_username(target_query)
			if not target and target_query.startswith("UC"):
				target = find_user_by_youtube_channel_id(target_query)

		if not target:
			await send_chat_message(client, live_chat_id, f"No encontré al usuario '{target_query}'.")
			return True

		result = transfer_points(
			from_user_id=sender.user_id,
			to_user_id=target.user_id,
			amount=amount,
			guild_id=live_chat_id,
			platform="youtube",
		)

		if not result.get("success"):
			await send_chat_message(client, live_chat_id, result.get("error", "No se pudo realizar la transferencia."))
			return True

		to_name = target.youtube_profile.youtube_username if target.youtube_profile else target.display_name
		from_points = float(result.get("from_balance", 0) or 0)
		await send_chat_message(
			client,
			live_chat_id,
			f"✅ Transferidos {_format_points(amount)} a @{to_name}. Tu nuevo balance: {_format_points(from_points)}.",
		)
		return True

	if command not in ECONOMY_COMMAND_ALIASES:
		return False

	# Caso 1: !puntos -> self (autor del mensaje)
	if not args:
		lookup = find_user_by_youtube_channel_id(message.author_channel_id)
		if not lookup:
			await send_chat_message(
				client,
				live_chat_id,
				f"No encontré usuario vinculado para {message.author_name}.",
			)
			return True

		balance = get_user_balance_by_youtube_id(message.author_channel_id)
		points = balance.get("global_points", 0) if balance else 0
		await send_chat_message(
			client,
			live_chat_id,
			f"{message.author_name} tiene {_format_points(points)}.",
		)
		return True

	query = " ".join(args).strip()
	if not query:
		await send_chat_message(client, live_chat_id, "Uso: !puntos, !puntos <id> o !puntos <usuario>")
		return True

	# Caso 2: !puntos <id_universal>
	if query.isdigit():
		lookup = find_user_by_global_id(int(query))
		if not lookup:
			await send_chat_message(client, live_chat_id, f"No existe usuario con id {query}.")
			return True

		balance = get_user_balance_by_id(lookup.user_id)
		points = balance.get("global_points", 0) if balance else 0

		if lookup.discord_profile and lookup.discord_profile.discord_username:
			await send_chat_message(
				client,
				live_chat_id,
				f"El usuario @{lookup.discord_profile.discord_username} (discord) tiene {_format_points(points)}.",
			)
		elif lookup.youtube_profile and lookup.youtube_profile.youtube_username:
			await send_chat_message(
				client,
				live_chat_id,
				f"El usuario @{lookup.youtube_profile.youtube_username} tiene {_format_points(points)}.",
			)
		else:
			await send_chat_message(
				client,
				live_chat_id,
				f"El usuario con id {lookup.user_id} tiene {_format_points(points)}.",
			)
		return True

	# Caso 3: !puntos <@usuario> o !puntos <usuario>
	lookup = find_user_by_youtube_username(query)
	if not lookup and query.startswith("UC"):
		lookup = find_user_by_youtube_channel_id(query)

	if not lookup:
		await send_chat_message(client, live_chat_id, f"No encontré al usuario '{query}'.")
		return True

	balance = get_user_balance_by_id(lookup.user_id)
	points = balance.get("global_points", 0) if balance else 0
	username = lookup.youtube_profile.youtube_username if lookup.youtube_profile else lookup.display_name
	await send_chat_message(
		client,
		live_chat_id,
		f"El usuario @{username} tiene {_format_points(points)}.",
	)
	return True

