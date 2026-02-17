"""
Comandos de administracion de economia para PowerBot Discord.
"""
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from backend.database import get_connection
from backend.managers import get_or_create_discord_user, get_user_by_id
from backend.managers import economy_manager
from backend.services.discord_bot.config.economy import get_economy_config


def setup_admin_economy_commands(bot: commands.Bot) -> None:
	"""Registra comandos de economia para moderacion"""

	@bot.tree.command(name="aps", description="Agrega puntos a un usuario (solo admin)")
	@app_commands.describe(
		target="Usuario de Discord a modificar",
		user_id="ID universal del usuario",
		cantidad="Cantidad a agregar (hasta 2 decimales)"
	)
	async def aps(
		interaction: discord.Interaction,
		target: Optional[discord.User] = None,
		user_id: Optional[int] = None,
		cantidad: str = "0"
	):
		if not interaction.user.guild_permissions.administrator:
			await _deny_permission(interaction)
			return

		await interaction.response.defer()

		if target is None and user_id is None:
			target = interaction.user

		economy_config = get_economy_config(interaction.guild.id)
		currency_name = economy_config.get_currency_name()
		currency_symbol = economy_config.get_currency_symbol()

		lookup, display_name = _resolve_target(target, user_id)
		if lookup is None:
			await _send_error(interaction, "Objetivo no encontrado. Usa @usuario o ID universal.")
			return

		amount, error = _parse_amount(cantidad, allow_all=False)
		if error:
			await _send_error(interaction, error)
			return

		new_balance = _apply_balance_delta(
			user_id=lookup,
			delta=amount,
			reason="admin_add_points",
			interaction=interaction
		)

		embed = discord.Embed(
			title="✅ Puntos agregados",
			description=(
				f"Se agregaron **{amount:.2f}{currency_symbol}** a **{display_name}**\n"
				f"Nuevo balance: **{new_balance:.2f}{currency_symbol}**\n"
				f"Moneda: **{currency_name}**"
			),
			color=discord.Color.green()
		)
		await interaction.followup.send(embed=embed)

	@bot.tree.command(name="rps", description="Resta puntos a un usuario (solo admin)")
	@app_commands.describe(
		target="Usuario de Discord a modificar",
		user_id="ID universal del usuario",
		cantidad="Cantidad a restar (hasta 2 decimales) o 'all'"
	)
	async def rps(
		interaction: discord.Interaction,
		target: Optional[discord.User] = None,
		user_id: Optional[int] = None,
		cantidad: str = "0"
	):
		if not interaction.user.guild_permissions.administrator:
			await _deny_permission(interaction)
			return

		await interaction.response.defer()

		if target is None and user_id is None:
			target = interaction.user

		economy_config = get_economy_config(interaction.guild.id)
		currency_name = economy_config.get_currency_name()
		currency_symbol = economy_config.get_currency_symbol()

		lookup, display_name = _resolve_target(target, user_id)
		if lookup is None:
			await _send_error(interaction, "Objetivo no encontrado. Usa @usuario o ID universal.")
			return

		amount, error = _parse_amount(cantidad, allow_all=True)
		if error:
			await _send_error(interaction, error)
			return

		if amount is None:
			current_balance = _get_current_balance(lookup)
			if current_balance <= 0:
				await _send_error(interaction, "El usuario no tiene puntos para remover.")
				return
			amount = current_balance

		new_balance = _apply_balance_delta(
			user_id=lookup,
			delta=-amount,
			reason="admin_remove_points",
			interaction=interaction
		)

		embed = discord.Embed(
			title="⚠️ Puntos removidos",
			description=(
				f"Se removieron **{amount:.2f}{currency_symbol}** a **{display_name}**\n"
				f"Nuevo balance: **{new_balance:.2f}{currency_symbol}**\n"
				f"Moneda: **{currency_name}**"
			),
			color=discord.Color.red()
		)
		await interaction.followup.send(embed=embed)


def _resolve_target(
	target: Optional[discord.User],
	user_id: Optional[int]
) -> Tuple[Optional[int], Optional[str]]:
	if target is not None:
		user, _, _ = get_or_create_discord_user(
			discord_id=str(target.id),
			discord_username=target.name,
			avatar_url=str(target.display_avatar.url)
		)
		return user.user_id, target.display_name

	if user_id is not None:
		user = get_user_by_id(user_id)
		if not user:
			return None, None
		return user.user_id, user.username

	return None, None


def _parse_amount(value: str, allow_all: bool) -> Tuple[Optional[float], Optional[str]]:
	raw = value.strip().lower()
	if allow_all and raw == "all":
		return None, None

	try:
		amount = Decimal(raw)
	except (InvalidOperation, ValueError):
		return None, "La cantidad debe ser un numero valido."

	if amount <= 0:
		return None, "La cantidad debe ser mayor a 0."

	if amount.as_tuple().exponent < -2:
		return None, "La cantidad debe tener maximo 2 decimales."

	return float(amount.quantize(Decimal("0.01"))), None


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
				f"admin:{interaction.id}",
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


async def _deny_permission(interaction: discord.Interaction) -> None:
	embed = discord.Embed(
		title="❌ Acceso denegado",
		description="Solo administradores pueden usar este comando.",
		color=discord.Color.red()
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)


async def _send_error(interaction: discord.Interaction, message: str) -> None:
	embed = discord.Embed(
		title="❌ Error",
		description=message,
		color=discord.Color.red()
	)
	await interaction.followup.send(embed=embed, ephemeral=True)
