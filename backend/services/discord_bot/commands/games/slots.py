"""
Comandos de tragamonedas.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from backend.managers import get_or_create_discord_user
from backend.managers import economy_manager
from backend.services.activities import slots_master, games_config, cooldown_manager, casino_master
from backend.services.discord_bot.economy.economy_channel import (
	get_casino_bankruptcy_state,
	register_casino_bankruptcy,
)
from backend.services.discord_bot.config.economy import get_economy_config


def setup_slots_commands(bot: commands.Bot) -> None:
	"""Registra comandos de tragamonedas"""

	@bot.tree.command(name="tragamonedas", description="Juega a la maquina tragamonedas. Alias: /tm")
	@app_commands.describe(cantidad="Cantidad a apostar, 'all' o vacio para auto-minimo")
	async def tragamonedas(interaction: discord.Interaction, cantidad: Optional[str] = None):
		await _run_slots(interaction, cantidad)

	@bot.tree.command(name="tm", description="Alias de /tragamonedas")
	@app_commands.describe(cantidad="Cantidad a apostar, 'all' o vacio para auto-minimo")
	async def tm(interaction: discord.Interaction, cantidad: Optional[str] = None):
		await _run_slots(interaction, cantidad)


async def _run_slots(interaction: discord.Interaction, cantidad: Optional[str]) -> None:
	economy_config = get_economy_config(interaction.guild.id)
	currency_name = economy_config.get_currency_name()
	currency_symbol = economy_config.get_currency_symbol()

	user, _, _ = get_or_create_discord_user(
		discord_id=str(interaction.user.id),
		discord_username=interaction.user.name,
		avatar_url=str(interaction.user.display_avatar.url)
	)

	# Cargar configuracion de slots
	config = games_config.get_slots_config()
	min_limit = float(config.get("min_limit", 0.0) or 0.0)
	max_limit = float(config.get("max_limit", 0.0) or 0.0)
	cooldown_seconds = int(config.get("cooldown", 0) or 0)

	# Verificar cooldown
	can_play, remaining = cooldown_manager.check_cooldown(
		str(interaction.user.id), "slots", cooldown_seconds
	)
	if not can_play:
		await _send_cooldown_error(interaction, remaining)
		return

	current_balance = _get_current_balance(user.user_id)

	if cantidad is None:
		bet_amount = _resolve_default_bet_amount(min_limit)
	else:
		bet_amount, error = _parse_bet_amount(cantidad, current_balance)
		if error:
			await interaction.response.send_message(error, ephemeral=True)
			return

	# Verificar limite inferior
	if min_limit > 0 and bet_amount < min_limit:
		await _send_min_limit_error(interaction, bet_amount, min_limit, currency_symbol)
		return

	# Verificar limite superior
	if max_limit > 0 and bet_amount > max_limit:
		await _send_limit_error(interaction, bet_amount, max_limit, currency_symbol)
		return

	insufficient = _ensure_sufficient_balance(
		current_balance,
		bet_amount,
		currency_name,
		currency_symbol
	)
	if insufficient:
		await _send_balance_error(interaction, insufficient, currency_symbol)
		return

	is_valid, message = slots_master.validate_gamble(current_balance, bet_amount)
	if not is_valid:
		await interaction.response.send_message(message, ephemeral=True)
		return

	casino_fund_balance = economy_manager.get_casino_fund_balance()
	if casino_fund_balance <= 0:
		await _send_casino_bankruptcy_error(interaction)
		return

	await interaction.response.defer()

	combo, ganancia_neta, multiplicador, descripcion, es_ganancia, casino_tier = (
		slots_master.spin_slots(bet_amount, casino_fund_balance)
	)

	settlement = _settle_casino_bet(
		user_id=user.user_id,
		delta=ganancia_neta,
		reason="slots",
		interaction=interaction
	)
	if not settlement.get("success"):
		await interaction.followup.send(
			embed=_build_casino_error_embed(str(settlement.get("error", "No se pudo liquidar la jugada."))),
			ephemeral=True,
		)
		return

	cooldown_manager.update_cooldown(str(interaction.user.id), "slots")

	new_balance = float(settlement["user_balance"])
	casino_balance_after = float(settlement["casino_balance_after"])
	casino_tier = casino_master.get_casino_tier(casino_balance_after, bet_amount)

	if settlement.get("bankruptcy_triggered"):
		register_casino_bankruptcy(
			cause_display=interaction.user.mention,
			cause_platform="discord",
			cause_user_id=str(interaction.user.id),
			game_name="slots",
			previous_balance=float(settlement["casino_balance_before"]),
			new_balance=casino_balance_after,
			bet_amount=float(bet_amount),
			net_result=float(ganancia_neta),
		)

	summary = slots_master.get_slot_summary(
		username=interaction.user.name,
		bet_amount=bet_amount,
		combo=combo,
		ganancia_neta=ganancia_neta,
		multiplicador=multiplicador,
		descripcion=descripcion,
		es_ganancia=es_ganancia,
		casino_tier=casino_tier,
		puntos_finales=int(new_balance),
	)

	if summary["color"] == "verde":
		embed_color = 0x00FF00
	elif summary["color"] == "amarillo":
		embed_color = 0xFFFF00
	else:
		embed_color = 0xFF0000

	embed = discord.Embed(
		title="Tragamonedas",
		color=embed_color,
		description=summary["combo_display"],
	)

	embed.add_field(
		name="Linea",
		value=summary["descripcion"],
		inline=False
	)

	embed.add_field(
		name="Apuesta",
		value=f"{bet_amount:,}{currency_symbol}",
		inline=True
	)

	embed.add_field(
		name=summary["ganancia_perdida_label"],
		value=f"{summary['ganancia_perdida_texto']}{currency_symbol}",
		inline=True
	)

	embed.add_field(
		name="Saldo",
		value=f"{int(new_balance):,}{currency_symbol}",
		inline=True
	)

	if settlement.get("bankruptcy_triggered"):
		embed.add_field(
			name="🚨 Evento crítico",
			value="Esta tirada dejó al casino en bancarrota. Las tiradas han quedado suspendidas hasta nuevo aviso",
			inline=False,
		)

	embed.set_footer(text=f"@{interaction.user.name}")
	embed.timestamp = datetime.now(timezone.utc)

	await interaction.followup.send(embed=embed)


def _resolve_default_bet_amount(min_limit: float) -> int:
	"""Apuesta por defecto para comando sin cantidad: max(min_limit, 5)."""
	return int(max(float(min_limit or 0.0), 5.0))


def _parse_bet_amount(value: str, current_balance: float) -> tuple[Optional[int], Optional[str]]:
	raw = value.strip().lower()
	if raw == "all":
		return int(current_balance), None

	try:
		amount = int(float(raw))
	except ValueError:
		return None, "❌ Cantidad invalida. Usa un numero o 'all'."

	return amount, None


def _ensure_sufficient_balance(
	current_balance: float,
	bet_amount: int,
	currency_name: str,
	currency_symbol: str
) -> Optional[str]:
	if current_balance <= 0:
		return (
			f"No tienes {currency_name} suficiente para apostar. "
			f"Tienes {int(current_balance):,} {currency_symbol} y necesitas {bet_amount:,} {currency_symbol}."
		)
	if bet_amount > current_balance:
		faltan = int(bet_amount - current_balance)
		return (
			f"❌No tienes {currency_name} suficiente para esa apuesta. "
			f"Tienes {int(current_balance):,} {currency_symbol} y te faltan {faltan:,} {currency_symbol}."
		)
	return None


async def _send_balance_error(
	interaction: discord.Interaction,
	message: str,
	currency_symbol: str
) -> None:
	embed = discord.Embed(
		title="Saldo insuficiente",
		description=message,
		color=discord.Color.red()
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)


async def _send_cooldown_error(
	interaction: discord.Interaction,
	remaining_seconds: float
) -> None:
	minutes = int(remaining_seconds // 60)
	seconds = int(remaining_seconds % 60)
	if minutes > 0:
		time_str = f"{minutes}m {seconds}s"
	else:
		time_str = f"{seconds}s"

	embed = discord.Embed(
		title="⏳ Cooldown activo",
		description=f"Debes esperar **{time_str}** antes de jugar de nuevo.",
		color=discord.Color.orange()
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)


async def _send_limit_error(
	interaction: discord.Interaction,
	bet_amount: int,
	limit: float,
	currency_symbol: str
) -> None:
	embed = discord.Embed(
		title="❌ Limite excedido",
		description=(
			f"La apuesta maxima es **{int(limit):,}{currency_symbol}**.\n"
			f"Intentaste apostar **{bet_amount:,}{currency_symbol}**."
		),
		color=discord.Color.red()
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)


async def _send_min_limit_error(
	interaction: discord.Interaction,
	bet_amount: int,
	min_limit: float,
	currency_symbol: str
) -> None:
	embed = discord.Embed(
		title="❌ Apuesta demasiado baja",
		description=(
			f"La apuesta minima es **{int(min_limit):,}{currency_symbol}**.\n"
			f"Intentaste apostar **{bet_amount:,}{currency_symbol}**."
		),
		color=discord.Color.red()
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)


def _settle_casino_bet(
	user_id: int,
	delta: float,
	reason: str,
	interaction: discord.Interaction
) -> dict:
	return economy_manager.settle_casino_bet(
		user_id=user_id,
		delta=delta,
		reason=reason,
		platform="discord",
		guild_id=str(interaction.guild_id) if interaction.guild_id else None,
		channel_id=str(interaction.channel_id) if interaction.channel_id else None,
		source_id=f"slots:{interaction.id}",
		allow_negative_casino_fund=True,
	)


def _build_casino_error_embed(error_message: str) -> discord.Embed:
	return discord.Embed(
		title="🎰 Operación del casino cancelada",
		description=error_message,
		color=discord.Color.red(),
	)


async def _send_casino_bankruptcy_error(interaction: discord.Interaction) -> None:
	state = get_casino_bankruptcy_state()
	cause_display = str(state.get("cause_display") or "un jugador")
	game_name = str(state.get("game_name") or "casino").upper()

	embed = discord.Embed(
		title="🎰 Casino En Bancarrota",
		description="El fondo del casino está agotado. Las mesas no aceptan mas apuestas hasta que se recarguen los fondos.",
		color=discord.Color.red(),
	)
	embed.add_field(name="Causa registrada", value=cause_display, inline=False)
	embed.add_field(name="Último juego", value=game_name, inline=True)
	await interaction.response.send_message(embed=embed, ephemeral=True)


def _get_current_balance(user_id: int) -> float:
	return float(economy_manager.get_total_balance(user_id))
