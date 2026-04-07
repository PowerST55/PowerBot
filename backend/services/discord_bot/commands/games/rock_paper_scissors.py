"""
Comandos de Piedra Papel Tijeras para PowerBot Discord.
"""
from __future__ import annotations

from datetime import timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from backend.managers import get_or_create_discord_user
from backend.managers import economy_manager
from backend.managers.user_lookup_manager import find_user_by_discord_id
from backend.services.activities import ppt_master
from backend.services.discord_bot.config.economy import get_economy_config


DEFAULT_CURRENCY_NAME = "pews"
DEFAULT_CURRENCY_SYMBOL = "💎"


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


class PPTOpenChallengeView(discord.ui.View):
	"""View para duelos abiertos de PPT."""

	def __init__(
		self,
		challenger_id: int,
		bet_amount: float,
		currency_symbol: str,
		timeout: int = 1200,
	):
		super().__init__(timeout=timeout)
		self.challenger_id = challenger_id
		self.bet_amount = bet_amount
		self.currency_symbol = currency_symbol
		self.opponent: Optional[discord.User] = None
		self.accept_interaction: Optional[discord.Interaction] = None
		self.timed_out = False

	async def on_timeout(self):
		self.timed_out = True
		for item in self.children:
			item.disabled = True

	@discord.ui.button(label="Aceptar duelo", emoji="⚔️", style=discord.ButtonStyle.primary)
	async def accept_duel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.user.id == self.challenger_id:
			await interaction.response.send_message("❌ No puedes aceptar tu propio duelo.", ephemeral=True)
			return
		if interaction.user.bot:
			await interaction.response.send_message("❌ Los bots no pueden participar.", ephemeral=True)
			return

		challenger_member = interaction.guild.get_member(self.challenger_id) if interaction.guild else None
		challenger_name = challenger_member.name if challenger_member else f"user_{self.challenger_id}"
		challenger_avatar = str(challenger_member.display_avatar.url) if challenger_member else ""
		challenger_data, _, _ = get_or_create_discord_user(
			discord_id=str(self.challenger_id),
			discord_username=challenger_name,
			avatar_url=challenger_avatar,
		)
		opponent_data, _, _ = get_or_create_discord_user(
			discord_id=str(interaction.user.id),
			discord_username=interaction.user.name,
			avatar_url=str(interaction.user.display_avatar.url),
		)

		challenger_points = _get_current_balance(challenger_data.user_id)
		opponent_points = _get_current_balance(opponent_data.user_id)

		if challenger_points < self.bet_amount:
			await interaction.response.send_message(
				"❌ El creador del duelo no tiene puntos suficientes ahora mismo. Intenta de nuevo en un momento.",
				ephemeral=True,
			)
			return

		if opponent_points < self.bet_amount:
			await interaction.response.send_message(
				f"❌ No tienes puntos suficientes. Necesitas **{self.bet_amount:,.2f}{self.currency_symbol}** para aceptar.",
				ephemeral=True,
			)
			return

		if self.opponent is not None:
			await interaction.response.send_message("❌ Este duelo ya fue tomado.", ephemeral=True)
			return

		self.opponent = interaction.user
		self.accept_interaction = interaction
		button.disabled = True
		await interaction.response.send_message("✅ Duelo aceptado. Revisa tu mensaje privado para elegir.", ephemeral=True)
		self.stop()


class PPTDMChallengeView(discord.ui.View):
	"""Invitación privada para aceptar o rechazar un duelo por MD."""

	def __init__(self, challenger_id: int, rival_id: int, timeout: int = 300):
		super().__init__(timeout=timeout)
		self.challenger_id = challenger_id
		self.rival_id = rival_id
		self.accepted = False
		self.declined = False
		self.action_interaction: Optional[discord.Interaction] = None
		self.timed_out = False

	async def on_timeout(self):
		self.timed_out = True
		for item in self.children:
			item.disabled = True

	@discord.ui.button(label="Aceptar", emoji="✅", style=discord.ButtonStyle.success)
	async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.user.id != self.rival_id:
			await interaction.response.send_message("❌ Este reto no es para ti.", ephemeral=True)
			return

		self.accepted = True
		self.action_interaction = interaction
		await interaction.response.defer()
		self.stop()

	@discord.ui.button(label="Rechazar", emoji="❌", style=discord.ButtonStyle.secondary)
	async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.user.id != self.rival_id:
			await interaction.response.send_message("❌ Este reto no es para ti.", ephemeral=True)
			return

		self.declined = True
		self.action_interaction = interaction
		await interaction.response.defer()
		self.stop()


def _get_current_balance(user_id: int) -> float:
	"""Obtiene el balance actual de un usuario"""
	return float(economy_manager.get_total_balance(user_id))


def _transfer_ppt_bet(
	*,
	loser_user_id: int,
	winner_user_id: int,
	amount: float,
	interaction: discord.Interaction,
) -> dict:
	"""Liquida una apuesta PPT con una transferencia directa usuario a usuario."""
	return economy_manager.transfer_points(
		from_user_id=loser_user_id,
		to_user_id=winner_user_id,
		amount=amount,
		guild_id=str(interaction.guild.id) if interaction.guild else None,
		platform="discord",
	)


def _build_settlement_error_embed(error_message: str) -> discord.Embed:
	"""Genera un embed uniforme para fallos al liquidar la apuesta."""
	return discord.Embed(
		title="❌ Juego Anulado",
		description=(
			"No se pudo liquidar la apuesta entre los jugadores. "
			"No se movieron fondos del sistema y la partida quedó sin efecto.\n\n"
			f"Detalle: {error_message}"
		),
		color=0xFF0000,
	)


def _build_join_server_required_embed() -> discord.Embed:
	return discord.Embed(
		title="🔒 Debes unirte a un servidor",
		description=(
			"Para jugar Piedra, Papel o Tijeras por MD primero debes estar registrado en la base de datos del bot.\n\n"
			"Únete a un servidor donde esté PowerBot y usa cualquier comando allí para crear tu perfil antes de jugar por mensaje privado."
		),
		color=0xE67E22,
	)


def _resolve_currency_for_interaction(
	interaction: discord.Interaction,
	*,
	rival: Optional[discord.abc.User] = None,
) -> tuple[str, str]:
	if interaction.guild is not None:
		economy_config = get_economy_config(interaction.guild.id)
		return economy_config.get_currency_name(), economy_config.get_currency_symbol()

	participant_ids = [interaction.user.id]
	if rival is not None:
		participant_ids.append(rival.id)

	for guild in interaction.client.guilds:
		if all(guild.get_member(user_id) is not None for user_id in participant_ids):
			economy_config = get_economy_config(guild.id)
			return economy_config.get_currency_name(), economy_config.get_currency_symbol()

	return DEFAULT_CURRENCY_NAME, DEFAULT_CURRENCY_SYMBOL


def _get_registered_ppt_player(user: discord.abc.User):
	return find_user_by_discord_id(str(user.id))


def _build_dm_result_embed(
	*,
	first_player: discord.abc.User,
	second_player: discord.abc.User,
	first_choice: str,
	second_choice: str,
	bet_amount: float,
	currency_symbol: str,
	winner: int,
	resultado_texto: str,
	transfer_result: Optional[dict] = None,
) -> discord.Embed:
	emoji1 = ppt_master.get_ppt_emoji(first_choice)
	emoji2 = ppt_master.get_ppt_emoji(second_choice)

	if winner == 0:
		embed = discord.Embed(
			title="🤝 ¡Empate!",
			description=(
				f"{first_player.mention} y {second_player.mention} empataron.\n\n"
				f"{resultado_texto}"
			),
			color=0xFEE75C,
		)
		embed.add_field(name=f"🎯 {first_player.display_name}", value=f"{emoji1} **{first_choice.capitalize()}**", inline=True)
		embed.add_field(name=f"🎯 {second_player.display_name}", value=f"{emoji2} **{second_choice.capitalize()}**", inline=True)
		embed.add_field(
			name="💰 Resultado",
			value=f"Cada uno conserva sus **{bet_amount:,.2f}{currency_symbol}**",
			inline=False,
		)
		embed.set_footer(text="PPT • Mensaje privado")
		return embed

	if winner == 1:
		winner_player = first_player
		loser_player = second_player
	else:
		winner_player = second_player
		loser_player = first_player

	embed = discord.Embed(
		title="🏆 ¡Victoria!",
		description=(
			f"{winner_player.mention} ganó el duelo contra {loser_player.mention}.\n\n"
			f"{resultado_texto}"
		),
		color=0x57F287,
	)
	embed.add_field(name=f"🎯 {first_player.display_name}", value=f"{emoji1} **{first_choice.capitalize()}**", inline=True)
	embed.add_field(name=f"🎯 {second_player.display_name}", value=f"{emoji2} **{second_choice.capitalize()}**", inline=True)
	embed.add_field(
		name="💰 Recompensa",
		value=(
			f"{winner_player.mention} gana **+{bet_amount:,.2f}{currency_symbol}**\n"
			f"{loser_player.mention} pierde **-{bet_amount:,.2f}{currency_symbol}**"
		),
		inline=False,
	)
	if transfer_result:
		winner_balance = float(transfer_result.get("to_balance", 0.0))
		loser_balance = float(transfer_result.get("from_balance", 0.0))
		if winner == 1:
			balance_text = (
				f"{first_player.mention}: **{winner_balance:,.2f}{currency_symbol}**\n"
				f"{second_player.mention}: **{loser_balance:,.2f}{currency_symbol}**"
			)
		else:
			balance_text = (
				f"{second_player.mention}: **{winner_balance:,.2f}{currency_symbol}**\n"
				f"{first_player.mention}: **{loser_balance:,.2f}{currency_symbol}**"
			)
		embed.add_field(name="📊 Balances", value=balance_text, inline=False)

	embed.set_footer(text="PPT • Mensaje privado")
	return embed


async def _play_ppt_game_dm(
	interaction: discord.Interaction,
	rival: discord.User,
	bet_amount: float,
) -> None:
	player1_lookup = _get_registered_ppt_player(interaction.user)
	if not player1_lookup:
		await interaction.response.send_message(embed=_build_join_server_required_embed(), ephemeral=True)
		return

	player2_lookup = _get_registered_ppt_player(rival)
	if not player2_lookup:
		embed = _build_join_server_required_embed()
		embed.title = "🔒 Rival no registrado"
		embed.description = (
			f"{rival.mention} aún no tiene perfil en la base de datos del bot.\n\n"
			"Debe unirse a un servidor donde esté PowerBot y usar el bot allí antes de poder jugar por MD."
		)
		await interaction.response.send_message(embed=embed, ephemeral=True)
		return

	_, currency_symbol = _resolve_currency_for_interaction(interaction, rival=rival)
	player1_points = _get_current_balance(player1_lookup.user_id)
	player2_points = _get_current_balance(player2_lookup.user_id)

	is_valid, error_message = ppt_master.validate_ppt_game(player1_points, player2_points, bet_amount)
	if not is_valid:
		await interaction.response.send_message(error_message, ephemeral=True)
		return

	view_player1 = PPTView(allowed_user_id=interaction.user.id, timeout=180)
	player1_embed = discord.Embed(
		title="🎮 Piedra, Papel o Tijeras",
		description=(
			f"**Desafío por MD contra {rival.mention}**\n\n"
			f"💰 Apuesta: **{bet_amount:,.2f}{currency_symbol}**\n\n"
			"Tu elección es secreta."
		),
		color=0x5865F2,
	)
	player1_embed.set_footer(text="⏱️ Tienes 3 minutos para elegir")
	await interaction.response.send_message(embed=player1_embed, view=view_player1)

	await view_player1.wait()
	if view_player1.timed_out or view_player1.choice is None:
		await interaction.followup.send("⏱️ No elegiste a tiempo. El duelo por MD fue cancelado.", ephemeral=True)
		return

	player1_choice = view_player1.choice

	rival_dm = rival.dm_channel or await rival.create_dm()
	challenge_view = PPTDMChallengeView(challenger_id=interaction.user.id, rival_id=rival.id, timeout=300)
	challenge_embed = discord.Embed(
		title="⚔️ Desafío de PPT por MD",
		description=(
			f"{interaction.user.mention} te ha retado a una partida de Piedra, Papel o Tijeras por MD.\n\n"
			f"💰 Apuesta: **{bet_amount:,.2f}{currency_symbol}**\n"
			"Pulsa aceptar para jugar o rechazar para cancelar."
		),
		color=0x3498DB,
	)
	challenge_embed.set_footer(text="⏱️ El reto expira en 5 minutos")
	challenge_message = await rival_dm.send(embed=challenge_embed, view=challenge_view)

	await challenge_view.wait()
	if challenge_view.timed_out:
		for item in challenge_view.children:
			item.disabled = True
		await challenge_message.edit(view=challenge_view)
		await interaction.followup.send(f"⏱️ {rival.mention} no respondió a tiempo. El duelo fue cancelado.")
		return

	if challenge_view.declined:
		for item in challenge_view.children:
			item.disabled = True
		await challenge_message.edit(view=challenge_view)
		await interaction.followup.send(f"❌ {rival.mention} rechazó el duelo.")
		return

	for item in challenge_view.children:
		item.disabled = True
	await challenge_message.edit(view=challenge_view)

	accept_interaction = challenge_view.action_interaction
	player2_pick_view = PPTView(allowed_user_id=rival.id, timeout=180)
	player2_pick_embed = discord.Embed(
		title="🎮 Elige tu jugada",
		description=(
			f"Aceptaste el duelo de {interaction.user.mention}.\n\n"
			f"💰 Apuesta: **{bet_amount:,.2f}{currency_symbol}**\n"
			"Tu elección es secreta."
		),
		color=0xFEE75C,
	)
	player2_pick_embed.set_footer(text="⏱️ Tienes 3 minutos para elegir")
	if accept_interaction is not None:
		await accept_interaction.followup.send(embed=player2_pick_embed, view=player2_pick_view)
	else:
		await rival_dm.send(embed=player2_pick_embed, view=player2_pick_view)

	await interaction.followup.send(f"✅ {rival.mention} aceptó el duelo. Esperando su elección...")

	await player2_pick_view.wait()
	if player2_pick_view.timed_out or player2_pick_view.choice is None:
		await interaction.followup.send(f"⏱️ {rival.mention} no eligió a tiempo. El duelo fue cancelado.")
		await rival_dm.send("⏱️ No elegiste a tiempo. El duelo fue cancelado.")
		return

	player2_choice = player2_pick_view.choice

	player1_points_final = _get_current_balance(player1_lookup.user_id)
	player2_points_final = _get_current_balance(player2_lookup.user_id)
	if player1_points_final < bet_amount or player2_points_final < bet_amount:
		error_embed = discord.Embed(
			title="❌ Juego Anulado",
			description="Uno de los jugadores ya no tiene puntos suficientes para continuar.",
			color=0xFF0000,
		)
		await interaction.followup.send(embed=error_embed)
		await rival_dm.send(embed=error_embed)
		return

	winner, resultado_texto = ppt_master.determine_ppt_winner(player1_choice, player2_choice)
	transfer_result = None
	if winner == 1:
		transfer_result = _transfer_ppt_bet(
			loser_user_id=player2_lookup.user_id,
			winner_user_id=player1_lookup.user_id,
			amount=bet_amount,
			interaction=interaction,
		)
	elif winner == 2:
		transfer_result = _transfer_ppt_bet(
			loser_user_id=player1_lookup.user_id,
			winner_user_id=player2_lookup.user_id,
			amount=bet_amount,
			interaction=interaction,
		)

	if transfer_result is not None and not transfer_result.get("success"):
		error_embed = _build_settlement_error_embed(str(transfer_result.get("error", "No se pudo completar la transferencia.")))
		await interaction.followup.send(embed=error_embed)
		await rival_dm.send(embed=error_embed)
		return

	result_embed = _build_dm_result_embed(
		first_player=interaction.user,
		second_player=rival,
		first_choice=player1_choice,
		second_choice=player2_choice,
		bet_amount=bet_amount,
		currency_symbol=currency_symbol,
		winner=winner,
		resultado_texto=resultado_texto,
		transfer_result=transfer_result,
	)
	await interaction.followup.send(embed=result_embed)
	await rival_dm.send(embed=result_embed)


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
		transfer_result = _transfer_ppt_bet(
			loser_user_id=player2.user_id,
			winner_user_id=player1.user_id,
			amount=bet_amount,
			interaction=interaction,
		)
		if not transfer_result.get("success"):
			await public_message.edit(
				embed=_build_settlement_error_embed(str(transfer_result.get("error", "No se pudo completar la transferencia."))),
				view=None,
			)
			return
		
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
		embed_resultado.add_field(
			name="📊 Balances",
			value=(
				f"{first_player.mention}: **{float(transfer_result['to_balance']):,.2f}{currency_symbol}**\n"
				f"{second_player.mention}: **{float(transfer_result['from_balance']):,.2f}{currency_symbol}**"
			),
			inline=False
		)
		
	else:  # Gana player2 (segundo jugador)
		transfer_result = _transfer_ppt_bet(
			loser_user_id=player1.user_id,
			winner_user_id=player2.user_id,
			amount=bet_amount,
			interaction=interaction,
		)
		if not transfer_result.get("success"):
			await public_message.edit(
				embed=_build_settlement_error_embed(str(transfer_result.get("error", "No se pudo completar la transferencia."))),
				view=None,
			)
			return
		
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
		embed_resultado.add_field(
			name="📊 Balances",
			value=(
				f"{second_player.mention}: **{float(transfer_result['to_balance']):,.2f}{currency_symbol}**\n"
				f"{first_player.mention}: **{float(transfer_result['from_balance']):,.2f}{currency_symbol}**"
			),
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
	@app_commands.allowed_installs(guilds=True, users=True)
	@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
	@app_commands.describe(
		cantidad="Cantidad a apostar",
		rival="Usuario rival a desafiar (opcional)"
	)
	async def ppt(
		interaction: discord.Interaction,
		cantidad: str,
		rival: Optional[discord.User] = None,
	):
		"""Juega Piedra Papel Tijeras contra otro usuario y apuesta puntos."""
		await _handle_ppt_command(interaction, cantidad, rival)

	@bot.tree.command(name="piedra_papel_tijeras", description="Piedra Papel Tijeras - Juega y apuesta")
	@app_commands.allowed_installs(guilds=True, users=True)
	@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
	@app_commands.describe(
		cantidad="Cantidad a apostar",
		rival="Usuario rival a desafiar (opcional)"
	)
	async def ppt_full(
		interaction: discord.Interaction,
		cantidad: str,
		rival: Optional[discord.User] = None,
	):
		"""Alias del comando /ppt"""
		await _handle_ppt_command(interaction, cantidad, rival)


async def _handle_ppt_command(
	interaction: discord.Interaction,
	cantidad: str,
	rival: Optional[discord.User],
) -> None:
	"""Maneja /ppt en modo directo o duelo abierto."""
	# Parsear cantidad
	try:
		bet_amount = round(float(cantidad), 2)
	except ValueError:
		await interaction.response.send_message("❌ La cantidad debe ser un número.", ephemeral=True)
		return

	if bet_amount <= 0:
		await interaction.response.send_message("❌ La cantidad debe ser mayor a 0.", ephemeral=True)
		return

	if interaction.guild is None:
		if rival is None:
			await interaction.response.send_message(
				"❌ En mensajes privados debes indicar un rival para jugar. El duelo abierto solo funciona dentro de servidores.",
				ephemeral=True,
			)
			return
		if rival.id == interaction.user.id:
			await interaction.response.send_message("❌ No puedes jugar contra ti mismo.", ephemeral=True)
			return
		if rival.bot:
			await interaction.response.send_message("❌ No puedes jugar contra bots.", ephemeral=True)
			return

		await _play_ppt_game_dm(interaction, rival, bet_amount)
		return

	# Modo duelo directo contra rival especificado
	if rival is not None:
		if rival.id == interaction.user.id:
			await interaction.response.send_message("❌ No puedes jugar contra ti mismo.", ephemeral=True)
			return
		if rival.bot:
			await interaction.response.send_message("❌ No puedes jugar contra bots.", ephemeral=True)
			return

		await play_ppt_game(interaction, rival, bet_amount, is_rematch=False)
		return

	# Modo duelo abierto: cualquiera puede aceptar, limitado a 1 jugador, 20 minutos.
	economy_config = get_economy_config(interaction.guild.id)
	currency_symbol = economy_config.get_currency_symbol()

	challenger_data, _, _ = get_or_create_discord_user(
		discord_id=str(interaction.user.id),
		discord_username=interaction.user.name,
		avatar_url=str(interaction.user.display_avatar.url),
	)
	challenger_points = _get_current_balance(challenger_data.user_id)
	if challenger_points < bet_amount:
		await interaction.response.send_message(
			f"❌ No tienes puntos suficientes para crear este duelo. Necesitas **{bet_amount:,.2f}{currency_symbol}**.",
			ephemeral=True,
		)
		return

	# Fase 1: el creador elige en privado antes de abrir el duelo.
	creator_pick_view = PPTView(allowed_user_id=interaction.user.id, timeout=180)
	creator_pick_embed = discord.Embed(
		title="🎮 Elige tu jugada",
		description=(
			"Tu eleccion es secreta.\n"
			"Cuando alguien acepte el duelo abierto, se comparara de inmediato."
		),
		color=0x5865F2,
	)
	creator_pick_embed.add_field(
		name="💰 Apuesta",
		value=f"**{bet_amount:,.2f}{currency_symbol}**",
		inline=False,
	)
	creator_pick_embed.set_footer(text="⏱️ Tienes 3 minutos para elegir")

	await interaction.response.send_message(embed=creator_pick_embed, view=creator_pick_view, ephemeral=True)
	await creator_pick_view.wait()

	if creator_pick_view.timed_out or creator_pick_view.choice is None:
		await interaction.followup.send("⏱️ No elegiste a tiempo. No se creo el duelo abierto.", ephemeral=True)
		return

	challenger_choice = creator_pick_view.choice

	open_view = PPTOpenChallengeView(
		challenger_id=interaction.user.id,
		bet_amount=bet_amount,
		currency_symbol=currency_symbol,
		timeout=1200,
	)
	open_embed = discord.Embed(
		title="⚔️ Duelo Abierto de Piedra, Papel o Tijeras",
		description=(
			f"{interaction.user.mention} ha creado un duelo abierto.\n\n"
			f"💰 Apuesta: **{bet_amount:,.2f}{currency_symbol}**\n"
			"👥 Puede entrar el primero que acepte\n"
			"⏱️ Este duelo expira en **20 minutos**"
		),
		color=0x3498DB,
	)
	open_embed.set_footer(text="Pulsa 'Aceptar duelo' para entrar")

	public_message = await interaction.followup.send(embed=open_embed, view=open_view, wait=True)

	await open_view.wait()

	if open_view.timed_out or open_view.opponent is None:
		expired_embed = discord.Embed(
			title="⏱️ Duelo vencido",
			description="Nadie acepto el duelo en 20 minutos. El enfrentamiento quedo invalido.",
			color=0xFF6600,
		)
		await public_message.edit(embed=expired_embed, view=None)
		return

	# Revalidar fondos de ambos jugadores al momento de iniciar el duelo.
	opponent = open_view.opponent
	opponent_data, _, _ = get_or_create_discord_user(
		discord_id=str(opponent.id),
		discord_username=opponent.name,
		avatar_url=str(opponent.display_avatar.url),
	)
	opponent_points = _get_current_balance(opponent_data.user_id)
	challenger_points_final = _get_current_balance(challenger_data.user_id)

	is_valid, error_msg = ppt_master.validate_ppt_game(challenger_points_final, opponent_points, bet_amount)
	if not is_valid:
		await public_message.edit(
			embed=discord.Embed(title="❌ Duelo anulado", description=error_msg, color=0xFF0000),
			view=None,
		)
		return

	# Fase 2: el retador que acepta elige en privado.
	accept_interaction = open_view.accept_interaction
	opponent_pick_view = PPTView(allowed_user_id=opponent.id, timeout=180)
	opponent_pick_embed = discord.Embed(
		title="🎮 Elige tu jugada",
		description=(
			f"Aceptaste el duelo de {interaction.user.mention}.\n"
			"Tu eleccion es secreta y el resultado saldra al instante."
		),
		color=0xFEE75C,
	)
	opponent_pick_embed.add_field(
		name="💰 Apuesta",
		value=f"**{bet_amount:,.2f}{currency_symbol}**",
		inline=False,
	)
	opponent_pick_embed.set_footer(text="⏱️ Tienes 3 minutos para elegir")

	if accept_interaction is not None:
		await accept_interaction.followup.send(embed=opponent_pick_embed, view=opponent_pick_view, ephemeral=True)
	else:
		await interaction.followup.send(
			f"{opponent.mention}, revisa tus privados para elegir.",
			ephemeral=True,
		)

	await public_message.edit(
		embed=discord.Embed(
			title="✅ Duelo tomado",
			description=(
				f"{opponent.mention} acepto el duelo de {interaction.user.mention}.\n"
				"Esperando su eleccion privada..."
			),
			color=0x57F287,
		),
		view=None,
	)

	await opponent_pick_view.wait()
	if opponent_pick_view.timed_out or opponent_pick_view.choice is None:
		await public_message.edit(
			embed=discord.Embed(
				title="⏱️ Tiempo agotado",
				description=f"{opponent.mention} no eligio a tiempo. Duelo cancelado.",
				color=0xFF6600,
			),
			view=None,
		)
		return

	opponent_choice = opponent_pick_view.choice

	# Fase 3: resolver resultado inmediato
	winner, resultado_texto = ppt_master.determine_ppt_winner(challenger_choice, opponent_choice)
	emoji_challenger = ppt_master.get_ppt_emoji(challenger_choice)
	emoji_opponent = ppt_master.get_ppt_emoji(opponent_choice)

	if winner == 0:
		result_embed = discord.Embed(
			title="🤝 ¡Empate!",
			description=(
				f"{interaction.user.mention} y {opponent.mention} empataron.\n\n"
				f"{resultado_texto}"
			),
			color=0xFEE75C,
		)
		result_embed.add_field(
			name=f"🎯 {interaction.user.display_name}",
			value=f"{emoji_challenger} **{challenger_choice.capitalize()}**",
			inline=True,
		)
		result_embed.add_field(
			name=f"🎯 {opponent.display_name}",
			value=f"{emoji_opponent} **{opponent_choice.capitalize()}**",
			inline=True,
		)
		result_embed.add_field(
			name="💰 Resultado",
			value=f"Cada uno conserva sus **{bet_amount:,.2f}{currency_symbol}**",
			inline=False,
		)
	elif winner == 1:
		transfer_result = _transfer_ppt_bet(
			loser_user_id=opponent_data.user_id,
			winner_user_id=challenger_data.user_id,
			amount=bet_amount,
			interaction=interaction,
		)
		if not transfer_result.get("success"):
			await public_message.edit(
				embed=_build_settlement_error_embed(str(transfer_result.get("error", "No se pudo completar la transferencia."))),
				view=None,
			)
			return
		result_embed = discord.Embed(
			title="🏆 ¡Victoria!",
			description=(
				f"{interaction.user.mention} le gano a {opponent.mention}.\n\n"
				f"{resultado_texto}"
			),
			color=0x57F287,
		)
		result_embed.add_field(
			name=f"👑 {interaction.user.display_name} (Ganador)",
			value=f"{emoji_challenger} **{challenger_choice.capitalize()}**",
			inline=True,
		)
		result_embed.add_field(
			name=f"💔 {opponent.display_name}",
			value=f"{emoji_opponent} **{opponent_choice.capitalize()}**",
			inline=True,
		)
		result_embed.add_field(
			name="💰 Recompensa",
			value=f"{interaction.user.mention} gana **+{bet_amount:,.2f}{currency_symbol}**\n{opponent.mention} pierde **-{bet_amount:,.2f}{currency_symbol}**",
			inline=False,
		)
		result_embed.add_field(
			name="📊 Balances",
			value=(
				f"{interaction.user.mention}: **{float(transfer_result['to_balance']):,.2f}{currency_symbol}**\n"
				f"{opponent.mention}: **{float(transfer_result['from_balance']):,.2f}{currency_symbol}**"
			),
			inline=False,
		)
	else:
		transfer_result = _transfer_ppt_bet(
			loser_user_id=challenger_data.user_id,
			winner_user_id=opponent_data.user_id,
			amount=bet_amount,
			interaction=interaction,
		)
		if not transfer_result.get("success"):
			await public_message.edit(
				embed=_build_settlement_error_embed(str(transfer_result.get("error", "No se pudo completar la transferencia."))),
				view=None,
			)
			return
		result_embed = discord.Embed(
			title="🏆 ¡Victoria!",
			description=(
				f"{opponent.mention} le gano a {interaction.user.mention}.\n\n"
				f"{resultado_texto}"
			),
			color=0x57F287,
		)
		result_embed.add_field(
			name=f"👑 {opponent.display_name} (Ganador)",
			value=f"{emoji_opponent} **{opponent_choice.capitalize()}**",
			inline=True,
		)
		result_embed.add_field(
			name=f"💔 {interaction.user.display_name}",
			value=f"{emoji_challenger} **{challenger_choice.capitalize()}**",
			inline=True,
		)
		result_embed.add_field(
			name="💰 Recompensa",
			value=f"{opponent.mention} gana **+{bet_amount:,.2f}{currency_symbol}**\n{interaction.user.mention} pierde **-{bet_amount:,.2f}{currency_symbol}**",
			inline=False,
		)
		result_embed.add_field(
			name="📊 Balances",
			value=(
				f"{opponent.mention}: **{float(transfer_result['to_balance']):,.2f}{currency_symbol}**\n"
				f"{interaction.user.mention}: **{float(transfer_result['from_balance']):,.2f}{currency_symbol}**"
			),
			inline=False,
		)

	result_embed.set_footer(text="🎮 Piedra, Papel o Tijeras")

	# Fase 4: ofrecer revancha tambien en duelo abierto.
	challenger_points_after = _get_current_balance(challenger_data.user_id)
	opponent_points_after = _get_current_balance(opponent_data.user_id)
	if challenger_points_after >= bet_amount and opponent_points_after >= bet_amount:
		rematch_view = PPTRematchView(player1_id=interaction.user.id, player2_id=opponent.id, timeout=60)
		result_embed.add_field(
			name="🔄 Revancha",
			value="¿Quieren jugar de nuevo? Quien presione el botón elige primero",
			inline=False,
		)
		result_message = await interaction.followup.send(embed=result_embed, view=rematch_view, wait=True)

		await rematch_view.wait()
		if rematch_view.rematch_accepted and not rematch_view.timed_out:
			if rematch_view.rematch_initiator_id == interaction.user.id:
				new_rival = opponent
			else:
				new_rival = interaction.user

			await play_ppt_game(
				rematch_view.rematch_interaction,
				new_rival,
				bet_amount,
				is_rematch=True,
				rematch_initiator_id=rematch_view.rematch_initiator_id,
			)
		else:
			await result_message.edit(embed=result_embed, view=None)
	else:
		await interaction.followup.send(embed=result_embed)
