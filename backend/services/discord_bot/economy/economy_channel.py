"""
Notificaciones de progreso de economía para Discord.

Reglas:
- Hitos se notifican solo una vez por usuario/guild.
- Bancarrota (saldo <= 0) se notifica múltiples veces, pero solo cuando pasa de >0 a <=0.
- Si el usuario inicia en 0, no dispara bancarrota.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import discord

from backend.managers import economy_manager
from backend.services.discord_bot.config import get_channels_config
from backend.services.discord_bot.config.economy import get_economy_config
from backend.services.discord_bot.config.mine_config import get_mine_config
from backend.managers.user_lookup_manager import (
	find_user_by_discord_id,
	find_user,
)


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
CASINO_AUTO_RELOAD_SECONDS = 12 * 60 * 60
CASINO_AUTO_RELOAD_TARGET = 2500.0
CASINO_AUTO_RELOAD_PARTIAL_RATIO = 0.15
MINE_AUTO_RELOAD_SECONDS = 12 * 60 * 60
MINE_AUTO_RELOAD_TARGET = 2500.0
MINE_AUTO_RELOAD_PARTIAL_RATIO = 0.15


def _data_dir() -> Path:
	return Path(__file__).resolve().parents[3] / "data" / "discord_bot"


def _state_file(guild_id: int) -> Path:
	return _data_dir() / f"guild_{guild_id}_economy_events.json"


def _external_events_file() -> Path:
	return _data_dir() / "economy_external_events.json"


def _casino_state_file() -> Path:
	return _data_dir() / "casino_bankruptcy_state.json"


def _casino_events_file() -> Path:
	return _data_dir() / "casino_bankruptcy_events.json"


def _mine_state_file() -> Path:
	return _data_dir() / "mine_depletion_state.json"


def _mine_events_file() -> Path:
	return _data_dir() / "mine_events.json"


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


def get_casino_bankruptcy_state() -> dict[str, Any]:
	"""Devuelve el último estado conocido de bancarrota del casino."""
	file_path = _casino_state_file()
	if file_path.exists():
		try:
			with open(file_path, "r", encoding="utf-8") as file:
				data = json.load(file)
				if isinstance(data, dict):
					data.setdefault("is_bankrupt", False)
					return data
		except Exception:
			pass
	return {"is_bankrupt": False}


def set_casino_bankruptcy_state(state: dict[str, Any]) -> None:
	file_path = _casino_state_file()
	file_path.parent.mkdir(parents=True, exist_ok=True)
	with open(file_path, "w", encoding="utf-8") as file:
		json.dump(state, file, indent=2, ensure_ascii=False)


def enqueue_casino_bankruptcy_event(event: dict[str, Any]) -> None:
	queue_file = _casino_events_file()
	queue_file.parent.mkdir(parents=True, exist_ok=True)

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


def pop_casino_bankruptcy_events(max_items: int = 20) -> list[dict[str, Any]]:
	queue_file = _casino_events_file()
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


def get_mine_depletion_state() -> dict[str, Any]:
	"""Devuelve el último estado conocido de agotamiento de la mina."""
	file_path = _mine_state_file()
	if file_path.exists():
		try:
			with open(file_path, "r", encoding="utf-8") as file:
				data = json.load(file)
				if isinstance(data, dict):
					data.setdefault("is_depleted", False)
					return data
		except Exception:
			pass
	return {"is_depleted": False}


def set_mine_depletion_state(state: dict[str, Any]) -> None:
	file_path = _mine_state_file()
	file_path.parent.mkdir(parents=True, exist_ok=True)
	with open(file_path, "w", encoding="utf-8") as file:
		json.dump(state, file, indent=2, ensure_ascii=False)


def enqueue_mine_event(event: dict[str, Any]) -> None:
	queue_file = _mine_events_file()
	queue_file.parent.mkdir(parents=True, exist_ok=True)

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


def pop_mine_events(max_items: int = 20) -> list[dict[str, Any]]:
	queue_file = _mine_events_file()
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


def register_mine_depleted(*, guild_id: int | None = None, source: str = "depleted") -> None:
	"""Registra que la mina quedó agotada y programa su próxima recarga."""
	current_state = get_mine_depletion_state()
	if current_state.get("is_depleted"):
		return

	now_ts = time.time()
	set_mine_depletion_state(
		{
			**current_state,
			"is_depleted": True,
			"depleted_at": now_ts,
			"next_retry_at": now_ts + MINE_AUTO_RELOAD_SECONDS,
			"guild_id": None if guild_id is None else int(guild_id),
			"source": str(source or "depleted").strip().lower(),
		}
	)


def register_mine_reopened(
	*,
	source: str,
	reloaded_amount: float,
	common_fund_before: float | None = None,
	common_fund_after: float | None = None,
	mine_balance_after: float | None = None,
) -> None:
	"""Registra la reactivación de la mina y la anuncia en economy_channel."""
	now_ts = time.time()
	current_state = get_mine_depletion_state()
	event = {
		"type": "mine_reopened",
		"source": str(source or "manual").strip().lower(),
		"reloaded_amount": float(reloaded_amount),
		"common_fund_before": None if common_fund_before is None else float(common_fund_before),
		"common_fund_after": None if common_fund_after is None else float(common_fund_after),
		"mine_balance_after": None if mine_balance_after is None else float(mine_balance_after),
		"timestamp": now_ts,
	}
	set_mine_depletion_state(
		{
			**current_state,
			"is_depleted": False,
			"reopened_at": now_ts,
			"last_recovery_source": event["source"],
			"last_reloaded_amount": float(reloaded_amount),
			"next_retry_at": None,
		}
	)
	enqueue_mine_event(event)


def _mine_has_operable_items_any_guild(mine_balance: float) -> bool:
	if mine_balance <= BANKRUPTCY_THRESHOLD:
		return False

	data_dir = _data_dir()
	for path in data_dir.glob("guild_*_mine_config.json"):
		try:
			guild_id = int(path.stem.split("_")[1])
		except Exception:
			continue
		try:
			items = get_mine_config(guild_id).list_items()
		except Exception:
			continue
		for item in items:
			probability_value = float(item.get("probability", 0) or 0)
			price_value = float(item.get("price", 0) or 0)
			if probability_value <= 0:
				continue
			if price_value > 0 and price_value > mine_balance:
				continue
			return True
	return False


def process_mine_recovery_cycle() -> None:
	"""Gestiona reapertura manual y recarga automática de la mina agotada."""
	state = get_mine_depletion_state()
	if not state.get("is_depleted"):
		return

	mine_balance = float(economy_manager.get_mine_fund_balance())
	if _mine_has_operable_items_any_guild(mine_balance):
		register_mine_reopened(
			source="manual",
			reloaded_amount=max(0.0, round(mine_balance, 2)),
			mine_balance_after=mine_balance,
		)
		return

	now_ts = time.time()
	next_retry_at = float(state.get("next_retry_at") or 0)
	if next_retry_at > now_ts:
		return

	common_fund_before = float(economy_manager.get_common_fund_balance())
	if common_fund_before <= 0:
		updated_state = {
			**state,
			"next_retry_at": now_ts + MINE_AUTO_RELOAD_SECONDS,
			"last_retry_at": now_ts,
			"last_retry_result": "skipped_common_fund_empty",
		}
		set_mine_depletion_state(updated_state)
		return

	reload_amount = (
		MINE_AUTO_RELOAD_TARGET
		if common_fund_before >= MINE_AUTO_RELOAD_TARGET
		else round(common_fund_before * MINE_AUTO_RELOAD_PARTIAL_RATIO, 2)
	)
	if reload_amount <= 0:
		updated_state = {
			**state,
			"next_retry_at": now_ts + MINE_AUTO_RELOAD_SECONDS,
			"last_retry_at": now_ts,
			"last_retry_result": "skipped_reload_amount_zero",
		}
		set_mine_depletion_state(updated_state)
		return

	try:
		transfer_result = economy_manager.transfer_system_funds(
			from_account_key=economy_manager.COMMON_FUND_ACCOUNT,
			to_account_key=economy_manager.MINE_FUND_ACCOUNT,
			amount=reload_amount,
			reason="mine_auto_reload",
		)
	except Exception:
		updated_state = {
			**state,
			"next_retry_at": now_ts + MINE_AUTO_RELOAD_SECONDS,
			"last_retry_at": now_ts,
			"last_retry_result": "failed_transfer",
		}
		set_mine_depletion_state(updated_state)
		return

	mine_balance_after = float(transfer_result.get("to_balance_after") or 0)
	if _mine_has_operable_items_any_guild(mine_balance_after):
		register_mine_reopened(
			source="auto",
			reloaded_amount=float(transfer_result.get("transferred") or reload_amount),
			common_fund_before=float(transfer_result.get("from_balance_before") or common_fund_before),
			common_fund_after=float(transfer_result.get("from_balance_after") or 0),
			mine_balance_after=mine_balance_after,
		)
		return

	updated_state = {
		**state,
		"next_retry_at": now_ts + MINE_AUTO_RELOAD_SECONDS,
		"last_retry_at": now_ts,
		"last_retry_result": "partial_reload_not_enough",
		"last_reloaded_amount": float(transfer_result.get("transferred") or reload_amount),
	}
	set_mine_depletion_state(updated_state)


def register_casino_bankruptcy(
	*,
	cause_display: str,
	cause_platform: str,
	cause_user_id: str,
	game_name: str,
	previous_balance: float,
	new_balance: float,
	bet_amount: float,
	net_result: float,
) -> None:
	"""Registra la bancarrota del casino y encola un anuncio global."""
	now_ts = time.time()
	event = {
		"type": "casino_bankruptcy",
		"cause_display": str(cause_display or "un jugador"),
		"cause_platform": str(cause_platform or "unknown").strip().lower(),
		"cause_user_id": str(cause_user_id or "unknown"),
		"game_name": str(game_name or "casino"),
		"previous_balance": float(previous_balance),
		"new_balance": float(new_balance),
		"bet_amount": float(bet_amount),
		"net_result": float(net_result),
		"timestamp": now_ts,
	}
	set_casino_bankruptcy_state(
		{
			"is_bankrupt": True,
			"bankrupt_at": now_ts,
			"next_retry_at": now_ts + CASINO_AUTO_RELOAD_SECONDS,
			"last_recovery_source": "bankruptcy",
			**event,
		}
	)
	enqueue_casino_bankruptcy_event(event)


def register_casino_reopened(
	*,
	source: str,
	reloaded_amount: float,
	common_fund_before: float | None = None,
	common_fund_after: float | None = None,
	casino_balance_after: float | None = None,
) -> None:
	"""Registra la reapertura del casino y la anuncia en economy_channel."""
	now_ts = time.time()
	current_state = get_casino_bankruptcy_state()
	event = {
		"type": "casino_reopened",
		"source": str(source or "manual").strip().lower(),
		"reloaded_amount": float(reloaded_amount),
		"common_fund_before": None if common_fund_before is None else float(common_fund_before),
		"common_fund_after": None if common_fund_after is None else float(common_fund_after),
		"casino_balance_after": None if casino_balance_after is None else float(casino_balance_after),
		"timestamp": now_ts,
	}
	set_casino_bankruptcy_state(
		{
			**current_state,
			"is_bankrupt": False,
			"reopened_at": now_ts,
			"last_recovery_source": event["source"],
			"last_reloaded_amount": float(reloaded_amount),
			"next_retry_at": None,
		}
	)
	enqueue_casino_bankruptcy_event(event)


def process_casino_recovery_cycle() -> None:
	"""Gestiona reapertura manual y recarga automática del casino en bancarrota."""
	state = get_casino_bankruptcy_state()
	if not state.get("is_bankrupt"):
		return

	casino_balance = float(economy_manager.get_casino_fund_balance())
	if casino_balance > BANKRUPTCY_THRESHOLD:
		previous_bankrupt_balance = float(state.get("new_balance") or 0)
		register_casino_reopened(
			source="manual",
			reloaded_amount=max(0.0, round(casino_balance - previous_bankrupt_balance, 2)),
			casino_balance_after=casino_balance,
		)
		return

	now_ts = time.time()
	next_retry_at = float(state.get("next_retry_at") or 0)
	if next_retry_at > now_ts:
		return

	common_fund_before = float(economy_manager.get_common_fund_balance())
	if common_fund_before <= 0:
		updated_state = {
			**state,
			"next_retry_at": now_ts + CASINO_AUTO_RELOAD_SECONDS,
			"last_retry_at": now_ts,
			"last_retry_result": "skipped_common_fund_empty",
		}
		set_casino_bankruptcy_state(updated_state)
		return

	reload_amount = (
		CASINO_AUTO_RELOAD_TARGET
		if common_fund_before >= CASINO_AUTO_RELOAD_TARGET
		else round(common_fund_before * CASINO_AUTO_RELOAD_PARTIAL_RATIO, 2)
	)
	if reload_amount <= 0:
		updated_state = {
			**state,
			"next_retry_at": now_ts + CASINO_AUTO_RELOAD_SECONDS,
			"last_retry_at": now_ts,
			"last_retry_result": "skipped_reload_amount_zero",
		}
		set_casino_bankruptcy_state(updated_state)
		return

	try:
		transfer_result = economy_manager.transfer_system_funds(
			from_account_key=economy_manager.COMMON_FUND_ACCOUNT,
			to_account_key=economy_manager.CASINO_FUND_ACCOUNT,
			amount=reload_amount,
			reason="casino_auto_reload",
		)
	except Exception:
		updated_state = {
			**state,
			"next_retry_at": now_ts + CASINO_AUTO_RELOAD_SECONDS,
			"last_retry_at": now_ts,
			"last_retry_result": "failed_transfer",
		}
		set_casino_bankruptcy_state(updated_state)
		return

	casino_balance_after = float(transfer_result.get("to_balance_after") or 0)
	if casino_balance_after > BANKRUPTCY_THRESHOLD:
		register_casino_reopened(
			source="auto",
			reloaded_amount=float(transfer_result.get("transferred") or reload_amount),
			common_fund_before=float(transfer_result.get("from_balance_before") or common_fund_before),
			common_fund_after=float(transfer_result.get("from_balance_after") or 0),
			casino_balance_after=casino_balance_after,
		)
		return

	updated_state = {
		**state,
		"new_balance": casino_balance_after,
		"next_retry_at": now_ts + CASINO_AUTO_RELOAD_SECONDS,
		"last_retry_at": now_ts,
		"last_retry_result": "partial_reload_not_enough",
		"last_reloaded_amount": float(transfer_result.get("transferred") or reload_amount),
	}
	set_casino_bankruptcy_state(updated_state)


async def notify_casino_bankruptcy_all_guilds(bot: discord.Client, event: dict[str, Any]) -> None:
	"""Publica eventos críticos del casino en todos los guilds con economy_channel."""
	for guild in bot.guilds:
		try:
			channels_config = get_channels_config(guild.id)
			economy_channel_id = channels_config.get_channel("economy_channel")
			if not economy_channel_id:
				continue

			channel = bot.get_channel(int(economy_channel_id))
			if channel is None:
				channel = guild.get_channel(int(economy_channel_id))
			if not isinstance(channel, discord.TextChannel):
				continue

			economy_config = get_economy_config(guild.id)
			currency_symbol = economy_config.get_currency_symbol()
			event_type = str(event.get("type") or "casino_bankruptcy").strip().lower()

			if event_type == "casino_reopened":
				source = str(event.get("source") or "manual").strip().lower()
				reloaded_amount = float(event.get("reloaded_amount") or 0)
				embed = discord.Embed(
					title="🎰 Casino Reabierto",
					description="El casino ha recuperado fondos y vuelve a aceptar apuestas.",
					color=0x2ECC71,
				)
				embed.add_field(
					name="Origen",
					value="Recarga automática desde fondo común" if source == "auto" else "Recarga manual detectada",
					inline=False,
				)
				embed.add_field(
					name="Recarga aplicada",
					value=f"{reloaded_amount:,.2f}{currency_symbol}",
					inline=True,
				)
				embed.add_field(
					name="Estado",
					value="Las mesas de gamble y tragamonedas vuelven a estar disponibles.",
					inline=False,
				)
				embed.set_footer(text="Economía central • Recuperación del casino")
				await channel.send(embed=embed)
				continue

			cause_display = str(event.get("cause_display") or "un jugador")
			game_name = str(event.get("game_name") or "casino").upper()
			bet_amount = float(event.get("bet_amount") or 0)
			net_result = float(event.get("net_result") or 0)

			embed = discord.Embed(
				title="🎰 Casino En Bancarrota",
				description=(
					"El fondo del casino cayó por debajo de cero y las mesas quedaron cerradas hasta nueva recarga."
				),
				color=0xC0392B,
			)
			embed.add_field(name="Causa", value=f"{cause_display}", inline=False)
			embed.add_field(name="Juego", value=game_name, inline=True)
			embed.add_field(name="Apuesta", value=f"{bet_amount:,.2f}{currency_symbol}", inline=True)
			embed.add_field(name="Ganancia neta", value=f"{net_result:,.2f}{currency_symbol}", inline=True)
			embed.add_field(
				name="Estado",
				value="Las mesas de gamble y tragamonedas quedan suspendidas hasta recapitalizar el fondo casino.",
				inline=False,
			)
			embed.set_footer(text="Economía central • Evento crítico del casino")
			await channel.send(embed=embed)
		except Exception as exc:
			print(f"⚠️ Error notificando bancarrota del casino en guild {guild.id}: {exc}")


async def notify_mine_status_all_guilds(bot: discord.Client, event: dict[str, Any]) -> None:
	"""Publica reaperturas de la mina en todos los guilds con economy_channel."""
	for guild in bot.guilds:
		try:
			channels_config = get_channels_config(guild.id)
			economy_channel_id = channels_config.get_channel("economy_channel")
			if not economy_channel_id:
				continue

			channel = bot.get_channel(int(economy_channel_id))
			if channel is None:
				channel = guild.get_channel(int(economy_channel_id))
			if not isinstance(channel, discord.TextChannel):
				continue

			economy_config = get_economy_config(guild.id)
			currency_symbol = economy_config.get_currency_symbol()
			source = str(event.get("source") or "manual").strip().lower()
			reloaded_amount = float(event.get("reloaded_amount") or 0)

			embed = discord.Embed(
				title="⛏️ Mina Reabierta",
				description="Han llegado nuevos recursos a la operación minera. La excavación vuelve a estar disponible.",
				color=0x2ECC71,
			)
			embed.add_field(
				name="Origen",
				value="Recarga automática desde fondo común" if source == "auto" else "Recarga manual detectada",
				inline=False,
			)
			embed.add_field(
				name="Carga aplicada",
				value=f"{reloaded_amount:,.2f}{currency_symbol}",
				inline=True,
			)
			embed.add_field(
				name="Estado",
				value="La mina vuelve a operar y se reanudan las extracciones.",
				inline=False,
			)
			embed.set_footer(text="Economía central • Recuperación de la mina")
			await channel.send(embed=embed)
		except Exception as exc:
			print(f"⚠️ Error notificando reapertura de la mina en guild {guild.id}: {exc}")


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

		# Resolver ID universal del usuario, si es posible
		global_user_id: int | None = None
		try:
			if platform_value == "discord" and discord_user_id:
				lookup = find_user_by_discord_id(str(discord_user_id))
				if lookup is not None:
					global_user_id = int(lookup.user_id)
			elif platform_value in {"discord", "youtube", "global"} and user_ref:
				lookup = find_user(platform_value, str(user_ref))
				if lookup is not None:
					global_user_id = int(lookup.user_id)
		except Exception:
			global_user_id = None

		id_prefix = f"`ID:{global_user_id}` " if global_user_id is not None else ""

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
				user_display = f"{id_prefix}<@{mention_id}>".strip()
			else:
				user_display = f"{id_prefix}@usuario".strip()
		else:
			# Para plataformas externas no usamos la ID de plataforma como "ID:";
			# solo mostramos el prefijo de ID universal si se pudo resolver.
			if global_user_id is not None:
				user_display = f"{id_prefix}**({platform_value}:{user_ref})**".strip()
			else:
				user_display = f"**({platform_value}:{user_ref})**"

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
