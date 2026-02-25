"""
Notificaciones de progreso de economía para Discord.

Reglas:
- Hitos se notifican solo una vez por usuario/guild.
- Bancarrota (saldo <= 0) se notifica múltiples veces, pero solo cuando pasa de >0 a <=0.
- Si el usuario inicia en 0, no dispara bancarrota.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import discord

from backend.services.discord_bot.config import get_channels_config
from backend.services.discord_bot.config.economy import get_economy_config


MILESTONE_LEVELS = [
	10,
	50,
	100,
	200,
	350,
	500,
	700,
	1000,
	1500,
	2000,
	3000,
	4000,
	5000,
	6000,
	7000,
	8000,
	9000,
	10000,
	20000,
	30000,
	40000,
	50000,
	60000,
	70000,
	80000,
	90000,
	100000,
]

BANKRUPTCY_THRESHOLD = 0.99


def _data_dir() -> Path:
	return Path(__file__).resolve().parents[3] / "data" / "discord_bot"


def _state_file(guild_id: int) -> Path:
	return _data_dir() / f"guild_{guild_id}_economy_events.json"


def _external_events_file() -> Path:
	return _data_dir() / "economy_external_events.json"


def _load_state(guild_id: int) -> dict[str, Any]:
	file_path = _state_file(guild_id)
	if file_path.exists():
		try:
			with open(file_path, "r", encoding="utf-8") as file:
				data = json.load(file)
				if isinstance(data, dict):
					data.setdefault("users", {})
					return data
		except Exception:
			pass
	return {"users": {}}


def _save_state(guild_id: int, state: dict[str, Any]) -> None:
	file_path = _state_file(guild_id)
	file_path.parent.mkdir(parents=True, exist_ok=True)
	with open(file_path, "w", encoding="utf-8") as file:
		json.dump(state, file, indent=2, ensure_ascii=False)


def _ensure_user_state(state: dict[str, Any], user_key: str) -> dict[str, Any]:
	users = state.setdefault("users", {})
	user_key = str(user_key)
	if user_key not in users or not isinstance(users[user_key], dict):
		users[user_key] = {"milestones": []}
	users[user_key].setdefault("milestones", [])
	return users[user_key]


def enqueue_external_platform_progress_event(
	platform: str,
	platform_user_id: str,
	previous_balance: float,
	new_balance: float,
) -> None:
	"""Encola eventos de progreso para plataformas no-Discord (cross-process)."""
	queue_file = _external_events_file()
	queue_file.parent.mkdir(parents=True, exist_ok=True)

	event = {
		"platform": str(platform).strip().lower(),
		"platform_user_id": str(platform_user_id).strip(),
		"previous_balance": float(previous_balance),
		"new_balance": float(new_balance),
	}

	queue: list[dict[str, Any]] = []
	if queue_file.exists():
		try:
			with open(queue_file, "r", encoding="utf-8") as file:
				loaded = json.load(file)
				if isinstance(loaded, list):
					queue = loaded
		except Exception:
			queue = []

	queue.append(event)
	with open(queue_file, "w", encoding="utf-8") as file:
		json.dump(queue, file, indent=2, ensure_ascii=False)


def pop_external_platform_progress_events(max_items: int = 100) -> list[dict[str, Any]]:
	"""Extrae eventos externos encolados para ser publicados por el bot de Discord."""
	queue_file = _external_events_file()
	if not queue_file.exists():
		return []

	try:
		with open(queue_file, "r", encoding="utf-8") as file:
			loaded = json.load(file)
		if not isinstance(loaded, list) or not loaded:
			return []

		events = loaded[:max_items]
		remaining = loaded[max_items:]

		if remaining:
			with open(queue_file, "w", encoding="utf-8") as file:
				json.dump(remaining, file, indent=2, ensure_ascii=False)
		else:
			try:
				queue_file.unlink()
			except Exception:
				with open(queue_file, "w", encoding="utf-8") as file:
					json.dump([], file, indent=2, ensure_ascii=False)

		return [event for event in events if isinstance(event, dict)]
	except Exception:
		return []


async def notify_economy_progress_if_needed(
	bot: discord.Client,
	guild_id: int,
	discord_user_id: int,
	previous_balance: float,
	new_balance: float,
	platform: str = "discord",
	platform_user_id: str | None = None,
) -> None:
	"""Notifica hitos y bancarrota en el canal de economía configurado."""
	try:
		platform_value = str(platform or "discord").strip().lower()
		user_ref = str(platform_user_id or discord_user_id)
		user_state_key = f"{platform_value}:{user_ref}"

		channels_config = get_channels_config(guild_id)
		economy_channel_id = channels_config.get_channel("economy_channel")
		if not economy_channel_id:
			return

		channel = bot.get_channel(int(economy_channel_id))
		if channel is None:
			guild = bot.get_guild(int(guild_id))
			if guild is not None:
				channel = guild.get_channel(int(economy_channel_id))

		if not isinstance(channel, discord.TextChannel):
			return

		prev_value = float(previous_balance)
		new_value = float(new_balance)

		economy_config = get_economy_config(guild_id)
		currency_name = economy_config.get_currency_name()
		currency_symbol = economy_config.get_currency_symbol()

		if platform_value == "discord":
			mention_id: int | None = None
			try:
				mention_id = int(user_ref)
			except Exception:
				try:
					mention_id = int(discord_user_id)
				except Exception:
					mention_id = None

			if mention_id is not None and mention_id > 0:
				user_display = f"<@{mention_id}>"
			else:
				user_display = "@usuario"
		else:
			user_display = f"**ID {user_ref} ({platform_value})**"

		state = _load_state(guild_id)
		user_state = _ensure_user_state(state, user_state_key)
		already_notified = {int(value) for value in user_state.get("milestones", [])}

		pending_levels: list[int] = []
		for level in MILESTONE_LEVELS:
			if level in already_notified:
				continue
			# Catch-up: si el usuario ya superó el hito y no estaba marcado,
			# se dispara igualmente (no requiere valor exacto).
			if new_value >= float(level):
				pending_levels.append(level)

		for level in pending_levels:
			if level == 10:
				message = f"{user_display} consiguió sus primeros 10 {currency_symbol} 🚀"
			else:
				message = f"{user_display} consiguió {level:,} {currency_symbol} 🚀"
			await channel.send(message)
			already_notified.add(level)

		if prev_value > BANKRUPTCY_THRESHOLD and new_value <= BANKRUPTCY_THRESHOLD:
			await channel.send(
				f"{user_display} quedó en bancarrota: {new_value:,.2f} {currency_symbol} 💸"
			)
			# Reinicia logros para que el usuario pueda volver a obtener 10, 50, 100...
			user_state["milestones"] = []
			already_notified.clear()
			_save_state(guild_id, state)

		if pending_levels:
			user_state["milestones"] = sorted(already_notified)
			_save_state(guild_id, state)
	except Exception as exc:
		print(f"⚠️ Error notificando progreso de economía: {exc}")

async def notify_external_platform_progress_all_guilds(
	bot: discord.Client,
	platform: str,
	platform_user_id: str,
	previous_balance: float,
	new_balance: float,
) -> None:
	"""Publica progreso de usuario externo en todos los guilds con economy_channel configurado."""
	for guild in bot.guilds:
		try:
			await notify_economy_progress_if_needed(
				bot=bot,
				guild_id=int(guild.id),
				discord_user_id=0,
				previous_balance=float(previous_balance),
				new_balance=float(new_balance),
				platform=platform,
				platform_user_id=platform_user_id,
			)
		except Exception as exc:
			print(f"⚠️ Error notificando progreso externo en guild {guild.id}: {exc}")
