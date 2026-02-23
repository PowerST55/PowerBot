"""
Comandos generales del chat de YouTube.
"""

import logging
from typing import List

from backend.managers.user_lookup_manager import (
	find_user_by_global_id,
	find_user_by_youtube_channel_id,
	find_user_by_youtube_username,
)
from .economy.economy_general import process_economy_command
from .games.gamble import process_gamble_command
from .games.slots import process_slots_command
from .livefeed.admin import process_livefeed_admin_command
from .livefeed.spinwheel import process_spinwheel_participation_command
from ..send_message import send_chat_message
from ..youtube_core import YouTubeClient
from ..youtube_listener import YouTubeMessage

logger = logging.getLogger(__name__)


async def process_general_command(
	command: str,
	args: List[str],
	message: YouTubeMessage,
	client: YouTubeClient,
	live_chat_id: str,
) -> bool:
	"""Procesa comandos generales. Retorna True si se manejo el comando."""
	if await process_economy_command(command, args, message, client, live_chat_id):
		return True

	if await process_gamble_command(command, args, message, client, live_chat_id):
		return True

	if await process_slots_command(command, args, message, client, live_chat_id):
		return True

	if await process_livefeed_admin_command(command, args, message, client, live_chat_id):
		return True

	if await process_spinwheel_participation_command(command, args, message, client, live_chat_id):
		return True

	if command == "id":
		# Caso 1: !id -> buscar al mismo usuario por su canal YouTube
		if not args:
			result = find_user_by_youtube_channel_id(message.author_channel_id)
			if result:
				await send_chat_message(
					client,
					live_chat_id,
					f"La id de {message.author_name} es {result.user_id}"
				)
			else:
				await send_chat_message(
					client,
					live_chat_id,
					f"No encontré una ID para {message.author_name}."
				)
			return True

		query = " ".join(args).strip()
		if not query:
			await send_chat_message(client, live_chat_id, "Uso: !id, !id <id> o !id <usuario>")
			return True

		# Caso 2: !id 15 -> búsqueda inversa por ID global
		if query.isdigit():
			result = find_user_by_global_id(int(query))
			if not result:
				await send_chat_message(client, live_chat_id, f"No existe usuario con id {query}.")
				return True

			if result.discord_profile and result.discord_profile.discord_username:
				await send_chat_message(
					client,
					live_chat_id,
					f"El usuario @{result.discord_profile.discord_username} (discord) tiene la id: {result.user_id}"
				)
			elif result.youtube_profile and result.youtube_profile.youtube_username:
				await send_chat_message(
					client,
					live_chat_id,
					f"El Usuario con id {result.user_id} es @{result.youtube_profile.youtube_username}."
				)
			else:
				await send_chat_message(
					client,
					live_chat_id,
					f"El Usuario con id {result.user_id} es {result.display_name}."
				)
			return True

		# Caso 3: !id @usuario o !id usuario -> búsqueda por username YouTube
		yt_result = find_user_by_youtube_username(query)
		if yt_result and yt_result.youtube_profile:
			username = yt_result.youtube_profile.youtube_username or yt_result.display_name
			await send_chat_message(
				client,
				live_chat_id,
				f"El usuario @{username} tiene la id: {yt_result.user_id}"
			)
		else:
			await send_chat_message(client, live_chat_id, f"No encontré al usuario '{query}'.")
		return True

	return False

