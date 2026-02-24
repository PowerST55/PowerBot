"""
Comando slots para chat de YouTube.
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from backend.managers import economy_manager
from backend.managers.user_lookup_manager import find_user_by_youtube_channel_id
from backend.services.activities import cooldown_manager, games_config, slots_master

from ...config.economy import get_youtube_economy_config
from ...send_message import send_chat_message

if TYPE_CHECKING:
	from ...youtube_core import YouTubeClient
	from ...youtube_types import YouTubeMessage


SLOTS_ALIASES = {"tm", "tragamonedas", "slots", "sl"}


def _format_time_left(remaining_seconds: float) -> str:
	minutes = int(remaining_seconds // 60)
	seconds = int(remaining_seconds % 60)
	if minutes > 0:
		return f"{minutes}m {seconds}s"
	return f"{seconds}s"


def _parse_bet_amount(raw_value: str, current_balance: float) -> tuple[Optional[int], Optional[str]]:
	raw = raw_value.strip().lower()
	if raw == "all":
		return int(current_balance), None

	try:
		amount = int(float(raw))
	except ValueError:
		return None, "❌ Cantidad inválida. Usa un número entero o 'all'."

	return amount, None


def _get_current_balance(user_id: int) -> float:
	return float(economy_manager.get_total_balance(user_id))


def _apply_balance_delta(user_id: int, delta: float, reason: str, source_id: str | None) -> float:
	return float(
		economy_manager.apply_balance_delta(
			user_id=user_id,
			delta=delta,
			reason=reason,
			platform="youtube",
			source_id=source_id,
		)
	)


async def process_slots_command(
	command: str,
	args: List[str],
	message: "YouTubeMessage",
	client: "YouTubeClient",
	live_chat_id: str,
) -> bool:
	"""Procesa !tm / !tragamonedas / !slots / !sl."""
	if command not in SLOTS_ALIASES:
		return False

	if len(args) != 1:
		await send_chat_message(
			client,
			live_chat_id,
			"Uso: !tm <cantidad>. Aliases: !tragamonedas !slots !sl",
		)
		return True

	lookup = find_user_by_youtube_channel_id(message.author_channel_id)
	if not lookup:
		await send_chat_message(
			client,
			live_chat_id,
			f"❌ No encontré usuario vinculado para {message.author_name}. Escribe otro mensaje y vuelve a intentar.",
		)
		return True

	config = games_config.get_slots_config()
	limit = float(config.get("limit", 0.0) or 0.0)
	cooldown_seconds = int(config.get("cooldown", 0) or 0)

	can_play, remaining = cooldown_manager.check_cooldown(
		str(message.author_channel_id), "slots", cooldown_seconds
	)
	if not can_play:
		await send_chat_message(
			client,
			live_chat_id,
			f"⏳ {message.author_name} espera {_format_time_left(float(remaining or 0))} para volver a jugar slots.",
		)
		return True

	current_balance = _get_current_balance(lookup.user_id)
	bet_amount, parse_error = _parse_bet_amount(args[0], current_balance)
	if parse_error:
		await send_chat_message(client, live_chat_id, parse_error)
		return True

	assert bet_amount is not None

	if limit > 0 and bet_amount > limit:
		await send_chat_message(
			client,
			live_chat_id,
			f"❌ Límite de slots: {int(limit):,}. Intentaste {bet_amount:,}.",
		)
		return True

	is_valid, validation_message = slots_master.validate_gamble(current_balance, float(bet_amount))
	if not is_valid:
		await send_chat_message(client, live_chat_id, validation_message)
		return True

	combo, ganancia_neta, multiplicador, descripcion, es_ganancia, luck_multiplier = slots_master.spin_slots(
		bet_amount,
		str(message.author_channel_id),
	)

	cooldown_manager.update_cooldown(str(message.author_channel_id), "slots")

	new_balance = _apply_balance_delta(
		user_id=lookup.user_id,
		delta=float(ganancia_neta),
		reason="slots",
		source_id=f"yt_slots:{message.id or message.author_channel_id}:{message.published_at}",
	)

	if es_ganancia:
		slots_master.reset_user_luck_multiplier(str(message.author_channel_id))
	else:
		slots_master.increment_user_luck_multiplier(str(message.author_channel_id), 0.1)

	economy_config = get_youtube_economy_config()
	symbol = economy_config.get_currency_symbol()
	summary = slots_master.get_slot_summary(
		username=message.author_name,
		bet_amount=bet_amount,
		combo=combo,
		ganancia_neta=ganancia_neta,
		multiplicador=multiplicador,
		descripcion=descripcion,
		es_ganancia=es_ganancia,
		luck_multiplier=luck_multiplier,
		puntos_finales=int(new_balance),
	)

	await send_chat_message(
		client,
		live_chat_id,
		(
			f"🎰 {message.author_name} {summary['combo_display']} | {summary['descripcion']} | "
			f"{summary['ganancia_perdida_label']}: {summary['ganancia_perdida_texto']}{symbol} | "
			f"Saldo: {int(new_balance):,}{symbol}"
		),
	)
	return True

