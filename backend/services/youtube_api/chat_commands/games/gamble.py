"""
Comando gamble para chat de YouTube.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import List, Optional, TYPE_CHECKING

from backend.managers import economy_manager
from backend.managers.user_lookup_manager import find_user_by_youtube_channel_id
from backend.services.activities import cooldown_manager, gamble_master, games_config, casino_master
from backend.services.discord_bot.economy.economy_channel import (
	get_casino_bankruptcy_state,
	register_casino_bankruptcy,
)

from ...config.economy import get_youtube_economy_config
from ...send_message import send_chat_message

if TYPE_CHECKING:
	from ...youtube_core import YouTubeClient
	from ...youtube_types import YouTubeMessage


GAMBLE_ALIASES = {"g", "gamble"}


def _format_time_left(remaining_seconds: float) -> str:
	minutes = int(remaining_seconds // 60)
	seconds = int(remaining_seconds % 60)
	if minutes > 0:
		return f"{minutes}m {seconds}s"
	return f"{seconds}s"


def _parse_bet_amount(raw_value: str, current_balance: float) -> tuple[Optional[float], Optional[str]]:
	raw = raw_value.strip().lower()
	if raw == "all":
		return round(float(current_balance), 2), None

	try:
		amount = Decimal(raw)
	except (InvalidOperation, ValueError):
		return None, "❌ Cantidad inválida. Usa un número o 'all'."

	amount = amount.quantize(Decimal("0.01"))
	return float(amount), None


def _get_current_balance(user_id: int) -> float:
	return float(economy_manager.get_total_balance(user_id))


def _is_casino_bankrupt(casino_fund_balance: float) -> bool:
	state = get_casino_bankruptcy_state()
	if bool(state.get("is_bankrupt")):
		return True
	return float(casino_fund_balance) <= 0


def _settle_casino_bet(user_id: int, delta: float, reason: str, source_id: str | None) -> dict:
	return economy_manager.settle_casino_bet(
		user_id=user_id,
		delta=delta,
		reason=reason,
		platform="youtube",
		source_id=source_id,
		allow_negative_casino_fund=True,
	)


async def process_gamble_command(
	command: str,
	args: List[str],
	message: "YouTubeMessage",
	client: "YouTubeClient",
	live_chat_id: str,
) -> bool:
	"""Procesa !g / !gamble."""
	if command not in GAMBLE_ALIASES:
		return False

	if len(args) != 1:
		await send_chat_message(client, live_chat_id, "Uso: !g <cantidad>. Alias: !gamble")
		return True

	lookup = find_user_by_youtube_channel_id(message.author_channel_id)
	if not lookup:
		await send_chat_message(
			client,
			live_chat_id,
			f"❌ No encontré usuario vinculado para {message.author_name}. Escribe otro mensaje y vuelve a intentar.",
		)
		return True

	config = games_config.get_gamble_config()
	min_limit = float(config.get("min_limit", 0.0) or 0.0)
	max_limit = float(config.get("max_limit", 0.0) or 0.0)
	cooldown_seconds = int(config.get("cooldown", 0) or 0)

	can_play, remaining = cooldown_manager.check_cooldown(
		str(message.author_channel_id), "gamble", cooldown_seconds
	)
	if not can_play:
		await send_chat_message(
			client,
			live_chat_id,
			f"⏳ {message.author_name} espera {_format_time_left(float(remaining or 0))} para volver a jugar gamble.",
		)
		return True

	current_balance = _get_current_balance(lookup.user_id)
	bet_amount, parse_error = _parse_bet_amount(args[0], current_balance)
	if parse_error:
		await send_chat_message(client, live_chat_id, parse_error)
		return True

	assert bet_amount is not None

	if min_limit > 0 and bet_amount < min_limit:
		await send_chat_message(
			client,
			live_chat_id,
			f"❌ Límite mínimo de gamble: {min_limit:,.2f}. Intentaste {bet_amount:,.2f}.",
		)
		return True

	if max_limit > 0 and bet_amount > max_limit:
		await send_chat_message(
			client,
			live_chat_id,
			f"❌ Límite máximo de gamble: {max_limit:,.2f}. Intentaste {bet_amount:,.2f}.",
		)
		return True

	is_valid, validation_message = gamble_master.validate_gamble(current_balance, bet_amount)
	if not is_valid:
		await send_chat_message(client, live_chat_id, f"❌ {validation_message}")
		return True

	casino_fund_balance = economy_manager.get_casino_fund_balance()
	if _is_casino_bankrupt(casino_fund_balance):
		state = get_casino_bankruptcy_state()
		cause_display = str(state.get("cause_display") or "un jugador")
		await send_chat_message(
			client,
			live_chat_id,
			f"🎰 El casino está en bancarrota por causa de {cause_display}. Las mesas siguen cerradas hasta recargar fondo_casino.",
		)
		return True

	roll, ganancia_neta, multiplicador, rango = gamble_master.calculate_gamble_result(bet_amount, casino_fund_balance)

	settlement = _settle_casino_bet(
		user_id=lookup.user_id,
		delta=ganancia_neta,
		reason="gamble",
		source_id=f"yt_gamble:{message.id or message.author_channel_id}:{message.published_at}",
	)
	if not settlement.get("success"):
		await send_chat_message(client, live_chat_id, f"❌ No se pudo liquidar la jugada: {settlement.get('error', 'error desconocido')}")
		return True

	cooldown_manager.update_cooldown(str(message.author_channel_id), "gamble")

	new_balance = float(settlement["user_balance"])
	casino_balance_after = float(settlement["casino_balance_after"])

	if settlement.get("bankruptcy_triggered"):
		register_casino_bankruptcy(
			cause_display=f"@{message.author_name}",
			cause_platform="youtube",
			cause_user_id=str(message.author_channel_id),
			game_name="gamble",
			previous_balance=float(settlement["casino_balance_before"]),
			new_balance=casino_balance_after,
			bet_amount=bet_amount,
			net_result=ganancia_neta,
		)

	economy_config = get_youtube_economy_config()
	symbol = economy_config.get_currency_symbol()
	summary = gamble_master.get_gamble_summary(
		username=message.author_name,
		bet_amount=bet_amount,
		roll=roll,
		ganancia_neta=ganancia_neta,
		multiplicador=multiplicador,
		rango=rango,
		puntos_finales=new_balance,
	)

	await send_chat_message(
		client,
		live_chat_id,
		(
			f"{summary['resultado_emoji']} {message.author_name} | 🎲 {roll}/100 | "
			f"Apuesta: {bet_amount:,.2f}{symbol} | Resultado: {summary['ganancia_texto']}{symbol} | "
			f"Saldo: {new_balance:,.2f}{symbol}"
		),
	)
	return True

