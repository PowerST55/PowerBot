"""
Comandos de vinculación de cuentas para Discord.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from backend.managers.link_manager import create_discord_link_code, unlink_from_discord


def setup_link_commands(bot: commands.Bot) -> None:
	"""Registra comandos slash para vinculación de cuentas."""

	@bot.tree.command(name="vincular", description="Genera un código para vincular Discord con YouTube")
	async def vincular(interaction: discord.Interaction):
		result = create_discord_link_code(
			discord_user_id=str(interaction.user.id),
			discord_user_name=interaction.user.name,
		)

		if not result.success or not result.code:
			embed = discord.Embed(
				title="❌ No se pudo generar el código",
				description=result.message,
				color=discord.Color.red(),
			)
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		embed = discord.Embed(
			title="🔗 Vincular Discord con YouTube",
			description=(
				"Copia y pega este comando en el chat de YouTube para completar la vinculación.\n\n"
				"⏱️ El código expira en 10 minutos o cuando generes uno nuevo."
			),
			color=discord.Color.blurple(),
		)
		embed.add_field(name="Código", value=f"`{result.code}`", inline=False)
		embed.add_field(
			name="Comando listo para copiar",
			value=f"```\n!vincular {result.code}\n```",
			inline=False,
		)
		embed.set_footer(text="Este mensaje es privado y solo tú puedes verlo")

		await interaction.response.send_message(embed=embed, ephemeral=True)

	@bot.tree.command(name="desvincular", description="Desvincula tu cuenta de Discord de YouTube")
	async def desvincular(interaction: discord.Interaction):
		result = unlink_from_discord(str(interaction.user.id))

		if not result.success:
			embed = discord.Embed(
				title="❌ No se pudo desvincular",
				description=result.message,
				color=discord.Color.red(),
			)
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		embed = discord.Embed(
			title="🔓 Cuenta desvinculada",
			description=(
				"Discord quedó desvinculado de YouTube.\n"
				"✅ Discord conserva el saldo total acumulado.\n"
				"⚠️ YouTube quedó reiniciado en 0."
			),
			color=discord.Color.orange(),
		)
		embed.set_footer(text="Puedes volver a vincular con /vincular")
		await interaction.response.send_message(embed=embed, ephemeral=True)
