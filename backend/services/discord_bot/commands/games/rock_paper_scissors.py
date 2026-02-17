"""
Comandos de Piedra Papel Tijeras para PowerBot Discord.
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
from backend.services.activities import ppt_master
from backend.services.discord_bot.config.economy import get_economy_config


class PPTView(discord.ui.View):
	"""View con botones para Piedra Papel Tijeras"""
	def __init__(self, allowed_user_id: int, timeout=180):
		super().__init__(timeout=timeout)
		self.allowed_user_id = allowed_user_id
		self.choice = None
		self.timed_out = False
	
	async def on_timeout(self):
		"""Se ejecuta cuando expira el timeout"""
		self.timed_out = True
		for item in self.children:
			item.disabled = True
	
	@discord.ui.button(label="Piedra", emoji="🪨", style=discord.ButtonStyle.primary)
	async def piedra_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.user.id != self.allowed_user_id:
			await interaction.response.send_message("❌ No puedes interactuar con este juego.", ephemeral=True)
			return
		
		self.choice = "piedra"
		await interaction.response.defer()
		self.stop()
	
	@discord.ui.button(label="Papel", emoji="📄", style=discord.ButtonStyle.success)
	async def papel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.user.id != self.allowed_user_id:
			await interaction.response.send_message("❌ No puedes interactuar con este juego.", ephemeral=True)
			return
		
		self.choice = "papel"
		await interaction.response.defer()
		self.stop()
	
	@discord.ui.button(label="Tijeras", emoji="✂️", style=discord.ButtonStyle.danger)
	async def tijeras_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.user.id != self.allowed_user_id:
			await interaction.response.send_message("❌ No puedes interactuar con este juego.", ephemeral=True)
			return
		
		self.choice = "tijeras"
		await interaction.response.defer()
		self.stop()


class PPTRematchView(discord.ui.View):
	"""View con botón de revancha para Piedra Papel Tijeras"""
	def __init__(self, player1_id: int, player2_id: int, timeout=60):
		super().__init__(timeout=timeout)
		self.player1_id = player1_id
		self.player2_id = player2_id
		self.rematch_accepted = False
		self.rematch_initiator_id = None  # Quien presiona el botón
		self.rematch_interaction = None  # Interacción del botón de revancha
		self.timed_out = False
	
	async def on_timeout(self):
		"""Se ejecuta cuando expira el timeout"""
		self.timed_out = True
		for item in self.children:
			item.disabled = True
	
	@discord.ui.button(label="Revancha", emoji="🔄", style=discord.ButtonStyle.primary)
	async def rematch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		# Solo los jugadores pueden aceptar la revancha
		if interaction.user.id not in [self.player1_id, self.player2_id]:
			await interaction.response.send_message("❌ No participaste en este duelo.", ephemeral=True)
			return
		
		self.rematch_accepted = True
		self.rematch_initiator_id = interaction.user.id  # Guardar quien inició la revancha
		self.rematch_interaction = interaction  # Guardar la interacción del botón
		await interaction.response.send_message("✅ ¡Revancha aceptada!", ephemeral=True)
		self.stop()


def _get_current_balance(user_id: int) -> float:
	"""Obtiene el balance actual de un usuario"""
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


def _apply_balance_delta(user_id: int, delta: float, reason: str, interaction: discord.Interaction) -> float:
	"""Aplica un cambio al balance del usuario y registra la transacción"""
	conn = get_connection()
	try:
		economy_manager._ensure_wallet_tables(conn)
		conn.execute("BEGIN IMMEDIATE")
		
		now = datetime.now(timezone.utc).isoformat()
		
		# Asegurar que el wallet existe
		conn.execute(
			"INSERT INTO wallets (user_id, balance, created_at, updated_at) VALUES (?, 0, ?, ?) "
			"ON CONFLICT(user_id) DO NOTHING",
			(user_id, now, now)
		)
		
		# Actualizar balance
		conn.execute(
			"UPDATE wallets SET balance = balance + ?, updated_at = ? WHERE user_id = ?",
			(delta, now, user_id)
		)
		
		# Registrar en ledger
		conn.execute(
			"""INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, channel_id, created_at)
			   VALUES (?, ?, ?, ?, ?, ?, ?)""",
			(
				user_id,
				delta,
				reason,
				"discord",
				str(interaction.guild.id) if interaction.guild else None,
				str(interaction.channel.id) if interaction.channel else None,
				now
			)
		)
		
		# Obtener nuevo balance
		row = conn.execute(
			"SELECT balance FROM wallets WHERE user_id = ?",
			(user_id,)
		).fetchone()
		
		conn.commit()
		return float(row["balance"]) if row else 0.0
	except Exception:
		conn.rollback()
		raise
	finally:
		conn.close()


async def play_ppt_game(
	interaction: discord.Interaction,
	rival: discord.User,
	bet_amount: float,
	is_rematch: bool = False,
	rematch_initiator_id: int = None
):
	"""Ejecuta el juego de Piedra Papel Tijeras."""
	economy_config = get_economy_config(interaction.guild.id)
	currency_name = economy_config.get_currency_name()
	currency_symbol = economy_config.get_currency_symbol()
	
	# Determinar quien elige primero
	# Si es revancha y hay un iniciador, ese usuario elige primero
	if is_rematch and rematch_initiator_id:
		# El iniciador de la revancha elige primero
		if rematch_initiator_id == interaction.user.id:
			first_player = interaction.user
			second_player = rival
		else:
			first_player = rival
			second_player = interaction.user
	else:
		# Primera partida: quien ejecuta el comando elige primero
		first_player = interaction.user
		second_player = rival
	
	# Asegurar que ambos usuarios estén en el sistema
	player1, _, _ = get_or_create_discord_user(
		discord_id=str(first_player.id),
		discord_username=first_player.name,
		avatar_url=str(first_player.display_avatar.url)
	)
	
	player2, _, _ = get_or_create_discord_user(
		discord_id=str(second_player.id),
		discord_username=second_player.name,
		avatar_url=str(second_player.display_avatar.url)
	)
	
	# Obtener puntos actuales
	player1_points = _get_current_balance(player1.user_id)
	player2_points = _get_current_balance(player2.user_id)
	
	# Validar apuesta
	es_valido, mensaje_error = ppt_master.validate_ppt_game(player1_points, player2_points, bet_amount)
	if not es_valido:
		if is_rematch:
			await interaction.followup.send(mensaje_error, ephemeral=True)
		else:
			await interaction.response.send_message(mensaje_error, ephemeral=True)
		return
	
	# ====== FASE 1: Primer jugador elige (privado) ======
	view_player1 = PPTView(allowed_user_id=first_player.id, timeout=180)
	
	embed_player1 = discord.Embed(
		title="🎮 Piedra, Papel o Tijeras",
		description=f"**Desafío contra {second_player.mention}**\n\n💰 Apuesta: **{bet_amount:,.2f}{currency_symbol}**\n\n🔒 Solo tú puedes ver este mensaje.\nElige tu opción:",
		color=0x5865F2
	)
	embed_player1.set_footer(text="⏱️ Tienes 3 minutos para elegir")
	
	if is_rematch:
		await interaction.followup.send(embed=embed_player1, view=view_player1, ephemeral=True)
	else:
		await interaction.response.send_message(embed=embed_player1, view=view_player1, ephemeral=True)
	
	# Esperar elección del primer jugador
	await view_player1.wait()
	
	if view_player1.timed_out or view_player1.choice is None:
		await interaction.followup.send("⏱️ **Tiempo agotado.** El juego ha sido cancelado.", ephemeral=True)
		return
	
	player1_choice = view_player1.choice
	
	# ====== FASE 2: Segundo jugador elige (público) ======
	view_player2 = PPTView(allowed_user_id=second_player.id, timeout=180)
	
	embed_player2 = discord.Embed(
		title="⚔️ ¡Duelo de Piedra, Papel o Tijeras!",
		description=f"{first_player.mention} te ha retado a un duelo\n\n💰 **Apuesta:** {bet_amount:,.2f}{currency_symbol} cada uno\n⏱️ **Tiempo:** 3 minutos\n\n{second_player.mention}, elige tu opción:",
		color=0xFEE75C
	)
	embed_player2.set_thumbnail(url=second_player.display_avatar.url if second_player.display_avatar else None)
	embed_player2.set_footer(text=f"Desafío iniciado por {first_player.name}")
	
	# Enviar mensaje público
	public_message = await interaction.followup.send(embed=embed_player2, view=view_player2, wait=True)
	
	# Esperar elección del segundo jugador
	await view_player2.wait()
	
	if view_player2.timed_out or view_player2.choice is None:
		embed_timeout = discord.Embed(
			title="⏱️ Tiempo Agotado",
			description=f"{second_player.mention} no respondió a tiempo.\n\nEl duelo ha sido cancelado.",
			color=0xFF6600
		)
		await public_message.edit(embed=embed_timeout, view=None)
		return
	
	player2_choice = view_player2.choice
	
	# ====== FASE 3: Re-validar puntos (anti-exploit) ======
	player1_points_final = _get_current_balance(player1.user_id)
	player2_points_final = _get_current_balance(player2.user_id)
	
	if player1_points_final < bet_amount or player2_points_final < bet_amount:
		embed_error = discord.Embed(
			title="❌ Juego Anulado",
			description="Uno de los jugadores no tiene suficientes puntos.",
			color=0xFF0000
		)
		await public_message.edit(embed=embed_error, view=None)
		return
	
	# ====== FASE 4: Determinar ganador ======
	winner, resultado_texto = ppt_master.determine_ppt_winner(player1_choice, player2_choice)
	
	emoji1 = ppt_master.get_ppt_emoji(player1_choice)
	emoji2 = ppt_master.get_ppt_emoji(player2_choice)
	
	# ====== FASE 5: Procesar resultado ======
	if winner == 0:  # Empate
		embed_resultado = discord.Embed(
			title="🤝 ¡Empate!",
			description=f"{first_player.mention} y {second_player.mention} han empatado su duelo\n\n{resultado_texto}",
			color=0xFEE75C
		)
		embed_resultado.add_field(
			name=f"🎯 {first_player.display_name}",
			value=f"{emoji1} **{player1_choice.capitalize()}**",
			inline=True
		)
		embed_resultado.add_field(
			name=f"🎯 {second_player.display_name}",
			value=f"{emoji2} **{player2_choice.capitalize()}**",
			inline=True
		)
		embed_resultado.add_field(
			name="💰 Resultado",
			value=f"Cada uno conserva sus **{bet_amount:,.2f}{currency_symbol}**",
			inline=False
		)
		
	elif winner == 1:  # Gana player1 (primer jugador)
		# Restar puntos al perdedor
		_apply_balance_delta(
			user_id=player2.user_id,
			delta=-bet_amount,
			reason="ppt_loss",
			interaction=interaction
		)
		
		# Sumar puntos al ganador
		p1_new_balance = _apply_balance_delta(
			user_id=player1.user_id,
			delta=bet_amount,
			reason="ppt_win",
			interaction=interaction
		)
		
		embed_resultado = discord.Embed(
			title="🏆 ¡Victoria!",
			description=f"{first_player.mention} ha ganado el duelo contra {second_player.mention}\n\n{resultado_texto}",
			color=0x57F287
		)
		embed_resultado.add_field(
			name=f"👑 {first_player.display_name} (Ganador)",
			value=f"{emoji1} **{player1_choice.capitalize()}**",
			inline=True
		)
		embed_resultado.add_field(
			name=f"💔 {second_player.display_name}",
			value=f"{emoji2} **{player2_choice.capitalize()}**",
			inline=True
		)
		embed_resultado.add_field(
			name="💰 Recompensa",
			value=f"{first_player.mention} gana **+{bet_amount:,.2f}{currency_symbol}**\n{second_player.mention} pierde **-{bet_amount:,.2f}{currency_symbol}**",
			inline=False
		)
		
	else:  # Gana player2 (segundo jugador)
		# Restar puntos al perdedor
		_apply_balance_delta(
			user_id=player1.user_id,
			delta=-bet_amount,
			reason="ppt_loss",
			interaction=interaction
		)
		
		# Sumar puntos al ganador
		p2_new_balance = _apply_balance_delta(
			user_id=player2.user_id,
			delta=bet_amount,
			reason="ppt_win",
			interaction=interaction
		)
		
		embed_resultado = discord.Embed(
			title="🏆 ¡Victoria!",
			description=f"{second_player.mention} ha ganado el duelo contra {first_player.mention}\n\n{resultado_texto}",
			color=0x57F287
		)
		embed_resultado.add_field(
			name=f"👑 {second_player.display_name} (Ganador)",
			value=f"{emoji2} **{player2_choice.capitalize()}**",
			inline=True
		)
		embed_resultado.add_field(
			name=f"💔 {first_player.display_name}",
			value=f"{emoji1} **{player1_choice.capitalize()}**",
			inline=True
		)
		embed_resultado.add_field(
			name="💰 Recompensa",
			value=f"{second_player.mention} gana **+{bet_amount:,.2f}{currency_symbol}**\n{first_player.mention} pierde **-{bet_amount:,.2f}{currency_symbol}**",
			inline=False
		)
	
	embed_resultado.set_footer(text="🎮 Piedra, Papel o Tijeras")
	
	# ====== FASE 6: Ofrecer revancha ======
	# Verificar que ambos jugadores tengan puntos para la revancha
	player1_points_after = _get_current_balance(player1.user_id)
	player2_points_after = _get_current_balance(player2.user_id)
	
	if player1_points_after >= bet_amount and player2_points_after >= bet_amount:
		# Ambos tienen puntos, ofrecer revancha
		rematch_view = PPTRematchView(player1_id=first_player.id, player2_id=second_player.id, timeout=60)
		embed_resultado.add_field(
			name="🔄 Revancha",
			value="¿Quieren jugar de nuevo? Quien presione el botón elige primero",
			inline=False
		)
		await public_message.edit(embed=embed_resultado, view=rematch_view)
		
		# Esperar si aceptan la revancha
		await rematch_view.wait()
		
		if rematch_view.rematch_accepted and not rematch_view.timed_out:
			# Determinar el rival basado en quien inició la revancha
			if rematch_view.rematch_initiator_id == first_player.id:
				new_rival = second_player
			else:
				new_rival = first_player
			
			# Usar la interacción del botón de revancha para que el mensaje vaya al iniciador
			await play_ppt_game(
				rematch_view.rematch_interaction,
				new_rival,
				bet_amount,
				is_rematch=True,
				rematch_initiator_id=rematch_view.rematch_initiator_id
			)
		else:
			# Eliminar botón de revancha si expiró o no se aceptó
			await public_message.edit(embed=embed_resultado, view=None)
	else:
		# No tienen puntos suficientes, solo mostrar resultado
		await public_message.edit(embed=embed_resultado, view=None)


def setup_ppt_commands(bot: commands.Bot) -> None:
	"""Registra comandos de Piedra Papel Tijeras"""

	@bot.tree.command(name="ppt", description="Piedra Papel Tijeras - Juega y apuesta")
	@app_commands.describe(
		rival="Usuario rival a desafiar",
		cantidad="Cantidad a apostar"
	)
	async def ppt(interaction: discord.Interaction, rival: discord.User, cantidad: str):
		"""Juega Piedra Papel Tijeras contra otro usuario y apuesta puntos."""
		# Evitar jugar contra sí mismo
		if rival.id == interaction.user.id:
			await interaction.response.send_message("❌ No puedes jugar contra ti mismo.", ephemeral=True)
			return
		
		# Evitar jugar contra bots
		if rival.bot:
			await interaction.response.send_message("❌ No puedes jugar contra bots.", ephemeral=True)
			return
		
		# Parsear cantidad
		try:
			bet_amount = round(float(cantidad), 2)
		except ValueError:
			await interaction.response.send_message("❌ La cantidad debe ser un número.", ephemeral=True)
			return
		
		if bet_amount <= 0:
			await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)
			return
		
		# Llamar a la función del juego
		await play_ppt_game(interaction, rival, bet_amount, is_rematch=False)

	@bot.tree.command(name="piedra_papel_tijeras", description="Piedra Papel Tijeras - Juega y apuesta")
	@app_commands.describe(
		rival="Usuario rival a desafiar",
		cantidad="Cantidad a apostar"
	)
	async def ppt_full(interaction: discord.Interaction, rival: discord.User, cantidad: str):
		"""Alias del comando /ppt"""
		# Evitar jugar contra sí mismo
		if rival.id == interaction.user.id:
			await interaction.response.send_message("❌ No puedes jugar contra ti mismo.", ephemeral=True)
			return
		
		# Evitar jugar contra bots
		if rival.bot:
			await interaction.response.send_message("❌ No puedes jugar contra bots.", ephemeral=True)
			return
		
		# Parsear cantidad
		try:
			bet_amount = round(float(cantidad), 2)
		except ValueError:
			await interaction.response.send_message("❌ La cantidad debe ser un número.", ephemeral=True)
			return
		
		if bet_amount <= 0:
			await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)
			return
		
		# Llamar a la función del juego
		await play_ppt_game(interaction, rival, bet_amount, is_rematch=False)
