"""
Comandos de administración y uso de mina.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from backend.services.discord_bot.config.mine_config import get_mine_config
from backend.services.discord_bot.economy.mine import send_mine_panel


def setup_mine_commands(bot: commands.Bot) -> None:
	"""Registra comandos /mine."""

	mine_group = app_commands.Group(name="mine", description="Sistema de mina")

	@mine_group.command(name="panel", description="Publica el panel de mina con botón")
	async def mine_panel(interaction: discord.Interaction):
		await send_mine_panel(interaction)

	@mine_group.command(name="rate", description="Configura cooldown global de mina en segundos (solo admin)")
	@app_commands.describe(rate="Cooldown en segundos")
	async def mine_rate(interaction: discord.Interaction, rate: int):
		if not interaction.user.guild_permissions.administrator:
			await _deny_permission(interaction)
			return

		if rate <= 0:
			await interaction.response.send_message("El rate debe ser mayor a 0 segundos.", ephemeral=True)
			return

		config = get_mine_config(interaction.guild.id)
		config.set_rate_seconds(rate)

		embed = discord.Embed(
			title="✅ Rate actualizado",
			description=f"Nuevo cooldown de mina: `{rate}` segundos",
			color=discord.Color.green(),
		)
		await interaction.response.send_message(embed=embed, ephemeral=True)

	@mine_group.command(name="add", description="Agrega ítem de mina (solo admin)")
	@app_commands.describe(
		name="Nombre del ítem",
		price="Valor fijo del ítem. Puede ser negativo para objetos malos",
		probability="Probabilidad 1-100",
		ip_percent="Opcional: porcentaje del patrimonio a descontar si el ítem es negativo",
		custom_text="Opcional: texto personalizado para el mensaje al encontrar este ítem",
	)
	async def mine_add(
		interaction: discord.Interaction,
		name: str,
		price: float,
		probability: int,
		ip_percent: float = 0.0,
		custom_text: str = "",
	):
		if not interaction.user.guild_permissions.administrator:
			await _deny_permission(interaction)
			return

		if price == 0:
			await interaction.response.send_message("El precio no puede ser 0.", ephemeral=True)
			return
		if probability < 1 or probability > 100:
			await interaction.response.send_message("La probabilidad debe estar entre 1 y 100.", ephemeral=True)
			return
		if ip_percent < 0:
			await interaction.response.send_message("El ip% no puede ser negativo.", ephemeral=True)
			return

		config = get_mine_config(interaction.guild.id)
		ok = config.add_item(
			name=name,
			price=price,
			probability=probability,
			ip_percent=ip_percent,
			custom_text=custom_text,
		)
		if not ok:
			await interaction.response.send_message(
				f"No se pudo agregar `{name}`. Ya existe o es inválido.",
				ephemeral=True,
			)
			return

		embed = discord.Embed(
			title="✅ Ítem agregado",
			description=f"Se agregó `{name}` a la mina.",
			color=discord.Color.red() if price < 0 else discord.Color.green(),
		)
		embed.add_field(name="Precio", value=f"`{price:,.2f}`", inline=True)
		embed.add_field(name="Probabilidad", value=f"`{probability}%`", inline=True)
		embed.add_field(name="ip%", value=f"`{ip_percent:,.2f}%`", inline=True)
		if custom_text.strip():
			embed.add_field(name="Texto personalizado", value=f"`{custom_text.strip()}`", inline=False)
		await interaction.response.send_message(embed=embed, ephemeral=True)

	@mine_group.command(name="remove", description="Elimina ítem de mina (solo admin)")
	@app_commands.describe(name="Nombre del ítem a eliminar")
	async def mine_remove(interaction: discord.Interaction, name: str):
		if not interaction.user.guild_permissions.administrator:
			await _deny_permission(interaction)
			return

		config = get_mine_config(interaction.guild.id)
		ok = config.remove_item(name)
		if not ok:
			await interaction.response.send_message(f"No existe un ítem llamado `{name}`.", ephemeral=True)
			return

		await interaction.response.send_message(f"✅ Ítem `{name}` eliminado de la mina.", ephemeral=True)

	@mine_group.command(name="list", description="Lista ítems de mina configurados")
	async def mine_list(interaction: discord.Interaction):
		config = get_mine_config(interaction.guild.id)
		items = config.list_items()

		embed = discord.Embed(
			title="⛏️ Ítems de mina",
			color=discord.Color.blue(),
		)
		embed.add_field(name="Rate", value=f"`{config.get_rate_seconds()}s`", inline=True)
		mine_channel_id = config.get_mine_channel_id()
		embed.add_field(
			name="Canal",
			value=(f"<#{mine_channel_id}>" if mine_channel_id else "`No configurado`"),
			inline=True,
		)

		if items:
			sorted_items = sorted(
				items,
				key=lambda item: float(item.get("probability", 0) or 0),
				reverse=True,
			)
			rows = []
			for item in sorted_items:
				custom_text = str(item.get("custom_text") or "").strip()
				row = (
					f"• `{item.get('name')} | {float(item.get('price', 0)):,.2f} | "
					f"{int(item.get('probability', 0))}% | "
					f"ip {float(item.get('ip_percent', item.get('ip%', 0.0)) or 0.0):,.2f}%"
				)
				if custom_text:
					row = f"{row} | txt {custom_text}`"
				rows.append(row)
			embed.description = "\n".join(rows)
		else:
			embed.description = "No hay ítems configurados."

		await interaction.response.send_message(embed=embed, ephemeral=True)

	bot.tree.add_command(mine_group)


async def _deny_permission(interaction: discord.Interaction) -> None:
	embed = discord.Embed(
		title="❌ Acceso denegado",
		description="Solo administradores pueden usar este comando.",
		color=discord.Color.red(),
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)
