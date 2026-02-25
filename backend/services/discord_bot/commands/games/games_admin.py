"""
Comandos administrativos de juegos.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from backend.services.activities import games_config
from backend.services.discord_bot.bot_logging import log_economy


def setup_games_admin_commands(bot: commands.Bot) -> None:
	"""Registra comandos de administracion de juegos"""

	set_group = _get_or_create_set_group(bot)

	@set_group.command(name="gamble", description="Configura limites y cooldown de gamble")
	@app_commands.describe(
		min_limit="Limite minimo por apuesta (0 = sin limite)",
		max_limit="Limite maximo por apuesta (0 = sin limite)",
		cooldown="Cooldown en segundos"
	)
	async def set_gamble(
		interaction: discord.Interaction,
		min_limit: float,
		max_limit: float,
		cooldown: int
	):
		if not _is_moderator(interaction):
			await _deny_permission(interaction)
			return

		if min_limit < 0 or max_limit < 0 or cooldown < 0:
			await _send_error(interaction, "Limites y cooldown deben ser >= 0.")
			return

		if max_limit > 0 and min_limit > max_limit:
			await _send_error(interaction, "El limite inferior no puede ser mayor que el limite superior.")
			return

		result = games_config.set_gamble_config(min_limit, max_limit, cooldown)
		embed = discord.Embed(
			title="Gamble actualizado",
			description=(
				f"Limite inferior: {result['min_limit']}\n"
				f"Limite superior: {result['max_limit']}\n"
				f"Cooldown: {result['cooldown']}s"
			),
			color=discord.Color.green()
		)
		await interaction.response.send_message(embed=embed, ephemeral=True)

		if interaction.guild is not None:
			await log_economy(
				bot,
				interaction.guild.id,
				"Configuración de gamble actualizada",
				f"{interaction.user.mention} actualizó la configuración de gamble.",
				fields={
					"Limite inferior": str(result["min_limit"]),
					"Limite superior": str(result["max_limit"]),
					"Cooldown": f"{result['cooldown']}s",
				},
				user=interaction.user,
			)

	@set_group.command(name="slots", description="Configura limites y cooldown de tragamonedas")
	@app_commands.describe(
		min_limit="Limite minimo por apuesta (0 = sin limite)",
		max_limit="Limite maximo por apuesta (0 = sin limite)",
		cooldown="Cooldown en segundos"
	)
	async def set_slots(
		interaction: discord.Interaction,
		min_limit: float,
		max_limit: float,
		cooldown: int
	):
		if not _is_moderator(interaction):
			await _deny_permission(interaction)
			return

		if min_limit < 0 or max_limit < 0 or cooldown < 0:
			await _send_error(interaction, "Limites y cooldown deben ser >= 0.")
			return

		if max_limit > 0 and min_limit > max_limit:
			await _send_error(interaction, "El limite inferior no puede ser mayor que el limite superior.")
			return

		result = games_config.set_slots_config(min_limit, max_limit, cooldown)
		embed = discord.Embed(
			title="Tragamonedas actualizado",
			description=(
				f"Limite inferior: {result['min_limit']}\n"
				f"Limite superior: {result['max_limit']}\n"
				f"Cooldown: {result['cooldown']}s"
			),
			color=discord.Color.green()
		)
		await interaction.response.send_message(embed=embed, ephemeral=True)

		if interaction.guild is not None:
			await log_economy(
				bot,
				interaction.guild.id,
				"Configuración de tragamonedas actualizada",
				f"{interaction.user.mention} actualizó la configuración de tragamonedas.",
				fields={
					"Limite inferior": str(result["min_limit"]),
					"Limite superior": str(result["max_limit"]),
					"Cooldown": f"{result['cooldown']}s",
				},
				user=interaction.user,
			)


def _get_or_create_set_group(bot: commands.Bot) -> app_commands.Group:
	existing = bot.tree.get_command("set")
	if isinstance(existing, app_commands.Group):
		return existing

	group = app_commands.Group(name="set", description="Configuracion del servidor")
	bot.tree.add_command(group)
	return group


def _is_moderator(interaction: discord.Interaction) -> bool:
	perms = interaction.user.guild_permissions
	return perms.administrator or perms.manage_guild


async def _deny_permission(interaction: discord.Interaction) -> None:
	embed = discord.Embed(
		title="Acceso denegado",
		description="Solo moderadores pueden usar este comando.",
		color=discord.Color.red()
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)


async def _send_error(interaction: discord.Interaction, message: str) -> None:
	embed = discord.Embed(
		title="Error",
		description=message,
		color=discord.Color.red()
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)
