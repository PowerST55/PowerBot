"""
Comando /top para ranking de puntos.
"""
import discord
from discord import app_commands
from discord.ext import commands

from backend.database import get_connection
from backend.managers.economy_manager import get_global_leaderboard
from backend.managers.user_manager import get_discord_profile_by_user_id
from backend.services.discord_bot.config.economy import get_economy_config


def setup_top_commands(bot: commands.Bot) -> None:
	"""Registra comandos de top"""

	@bot.tree.command(name="top", description="Muestra el top 10 de usuarios con mas puntos")
	async def top(interaction: discord.Interaction):
		await interaction.response.defer()

		economy_config = get_economy_config(interaction.guild.id)
		currency_name = economy_config.get_currency_name()
		currency_symbol = economy_config.get_currency_symbol()

		leaderboard = get_global_leaderboard(limit=10)
		if not leaderboard:
			embed = discord.Embed(
				title="Top 10",
				description="No hay datos disponibles.",
				color=discord.Color.blue()
			)
			await interaction.followup.send(embed=embed)
			return

		lines = []
		for idx, row in enumerate(leaderboard, start=1):
			username = row.get("username") or f"User {row.get('user_id')}"
			balance = row.get("balance", 0)
			discord_profile = get_discord_profile_by_user_id(row.get("user_id"))
			if discord_profile:
				display_name = f"<@{discord_profile.discord_id}>"
			else:
				display_name = username
			lines.append(
				f"`#{idx:02d}` {display_name}\n"
				f"    └─ `ID:{row.get('user_id')}`  •  **{balance:,.1f}{currency_symbol}**"
			)

		user_position, user_points = _get_user_rank_and_points(interaction.user.id)
		if user_position:
			if user_position <= 10:
				footer_text = (
					f"🎉 Estas en el top 10  •  Posicion: #{user_position}  •  "
					f"Puntos: {user_points:,.1f}{currency_symbol}"
				)
			else:
				footer_text = (
					f"Tu posicion: #{user_position}  •  "
					f"Puntos: {user_points:,.1f}{currency_symbol}"
				)
		else:
			footer_text = "No estas en el ranking"

		embed = discord.Embed(
			title=f"💰 Magnates del {currency_name} 💰",
			description="━━━━━━━━━━━━━━━━━━━━━━\nLos 10 usuarios mas ricos",
			color=0xFFD700
		)
		embed.add_field(
			name="",
			value="\n".join(lines),
			inline=False
		)
		embed.add_field(
			name="",
			value="━━━━━━━━━━━━━━━━━━━━━━",
			inline=False
		)
		embed.set_footer(text=footer_text)

		await interaction.followup.send(embed=embed)


def _get_user_rank_and_points(discord_id: int) -> tuple[int | None, int]:
	conn = get_connection()
	try:
		row = conn.execute(
			"SELECT user_id FROM discord_profile WHERE discord_id = ?",
			(str(discord_id),)
		).fetchone()
		if not row:
			return None, 0

		user_id = row["user_id"]
		points_row = conn.execute(
			"SELECT balance FROM wallets WHERE user_id = ?",
			(user_id,)
		).fetchone()
		points = points_row["balance"] if points_row else 0

		pos_row = conn.execute(
			"""
			SELECT 1 + COUNT(*) as rank
			FROM wallets
			WHERE balance > ?
			""",
			(points,)
		).fetchone()
		return (pos_row["rank"] if pos_row else None), points
	finally:
		conn.close()
