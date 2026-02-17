"""
Comandos de tragamonedas.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from backend.database import get_connection
from backend.managers import get_or_create_discord_user
from backend.managers import economy_manager
from backend.services.activities import slots_master, games_config, cooldown_manager
from backend.services.discord_bot.config.economy import get_economy_config


def setup_slots_commands(bot: commands.Bot) -> None:
	"""Registra comandos de tragamonedas"""

	@bot.tree.command(name="tragamonedas", description="Juega a la maquina tragamonedas. Alias: /tm")
	@app_commands.describe(cantidad="Cantidad a apostar o 'all'")
	async def tragamonedas(interaction: discord.Interaction, cantidad: str):
		await _run_slots(interaction, cantidad)

	@bot.tree.command(name="tm", description="Alias de /tragamonedas")
	@app_commands.describe(cantidad="Cantidad a apostar o 'all'")
	async def tm(interaction: discord.Interaction, cantidad: str):
		await _run_slots(interaction, cantidad)


async def _run_slots(interaction: discord.Interaction, cantidad: str) -> None:
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
	limit = config.get("limit", 0.0)
	cooldown_seconds = config.get("cooldown", 0)

	# Verificar cooldown
	can_play, remaining = cooldown_manager.check_cooldown(
		str(interaction.user.id), "slots", cooldown_seconds
	)
	if not can_play:
		await _send_cooldown_error(interaction, remaining)
		return

	current_balance = _get_current_balance(user.user_id)

	bet_amount, error = _parse_bet_amount(cantidad, current_balance)
	if error:
		await interaction.response.send_message(error, ephemeral=True)
		return

	# Verificar limite
	if limit > 0 and bet_amount > limit:
		await _send_limit_error(interaction, bet_amount, limit, currency_symbol)
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

	await interaction.response.defer()

	combo, ganancia_neta, multiplicador, descripcion, es_ganancia, luck_multiplier = (
		slots_master.spin_slots(bet_amount, str(interaction.user.id))
	)

	# Actualizar cooldown
	cooldown_manager.update_cooldown(str(interaction.user.id), "slots")

	new_balance = _apply_balance_delta(
		user_id=user.user_id,
		delta=ganancia_neta,
		reason="slots",
		interaction=interaction
	)

	if es_ganancia:
		slots_master.reset_user_luck_multiplier(str(interaction.user.id))
	else:
		slots_master.increment_user_luck_multiplier(str(interaction.user.id), 0.1)

	summary = slots_master.get_slot_summary(
		username=interaction.user.name,
		bet_amount=bet_amount,
		combo=combo,
		ganancia_neta=ganancia_neta,
		multiplicador=multiplicador,
		descripcion=descripcion,
		es_ganancia=es_ganancia,
		luck_multiplier=luck_multiplier,
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

	embed.set_footer(text=f"@{interaction.user.name}")
	embed.timestamp = datetime.now(timezone.utc)

	await interaction.followup.send(embed=embed)


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


def _apply_balance_delta(
	user_id: int,
	delta: float,
	reason: str,
	interaction: discord.Interaction
) -> float:
	conn = get_connection()
	try:
		economy_manager._ensure_wallet_tables(conn)
		conn.execute("BEGIN IMMEDIATE")
		now_iso = datetime.utcnow().isoformat()

		conn.execute(
			"INSERT INTO wallets (user_id, balance, created_at, updated_at) VALUES (?, 0, ?, ?) "
			"ON CONFLICT(user_id) DO NOTHING",
			(user_id, now_iso, now_iso),
		)

		conn.execute(
			"UPDATE wallets SET balance = balance + ?, updated_at = ? WHERE user_id = ?",
			(delta, now_iso, user_id),
		)

		conn.execute(
			"""
			INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, channel_id, source_id, created_at)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?)
			""",
			(
				user_id,
				delta,
				reason,
				"discord",
				str(interaction.guild_id) if interaction.guild_id else None,
				str(interaction.channel_id) if interaction.channel_id else None,
				f"slots:{interaction.id}",
				now_iso,
			),
		)

		row = conn.execute(
			"SELECT balance FROM wallets WHERE user_id = ?",
			(user_id,)
		).fetchone()
		conn.commit()

		return float(row["balance"] if row else 0)
	except Exception:
		conn.rollback()
		raise
	finally:
		conn.close()


def _get_current_balance(user_id: int) -> float:
	conn = get_connection()
	try:
		economy_manager._ensure_wallet_tables(conn)
		row = conn.execute(
			"SELECT balance FROM wallets WHERE user_id = ?",
			(user_id,)
		).fetchone()
		return float(row["balance"]) if row else 0.0
	finally:
		conn.close()
