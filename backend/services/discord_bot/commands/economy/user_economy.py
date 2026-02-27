"""
Comandos de economía para usuarios normales.
Sistema de consulta de puntos y transacciones.
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from datetime import datetime

from backend.managers.user_lookup_manager import find_user_by_discord_id, find_user_by_global_id
from backend.managers.economy_manager import get_user_balance_by_id, transfer_points
from backend.managers import get_or_create_discord_user
from backend.services.discord_bot.config.economy import get_economy_config


class DonationConfirmView(discord.ui.View):
	"""Confirmación efímera previa a donar."""

	def __init__(self, target_discord_user: discord.User, amount: float, currency_symbol: str):
		super().__init__(timeout=60)
		self.target_discord_user = target_discord_user
		self.amount = round(float(amount), 2)
		self.currency_symbol = currency_symbol

	@discord.ui.button(label="✅ Confirmar donación", style=discord.ButtonStyle.green)
	async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.guild is None:
			await interaction.response.send_message("Este botón solo funciona en servidor.", ephemeral=True)
			return

		if interaction.user.id == self.target_discord_user.id:
			await interaction.response.send_message("No puedes donarte a ti mismo.", ephemeral=True)
			return

		sender_lookup = find_user_by_discord_id(str(interaction.user.id))
		if not sender_lookup:
			try:
				get_or_create_discord_user(
					discord_id=str(interaction.user.id),
					discord_username=interaction.user.name,
					avatar_url=str(interaction.user.display_avatar.url)
				)
			except Exception:
				pass
			sender_lookup = find_user_by_discord_id(str(interaction.user.id))

		if not sender_lookup:
			await interaction.response.send_message("❌ No se pudo crear tu cuenta para donar.", ephemeral=True)
			return

		recipient_lookup = find_user_by_discord_id(str(self.target_discord_user.id))
		if not recipient_lookup:
			try:
				get_or_create_discord_user(
					discord_id=str(self.target_discord_user.id),
					discord_username=self.target_discord_user.name,
					avatar_url=str(self.target_discord_user.display_avatar.url)
				)
			except Exception:
				pass
			recipient_lookup = find_user_by_discord_id(str(self.target_discord_user.id))

		if not recipient_lookup:
			await interaction.response.send_message("❌ No se pudo registrar al destinatario.", ephemeral=True)
			return

		result = transfer_points(
			from_user_id=sender_lookup.user_id,
			to_user_id=recipient_lookup.user_id,
			amount=self.amount,
			guild_id=str(interaction.guild.id),
			platform="discord",
		)

		if not result.get("success"):
			embed = discord.Embed(
				title="❌ Donación fallida",
				description=str(result.get("error", "No se pudo completar la donación.")),
				color=discord.Color.red()
			)
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		embed = discord.Embed(
			title="✅ Donación realizada",
			description=(
				f"Has donado **{self.amount:,.2f} {self.currency_symbol}** a {self.target_discord_user.mention}\n"
				f"💸 Tu nuevo balance: **{float(result['from_balance']):,.2f} {self.currency_symbol}**"
			),
			color=discord.Color.green()
		)
		embed.set_footer(text=f"Donación • {datetime.now().strftime('%d/%m/%Y %H:%M')}")
		await interaction.response.send_message(embed=embed, ephemeral=True)

		try:
			notify_embed = discord.Embed(
				title="🎁 Has recibido una donación",
				description=(
					f"{interaction.user.mention} te donó **{self.amount:,.2f} {self.currency_symbol}**\n"
					f"💰 Tu nuevo balance: **{float(result['to_balance']):,.2f} {self.currency_symbol}**"
				),
				color=discord.Color.gold()
			)
			notify_embed.set_footer(text=f"Donación • {datetime.now().strftime('%d/%m/%Y %H:%M')}")
			await self.target_discord_user.send(embed=notify_embed)
		except Exception:
			pass

	@discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
	async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		await interaction.response.send_message("Donación cancelada.", ephemeral=True)


class DonationView(discord.ui.View):
	"""Botón público para que otros usuarios donen el monto fijo."""

	def __init__(self, target_discord_user: discord.User, amount: float, currency_symbol: str):
		super().__init__(timeout=None)
		self.target_discord_user = target_discord_user
		self.amount = round(float(amount), 2)
		self.currency_symbol = currency_symbol

	@discord.ui.button(label="💸 Donar", style=discord.ButtonStyle.success)
	async def donate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		confirm_view = DonationConfirmView(
			target_discord_user=self.target_discord_user,
			amount=self.amount,
			currency_symbol=self.currency_symbol,
		)
		embed = discord.Embed(
			title="Confirmar donación",
			description=f"¿Seguro que quieres donar **{self.amount:,.2f} {self.currency_symbol}** a {self.target_discord_user.mention}?",
			color=discord.Color.blurple(),
		)
		await interaction.response.send_message(embed=embed, ephemeral=True, view=confirm_view)


async def send_donation_embed(interaction: discord.Interaction, amount: float) -> discord.Embed:
	"""Publica un embed con botón para donaciones públicas de monto fijo."""
	if interaction.guild is None:
		return discord.Embed(
			title="❌ Comando no disponible",
			description="Este comando solo funciona en servidores.",
			color=discord.Color.red(),
		)

	amount = round(float(amount), 2)
	if amount <= 0:
		return discord.Embed(
			title="❌ Cantidad inválida",
			description="El monto debe ser mayor a cero.",
			color=discord.Color.red(),
		)

	economy_config = get_economy_config(interaction.guild.id)
	currency_symbol = economy_config.get_currency_symbol()

	creator_lookup = find_user_by_discord_id(str(interaction.user.id))
	if not creator_lookup:
		try:
			get_or_create_discord_user(
				discord_id=str(interaction.user.id),
				discord_username=interaction.user.name,
				avatar_url=str(interaction.user.display_avatar.url)
			)
		except Exception:
			pass
		creator_lookup = find_user_by_discord_id(str(interaction.user.id))

	if not creator_lookup:
		return discord.Embed(
			title="❌ Error",
			description="No se pudo registrar tu cuenta para crear la donación.",
			color=discord.Color.red(),
		)

	embed = discord.Embed(
		title="🎁 Donación abierta",
		description=(
			f"**Destino:** `ID:{creator_lookup.user_id}` {interaction.user.mention}\n"
			f"**Monto por click:** **{amount:,.2f} {currency_symbol}**\n\n"
			"Pulsa el botón para donar ese monto."
		),
		color=discord.Color.gold(),
	)
	embed.set_thumbnail(url=interaction.user.display_avatar.url)
	embed.set_footer(text=f"Creado • {datetime.now().strftime('%d/%m/%Y %H:%M')}")

	view = DonationView(
		target_discord_user=interaction.user,
		amount=amount,
		currency_symbol=currency_symbol,
	)
	await interaction.followup.send(embed=embed, view=view, ephemeral=False)

	return discord.Embed(
		title="✅ Publicado",
		description="Tu panel de donación se publicó en este canal.",
		color=discord.Color.green(),
	)


def setup_economy_commands(bot: commands.Bot):
	"""Registra comandos de economía para usuarios"""
	
	@bot.tree.command(name="pews", description="Consulta tus puntos o los de otro usuario")
	@app_commands.describe(
		target="Usuario de Discord a consultar (opcional)",
		user_id="ID Universal del usuario a consultar (opcional)"
	)
	async def pews(
		interaction: discord.Interaction,
		target: Optional[discord.User] = None,
		user_id: Optional[int] = None
	):
		"""
		Comando /pews con 3 modos de uso:
		
		1. /pews                    → Ver tus propios puntos
		2. /pews @usuario           → Ver puntos de otro usuario de Discord
		3. /pews user_id:2          → Ver puntos por ID universal
		"""
		await interaction.response.defer()
		
		# Obtener configuración de moneda del servidor
		economy_config = get_economy_config(interaction.guild.id)
		currency_name = economy_config.get_currency_name()
		currency_symbol = economy_config.get_currency_symbol()
		
		# CASO 1: Sin argumentos - consultar propios puntos
		if target is None and user_id is None:
			result = await _show_own_balance(
				bot,
				interaction,
				currency_name,
				currency_symbol
			)
			# Si es un error, enviar como ephemeral
			if result.title and "❌" in result.title:
				await interaction.followup.send(embed=result, ephemeral=True)
			else:
				await interaction.followup.send(embed=result)
			return
		
		# CASO 2: Con @usuario - consultar puntos de otro usuario Discord
		if target is not None:
			result = await _show_discord_user_balance(
				bot,
				interaction,
				target,
				currency_name,
				currency_symbol
			)
			# Si es un error, enviar como ephemeral
			if result.title and "❌" in result.title:
				await interaction.followup.send(embed=result, ephemeral=True)
			else:
				await interaction.followup.send(embed=result)
			return
		
		# CASO 3: Con ID universal - consultar por ID global
		if user_id is not None:
			result = await _show_global_id_balance(
				bot,
				interaction,
				user_id,
				currency_name,
				currency_symbol
			)
			# Si es un error, enviar como ephemeral
			if result.title and "❌" in result.title:
				await interaction.followup.send(embed=result, ephemeral=True)
			else:
				await interaction.followup.send(embed=result)
			return
	
	
	@bot.tree.command(name="dar", description="Transfiere puntos a otro usuario")
	@app_commands.describe(
		cantidad="Cantidad de puntos a transferir",
		target="Usuario de Discord a quien transferir (opcional)",
		user_id="ID Universal del usuario a quien transferir (opcional)"
	)
	async def dar(
		interaction: discord.Interaction,
		cantidad: float,
		target: Optional[discord.User] = None,
		user_id: Optional[int] = None
	):
		"""
		Comando /dar para transferir puntos a otro usuario.
		
		Uso:
		1. /dar cantidad:100 @usuario     → Transferir a usuario de Discord
		2. /dar cantidad:100 user_id:2    → Transferir por ID universal
		"""
		await interaction.response.defer(ephemeral=True)
		
		# Obtener configuración de moneda del servidor
		economy_config = get_economy_config(interaction.guild.id)
		currency_name = economy_config.get_currency_name()
		currency_symbol = economy_config.get_currency_symbol()
		
		# Validar cantidad positiva
		cantidad = round(float(cantidad), 2)
		if cantidad <= 0:
			embed = discord.Embed(
				title="❌ Cantidad inválida",
				description="La cantidad debe ser mayor a cero.",
				color=discord.Color.red()
			)
			await interaction.followup.send(embed=embed, ephemeral=True)
			return
		
		# Validar que se especificó un destinatario
		if target is None and user_id is None:
			embed = discord.Embed(
				title="❌ Destinatario no especificado",
				description="Debes especificar un usuario de Discord (@usuario) o un ID universal (user_id:123).",
				color=discord.Color.red()
			)
			await interaction.followup.send(embed=embed, ephemeral=True)
			return
		
		# Validar que no se especificaron ambos
		if target is not None and user_id is not None:
			embed = discord.Embed(
				title="❌ Parámetros contradictorios",
				description="Solo puedes especificar **@usuario** o **user_id**, no ambos.",
				color=discord.Color.red()
			)
			await interaction.followup.send(embed=embed, ephemeral=True)
			return
		
		# Obtener ID del remitente
		sender_lookup = find_user_by_discord_id(str(interaction.user.id))
		if not sender_lookup:
			# Auto-registrar
			try:
				user, discord_profile, is_new = get_or_create_discord_user(
					discord_id=str(interaction.user.id),
					discord_username=interaction.user.name,
					avatar_url=str(interaction.user.display_avatar.url)
				)
				sender_lookup = find_user_by_discord_id(str(interaction.user.id))
				if not sender_lookup:
					embed = discord.Embed(
						title="❌ Error",
						description="No se pudo crear tu cuenta. Intenta nuevamente.",
						color=discord.Color.red()
					)
					await interaction.followup.send(embed=embed, ephemeral=True)
					return
			except Exception as e:
				embed = discord.Embed(
					title="❌ Error",
					description=f"Error al registrarte: {str(e)}",
					color=discord.Color.red()
				)
				await interaction.followup.send(embed=embed, ephemeral=True)
				return
		
		from_user_id = sender_lookup.user_id
		
		# CASO 1: Transferir a usuario de Discord
		if target is not None:
			# Validar que no se transfiera a sí mismo
			if target.id == interaction.user.id:
				embed = discord.Embed(
					title="❌ Operación inválida",
					description="No puedes transferir puntos a ti mismo.",
					color=discord.Color.red()
				)
				await interaction.followup.send(embed=embed, ephemeral=True)
				return
			
			# Validar que no sea un bot
			if target.bot:
				embed = discord.Embed(
					title="❌ Operación inválida",
					description="No puedes transferir puntos a un bot.",
					color=discord.Color.red()
				)
				await interaction.followup.send(embed=embed, ephemeral=True)
				return
			
			# Obtener o crear destinatario
			recipient_lookup = find_user_by_discord_id(str(target.id))
			if not recipient_lookup:
				try:
					user, discord_profile, is_new = get_or_create_discord_user(
						discord_id=str(target.id),
						discord_username=target.name,
						avatar_url=str(target.display_avatar.url)
					)
					recipient_lookup = find_user_by_discord_id(str(target.id))
					if not recipient_lookup:
						embed = discord.Embed(
							title="❌ Error",
							description=f"No se pudo crear la cuenta de {target.mention}.",
							color=discord.Color.red()
						)
						await interaction.followup.send(embed=embed, ephemeral=True)
						return
				except Exception as e:
					embed = discord.Embed(
						title="❌ Error",
						description=f"Error al registrar a {target.mention}: {str(e)}",
						color=discord.Color.red()
					)
					await interaction.followup.send(embed=embed, ephemeral=True)
					return
			
			to_user_id = recipient_lookup.user_id
			recipient_display_name = target.display_name
			recipient_mention = target.mention
		
		# CASO 2: Transferir por ID universal
		elif user_id is not None:
			# Validar que no se transfiera a sí mismo
			if user_id == from_user_id:
				embed = discord.Embed(
					title="❌ Operación inválida",
					description="No puedes transferir puntos a ti mismo.",
					color=discord.Color.red()
				)
				await interaction.followup.send(embed=embed, ephemeral=True)
				return
			
			# Verificar que el destinatario existe
			recipient_lookup = find_user_by_global_id(user_id)
			if not recipient_lookup:
				embed = discord.Embed(
					title="❌ Usuario no encontrado",
					description=f"No existe ningún usuario con ID universal `{user_id}`.",
					color=discord.Color.red()
				)
				await interaction.followup.send(embed=embed, ephemeral=True)
				return
			
			to_user_id = recipient_lookup.user_id
			recipient_display_name = recipient_lookup.display_name
			recipient_mention = f"ID: {user_id}"
		
		# Realizar transferencia
		result = transfer_points(
			from_user_id=from_user_id,
			to_user_id=to_user_id,
			amount=cantidad,
			guild_id=str(interaction.guild.id) if interaction.guild else None,
			platform="discord"
		)
		
		if not result["success"]:
			embed = discord.Embed(
				title="❌ Transferencia fallida",
				description=result["error"],
				color=discord.Color.red()
			)
			await interaction.followup.send(embed=embed, ephemeral=True)
			return
		
		# Transferencia exitosa
		embed = discord.Embed(
			title="✅ Transferencia exitosa",
			description=(
				f"Has transferido **{cantidad:,.2f} {currency_symbol}** a **{recipient_display_name}**\n\n"
				f"💸 Tu nuevo balance: **{float(result['from_balance']):,.2f} {currency_symbol}**"
			),
			color=discord.Color.green()
		)
		
		now = datetime.now().strftime("%d/%m/%Y %H:%M")
		embed.set_footer(text=f"Transferencia • {now}")
		
		await interaction.followup.send(embed=embed, ephemeral=True)
		
		# Notificar al destinatario si es usuario de Discord (solo si se usó @mención)
		if target is not None:
			try:
				recipient_embed = discord.Embed(
					title="💰 Has recibido puntos",
					description=(
						f"**{interaction.user.display_name}** te ha transferido **{cantidad:,.2f} {currency_symbol}**\n\n"
						f"💵 Tu nuevo balance: **{float(result['to_balance']):,.2f} {currency_symbol}**"
					),
					color=discord.Color.gold()
				)
				recipient_embed.set_footer(text=f"Transferencia • {now}")
				
				# Intentar enviar DM al destinatario
				try:
					await target.send(embed=recipient_embed)
				except discord.Forbidden:
					# Si no se puede enviar DM, mencionar en el canal
					await interaction.channel.send(
						content=f"{target.mention}",
						embed=recipient_embed
					)
			except Exception:
				pass  # Si falla la notificación, no es crítico


async def _show_own_balance(
	bot: commands.Bot,
	interaction: discord.Interaction,
	currency_name: str,
	currency_symbol: str
) -> discord.Embed:
	"""Muestra el balance propio del usuario"""
	# Buscar usuario
	user_lookup = find_user_by_discord_id(str(interaction.user.id))
	
	# Si no existe, registrarlo automáticamente
	if not user_lookup:
		try:
			user, discord_profile, is_new = get_or_create_discord_user(
				discord_id=str(interaction.user.id),
				discord_username=interaction.user.name,
				avatar_url=str(interaction.user.display_avatar.url)
			)
			# Buscar de nuevo después de crear
			user_lookup = find_user_by_discord_id(str(interaction.user.id))
			if not user_lookup:
				return discord.Embed(
					title="❌ Error",
					description="No se pudo crear tu cuenta. Intenta nuevamente.",
					color=discord.Color.red()
				)
		except Exception as e:
			return discord.Embed(
				title="❌ Error",
				description=f"Error al registrarte: {str(e)}",
				color=discord.Color.red()
			)
	
	# Obtener balance
	balance = get_user_balance_by_id(user_lookup.user_id)
	
	if not balance or not balance["user_exists"]:
		return discord.Embed(
			title="❌ Error",
			description="No se pudo obtener tu balance.",
			color=discord.Color.red()
		)
	
	# Crear embed con balance
	embed = discord.Embed(
		title=f"💰 Balance de {interaction.user.display_name}",
		description=f"**{currency_name}:** {balance['global_points']:,} {currency_symbol}",
		color=discord.Color.gold()
	)
	
	# ID y fecha en el footer
	now = datetime.now().strftime("%d/%m/%Y %H:%M")
	embed.set_footer(text=f"User Id: {user_lookup.user_id} • Consultado {now}")
	
	return embed


async def _show_discord_user_balance(
	bot: commands.Bot,
	interaction: discord.Interaction,
	target: discord.User,
	currency_name: str,
	currency_symbol: str
) -> discord.Embed:
	"""Muestra el balance de un usuario de Discord"""
	# Buscar usuario
	user_lookup = find_user_by_discord_id(str(target.id))
	
	# Si no existe, registrarlo automáticamente
	if not user_lookup:
		try:
			user, discord_profile, is_new = get_or_create_discord_user(
				discord_id=str(target.id),
				discord_username=target.name,
				avatar_url=str(target.display_avatar.url)
			)
			# Buscar de nuevo después de crear
			user_lookup = find_user_by_discord_id(str(target.id))
			if not user_lookup:
				return discord.Embed(
					title="❌ Error",
					description=f"No se pudo crear la cuenta de {target.mention}. Intenta nuevamente.",
					color=discord.Color.red()
				)
		except Exception as e:
			return discord.Embed(
				title="❌ Error",
				description=f"Error al registrar a {target.mention}: {str(e)}",
				color=discord.Color.red()
			)
	
	# Obtener balance
	balance = get_user_balance_by_id(user_lookup.user_id)
	
	if not balance or not balance["user_exists"]:
		return discord.Embed(
			title="❌ Error",
			description=f"No se pudo obtener el balance de {target.mention}.",
			color=discord.Color.red()
		)
	
	# Crear embed
	embed = discord.Embed(
		title=f"💰 Balance de {target.display_name}",
		description=f"**{currency_name}:** {balance['global_points']:,} {currency_symbol}",
		color=discord.Color.blue()
	)
	
	# ID y fecha en el footer
	now = datetime.now().strftime("%d/%m/%Y %H:%M")
	embed.set_footer(text=f"User Id: {user_lookup.user_id} • Consultado {now}")
	
	return embed


async def _show_global_id_balance(
	bot: commands.Bot,
	interaction: discord.Interaction,
	global_user_id: int,
	currency_name: str,
	currency_symbol: str
) -> discord.Embed:
	"""Muestra el balance de un usuario por ID universal"""
	# Buscar usuario por ID global
	user_lookup = find_user_by_global_id(global_user_id)
	
	if not user_lookup:
		return discord.Embed(
			title="❌ Usuario no encontrado",
			description=f"No existe ningún usuario con ID universal `{global_user_id}`.",
			color=discord.Color.red()
		)
	
	# Obtener balance
	balance = get_user_balance_by_id(user_lookup.user_id)
	
	if not balance or not balance["user_exists"]:
		return discord.Embed(
			title="❌ Error",
			description=f"No se pudo obtener el balance del usuario ID `{global_user_id}`.",
			color=discord.Color.red()
		)
	
	# Crear embed
	embed = discord.Embed(
		title=f"💰 Balance de {user_lookup.display_name}",
		description=f"**{currency_name}:** {balance['global_points']:,} {currency_symbol}",
		color=discord.Color.purple()
	)
	
	# Mostrar plataformas conectadas
	platforms_text = []
	if user_lookup.has_discord:
		platforms_text.append(f"✅ Discord: <@{user_lookup.discord_profile.discord_id}>")
	if user_lookup.has_youtube:
		platforms_text.append(f"✅ YouTube: {user_lookup.youtube_profile.youtube_username}")
	
	if platforms_text:
		embed.add_field(
			name="🔗 Plataformas",
			value="\n".join(platforms_text),
			inline=False
		)
	
	# ID y fecha en el footer
	now = datetime.now().strftime("%d/%m/%Y %H:%M")
	embed.set_footer(text=f"User Id: {global_user_id} • Consultado {now}")
	
	# Thumbnail si tiene Discord
	if user_lookup.discord_profile:
		try:
			discord_user = await bot.fetch_user(int(user_lookup.discord_profile.discord_id))
			embed.set_thumbnail(url=discord_user.display_avatar.url)
		except:
			pass
	
	return embed
