"""
Comandos generales para PowerBot Discord.
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from backend.managers.user_lookup_manager import find_user_by_discord_id, find_user_by_global_id
from backend.managers.economy_manager import get_user_balance_by_id
from backend.managers import inventory_manager


def setup_general_commands(bot: commands.Bot) -> None:
	"""Registra comandos generales"""

	@bot.tree.command(
		name="id",
		description="Ver informacion de un usuario por @usuario o ID universal"
	)
	@app_commands.describe(
		target="Usuario de Discord a consultar",
		user_id="ID universal del usuario a consultar"
	)
	async def id_command(
		interaction: discord.Interaction,
		target: Optional[discord.User] = None,
		user_id: Optional[int] = None
	):
		"""
		Comando /id con 2 modos de uso:
		1. /id @usuario
		2. /id user_id:<ID>
		"""
		await interaction.response.defer()

		if target is None and user_id is None:
			target = interaction.user

		if target is not None:
			lookup = find_user_by_discord_id(str(target.id))
			if not lookup:
				embed = discord.Embed(
					title="❌ Usuario no encontrado",
					description=f"No existe registro para {target.mention}.",
					color=discord.Color.red()
				)
				await interaction.followup.send(embed=embed, ephemeral=True)
				return
			display_name = target.display_name
			avatar_url = str(target.display_avatar.url)
		else:
			lookup = find_user_by_global_id(user_id)
			if not lookup:
				embed = discord.Embed(
					title="❌ Usuario no encontrado",
					description=f"No existe usuario con ID universal: {user_id}",
					color=discord.Color.red()
				)
				await interaction.followup.send(embed=embed, ephemeral=True)
				return
			display_name = lookup.display_name
			avatar_url = None
			if lookup.discord_profile and lookup.discord_profile.avatar_url:
				avatar_url = lookup.discord_profile.avatar_url

		balance = get_user_balance_by_id(lookup.user_id)
		points = balance.get("global_points", 0) if balance.get("user_exists") else 0
		points = round(float(points), 2)

		inventory_stats = inventory_manager.get_inventory_stats(lookup.user_id)
		total_quantity = inventory_stats.get("total_quantity", 0)

		platforms = []
		if lookup.has_discord:
			platforms.append("Discord")
		if lookup.has_youtube:
			platforms.append("YouTube")

		platforms_text = " y ".join(platforms) if platforms else "Sin plataformas"

		embed = discord.Embed(
			title=f"🧾 ID de {display_name}",
			description=f"**ID Universal:** `{lookup.user_id}`",
			color=discord.Color.blue()
		)

		embed.add_field(
			name="💰 Puntos",
			value=f"{points:,.2f}",
			inline=True
		)
		embed.add_field(
			name="🎒 Inventario",
			value=f"{total_quantity} items",
			inline=True
		)
		embed.add_field(
			name="🔗 Plataformas",
			value=platforms_text,
			inline=False
		)

		if lookup.discord_profile:
			discord_name = lookup.discord_profile.discord_username or "Desconocido"
			discord_id = lookup.discord_profile.discord_id
			embed.add_field(
				name="Discord",
				value=f"{discord_name} (`{discord_id}`)",
				inline=False
			)

		if avatar_url:
			embed.set_thumbnail(url=avatar_url)

		await interaction.followup.send(embed=embed)
