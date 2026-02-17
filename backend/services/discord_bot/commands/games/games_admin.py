"""
Comandos administrativos de juegos.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from backend.services.activities import games_config


def setup_games_admin_commands(bot: commands.Bot) -> None:
	"""Registra comandos de administracion de juegos"""

	set_group = _get_or_create_set_group(bot)

	@set_group.command(name="gamble", description="Configura limite y cooldown de gamble")
	@app_commands.describe(
		limit="Limite maximo por apuesta",
		cooldown="Cooldown en segundos"
	)
	async def set_gamble(
		interaction: discord.Interaction,
		limit: float,
		cooldown: int
	):
		if not _is_moderator(interaction):
			await _deny_permission(interaction)
			return

		if limit < 0 or cooldown < 0:
			await _send_error(interaction, "Limit y cooldown deben ser >= 0.")
			return

		result = games_config.set_gamble_config(limit, cooldown)
		embed = discord.Embed(
			title="Gamble actualizado",
			description=(
				f"Limit: {result['limit']}\n"
				f"Cooldown: {result['cooldown']}s"
			),
			color=discord.Color.green()
		)
		await interaction.response.send_message(embed=embed, ephemeral=True)

	@set_group.command(name="slots", description="Configura limite y cooldown de tragamonedas")
	@app_commands.describe(
		limit="Limite maximo por apuesta",
		cooldown="Cooldown en segundos"
	)
	async def set_slots(
		interaction: discord.Interaction,
		limit: float,
		cooldown: int
	):
		if not _is_moderator(interaction):
			await _deny_permission(interaction)
			return

		if limit < 0 or cooldown < 0:
			await _send_error(interaction, "Limit y cooldown deben ser >= 0.")
			return

		result = games_config.set_slots_config(limit, cooldown)
		embed = discord.Embed(
			title="Tragamonedas actualizado",
			description=(
				f"Limit: {result['limit']}\n"
				f"Cooldown: {result['cooldown']}s"
			),
			color=discord.Color.green()
		)
		await interaction.response.send_message(embed=embed, ephemeral=True)


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
