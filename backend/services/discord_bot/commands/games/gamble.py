"""
Comando /g para gamble.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from backend.database import get_connection
from backend.managers import get_or_create_discord_user
from backend.managers import economy_manager
from backend.services.activities import gamble_master, games_config, cooldown_manager
from backend.services.discord_bot.config.economy import get_economy_config


def setup_gamble_commands(bot: commands.Bot) -> None:
	"""Registra comandos de gamble"""

	@bot.tree.command(name="g", description="Apuesta puntos para ganar o perder")
	@app_commands.describe(cantidad="Cantidad a apostar o 'all'")
	async def g(interaction: discord.Interaction, cantidad: str):
		economy_config = get_economy_config(interaction.guild.id)
		currency_name = economy_config.get_currency_name()
		currency_symbol = economy_config.get_currency_symbol()

		user, _, _ = get_or_create_discord_user(
			discord_id=str(interaction.user.id),
			discord_username=interaction.user.name,
			avatar_url=str(interaction.user.display_avatar.url)
		)

		# Cargar configuracion de gamble
		config = games_config.get_gamble_config()
		limit = config.get("limit", 0.0)
		cooldown_seconds = config.get("cooldown", 0)

		# Verificar cooldown
		can_play, remaining = cooldown_manager.check_cooldown(
			str(interaction.user.id), "gamble", cooldown_seconds
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

		is_valid, message = gamble_master.validate_gamble(current_balance, bet_amount)
		if not is_valid:
			await interaction.response.send_message(message, ephemeral=True)
			return

		await interaction.response.defer()

		roll, ganancia_neta, multiplicador, rango = gamble_master.calculate_gamble_result(bet_amount)

		# Actualizar cooldown
		cooldown_manager.update_cooldown(str(interaction.user.id), "gamble")

		new_balance = _apply_balance_delta(
			user_id=user.user_id,
			delta=ganancia_neta,
			reason="gamble",
			interaction=interaction
		)

		summary = gamble_master.get_gamble_summary(
			username=interaction.user.name,
			bet_amount=bet_amount,
			roll=roll,
			ganancia_neta=ganancia_neta,
			multiplicador=multiplicador,
			rango=rango,
			puntos_finales=new_balance
		)

		if summary["color"] == "verde":
			embed_color = 0x00FF00
		elif summary["color"] == "amarillo":
			embed_color = 0xFFFF00
		else:
			embed_color = 0xFF0000

		embed = discord.Embed(
			title=f"🎰 {summary['resultado_emoji']} Resultado del Gamble",
			color=embed_color
		)

		embed.add_field(
			name="🎲 Numero obtenido",
			value=f"**{roll}** / 100",
			inline=True
		)

		embed.add_field(
			name="💰 Apuesta",
			value=f"**{bet_amount:,.2f}{currency_symbol}**",
			inline=True
		)

		embed.add_field(
			name="📊 Multiplicador",
			value=f"**{multiplicador:.1f}x**",
			inline=True
		)

		embed.add_field(
			name="🎯 Categoria",
			value=rango,
			inline=False
		)

		embed.add_field(
			name="💵 Ganancia/Perdida",
			value=f"**{summary['ganancia_texto']}{currency_symbol}**",
			inline=True
		)

		embed.add_field(
			name="🏦 Saldo final",
			value=f"**{new_balance:,.2f}{currency_symbol}**",
			inline=True
		)

		embed.set_footer(text=f"Jugador: {interaction.user.name}")
		embed.timestamp = datetime.now(timezone.utc)

		await interaction.followup.send(embed=embed)


def _parse_bet_amount(value: str, current_balance: float) -> tuple[Optional[float], Optional[str]]:
	raw = value.strip().lower()
	if raw == "all":
		return round(float(current_balance), 2), None

	try:
		amount = Decimal(raw)
	except (InvalidOperation, ValueError):
		return None, "❌ Cantidad invalida. Usa un numero o 'all'."

	amount = amount.quantize(Decimal("0.01"))
	return float(amount), None


def _ensure_sufficient_balance(
	current_balance: float,
	bet_amount: float,
	currency_name: str,
	currency_symbol: str
) -> Optional[str]:
	if current_balance <= 0:
		return (
			f"❌No tienes {currency_name} suficiente para apostar. "
			f"Tienes {current_balance:,.2f} {currency_symbol} y necesitas {bet_amount:,.2f} {currency_symbol}."
		)
	if bet_amount > current_balance:
		faltan = bet_amount - current_balance
		return (
			f"❌No tienes {currency_name} suficiente para esa apuesta. "
			f"Tienes {current_balance:,.2f} {currency_symbol} y te faltan {faltan:,.2f} {currency_symbol}."
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
	bet_amount: float,
	limit: float,
	currency_symbol: str
) -> None:
	embed = discord.Embed(
		title="❌ Limite excedido",
		description=(
			f"La apuesta maxima es **{limit:,.2f}{currency_symbol}**.\n"
			f"Intentaste apostar **{bet_amount:,.2f}{currency_symbol}**."
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
				f"gamble:{interaction.id}",
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
