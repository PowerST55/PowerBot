"""Notificador de streams de YouTube para Discord.

Este módulo se apoya en StreamManager para detectar cuándo
comienza un directo en YouTube y envía una notificación a los
servidores que tengan:

  - Canal configurado: /set channel livestreams #canal
  - Rol de notificaciones: /set role notifications @rol (opcional)

La detección usa una sola llamada periódica a la API de YouTube
(via StreamManager.detect_stream), y cachea estado en
backend/data/youtube_bot/active_stream.json para minimizar consultas.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import discord

from backend.managers.stream_manager import StreamManager
from backend.services.discord_bot.config import get_channels_config
from backend.services.discord_bot.config.roles import get_roles_config
from backend.services.youtube_api import YouTubeAPI


async def _live_stream_loop(bot: discord.Client, interval: int = 60) -> None:
	"""Loop que detecta inicio de streams y notifica en Discord."""

	stream_manager = StreamManager()
	yt: Optional[YouTubeAPI] = None
	last_video_id_notified: Optional[str] = None

	while not bot.is_closed():
		try:
			# Verificar si hay al menos un guild con canal de livestream configurado
			guilds_to_notify = []
			for guild in bot.guilds:
				channels_config = get_channels_config(guild.id)
				ch_id = channels_config.get_channel("livestream_channel")
				if ch_id:
					guilds_to_notify.append((guild, int(ch_id)))

			if not guilds_to_notify:
				await asyncio.sleep(interval)
				continue

			# Asegurar conexión a YouTube API
			if yt is None or not yt.is_connected():
				yt = yt or YouTubeAPI()
				if not yt.connect():
					# Si no podemos conectar, esperamos y reintentamos luego
					await asyncio.sleep(interval)
					continue

			# Detectar estado de stream (1 llamada a la API por ciclo)
			result = stream_manager.detect_stream(yt.client)
			is_live = bool(result.get("is_live"))
			changed = bool(result.get("changed"))
			video_id = result.get("video_id") or None
			title = result.get("title") or "(sin título)"
			url = result.get("url") or ""

			# Sólo actuamos cuando hay cambio y es inicio de stream
			if not (changed and is_live and video_id):
				await asyncio.sleep(interval)
				continue

			# Evitar notificar dos veces el mismo video en este runtime
			if video_id == last_video_id_notified:
				await asyncio.sleep(interval)
				continue

			last_video_id_notified = video_id

			# Enviar notificación a todos los guilds configurados
			for guild, channel_id in guilds_to_notify:
				channel = guild.get_channel(channel_id) or bot.get_channel(channel_id)
				if not isinstance(channel, discord.TextChannel):
					continue

				roles_config = get_roles_config(guild.id)
				notif_role_id = roles_config.get_role("notifications")
				mention = f"<@&{notif_role_id}>" if notif_role_id else ""

				message = f"🔴 **{title}**\n{url} {mention}".strip()
				try:
					await channel.send(message)
				except Exception as exc:
					print(f"⚠️ Error enviando notificación de stream en {guild.name}: {exc}")

		except Exception as loop_exc:
			print(f"⚠️ Error en loop de notificador de streams: {loop_exc}")

		await asyncio.sleep(interval)


async def start_live_stream_notifier(bot: discord.Client, interval: int = 60) -> None:
	"""Arranca el notificador de streams si no está corriendo ya."""

	task_attr = "_live_stream_task"
	existing = getattr(bot, task_attr, None)
	if existing is None or existing.done():
		setattr(bot, task_attr, asyncio.create_task(_live_stream_loop(bot, interval)))
		print("📺 Notificador de directos YouTube activado")
