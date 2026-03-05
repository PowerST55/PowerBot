"""
Comandos de economía para usuarios normales.
Sistema de consulta de puntos y transacciones.
"""
import json
import time
import uuid
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Any
from datetime import datetime

from backend.managers.user_lookup_manager import find_user_by_discord_id, find_user_by_global_id
from backend.managers.economy_manager import get_user_balance_by_id, transfer_points
from backend.managers import get_or_create_discord_user
from backend.managers.avatar_manager import AvatarManager
from backend.services.discord_bot.config.economy import get_economy_config


def _project_root() -> Path:
	return Path(__file__).resolve().parents[5]


def _donation_data_dir() -> Path:
	path = _project_root() / "backend" / "data" / "discord_bot"
	path.mkdir(parents=True, exist_ok=True)
	return path


def _donation_index_file(guild_id: int) -> Path:
	return _donation_data_dir() / f"guild_{guild_id}_donation_buttons.json"


def _fmt_amount(value: float) -> str:
	return f"{float(value):,.2f}"


async def _resolve_avatar_url_for_target(
	*,
	target_lookup: Any,
	target_discord_user: Optional[discord.User] = None,
) -> Optional[discord.File]:
	"""Obtiene avatar local cacheado y lo devuelve como attachment para embed."""
	avatar_rel_path: Optional[str] = None

	try:
		if target_discord_user is not None:
			avatar_rel_path = AvatarManager.get_avatar_local_path(
				str(target_discord_user.id),
				"discord",
			)
		elif target_lookup and target_lookup.discord_profile:
			avatar_rel_path = AvatarManager.get_avatar_local_path(
				str(target_lookup.discord_profile.discord_id),
				"discord",
			)
		elif target_lookup and target_lookup.youtube_profile:
			avatar_rel_path = AvatarManager.get_avatar_local_path(
				str(target_lookup.youtube_profile.youtube_channel_id or target_lookup.user_id),
				"youtube",
			)

		if not avatar_rel_path:
			return None

		avatar_abs = _project_root() / avatar_rel_path
		if not avatar_abs.exists() or not avatar_abs.is_file():
			return None

		return discord.File(avatar_abs, filename=avatar_abs.name)
	except Exception:
		return None


class DonationButtonRegistry:
	"""Persistencia de paneles de donación por servidor."""

	@staticmethod
	def _load(guild_id: int) -> dict[str, Any]:
		path = _donation_index_file(guild_id)
		if not path.exists():
			return {"buttons": []}
		try:
			with open(path, "r", encoding="utf-8") as file:
				data = json.load(file)
				if isinstance(data, dict) and isinstance(data.get("buttons"), list):
					return data
		except Exception:
			pass
		return {"buttons": []}

	@staticmethod
	def _save(guild_id: int, payload: dict[str, Any]) -> None:
		path = _donation_index_file(guild_id)
		with open(path, "w", encoding="utf-8") as file:
			json.dump(payload, file, indent=2, ensure_ascii=False)

	@staticmethod
	async def _disable_panel(bot: commands.Bot, guild_id: int, entry: dict[str, Any]) -> None:
		channel_id = entry.get("channel_id")
		message_id = entry.get("message_id")
		if not channel_id or not message_id:
			return

		guild = bot.get_guild(int(guild_id))
		channel = None
		if guild is not None:
			channel = guild.get_channel(int(channel_id))
		if channel is None:
			channel = bot.get_channel(int(channel_id))
		if channel is None:
			try:
				channel = await bot.fetch_channel(int(channel_id))
			except Exception:
				return

		try:
			message = await channel.fetch_message(int(message_id))
			await message.edit(view=None)
		except Exception:
			return

	@staticmethod
	async def register(
		bot: commands.Bot,
		guild_id: int,
		entry: dict[str, Any],
		max_active_per_owner: int = 2,
	) -> int:
		"""Registra panel nuevo y elimina el más antiguo si supera el límite por owner."""
		data = DonationButtonRegistry._load(guild_id)
		buttons: list[dict[str, Any]] = [
			button for button in data.get("buttons", []) if isinstance(button, dict)
		]

		buttons.append(entry)
		owner_user_id = int(entry.get("owner_user_id"))
		owner_buttons = sorted(
			[
				button
				for button in buttons
				if int(button.get("owner_user_id", -1)) == owner_user_id
			],
			key=lambda button: float(button.get("created_ts", 0)),
		)

		removed = 0
		while len(owner_buttons) > max_active_per_owner:
			oldest = owner_buttons.pop(0)
			oldest_donation_id = str(oldest.get("donation_id"))
			buttons = [
				button
				for button in buttons
				if str(button.get("donation_id")) != oldest_donation_id
			]
			removed += 1
			await DonationButtonRegistry._disable_panel(bot, guild_id, oldest)

		data["buttons"] = buttons
		DonationButtonRegistry._save(guild_id, data)
		return removed

	@staticmethod
	def list_entries(guild_id: int) -> list[dict[str, Any]]:
		data = DonationButtonRegistry._load(guild_id)
		return [button for button in data.get("buttons", []) if isinstance(button, dict)]


class DonationConfirmView(discord.ui.View):
	"""Confirmación efímera previa a donar."""

	def __init__(
		self,
		*,
		target_user_id: int,
		target_label: str,
		amount: float,
		currency_symbol: str,
		target_discord_id: Optional[int] = None,
	):
		super().__init__(timeout=60)
		self.target_user_id = int(target_user_id)
		self.target_label = target_label
		self.target_discord_id = int(target_discord_id) if target_discord_id is not None else None
		self.amount = round(float(amount), 2)
		self.currency_symbol = currency_symbol

	@discord.ui.button(label="✅ Confirmar donación", style=discord.ButtonStyle.green)
	async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.guild is None:
			await interaction.response.send_message("Este botón solo funciona en servidor.", ephemeral=True)
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

		recipient_lookup = None
		if self.target_discord_id is not None:
			recipient_lookup = find_user_by_discord_id(str(self.target_discord_id))
			if recipient_lookup is None:
				target_user = interaction.client.get_user(self.target_discord_id)
				if target_user is None:
					try:
						target_user = await interaction.client.fetch_user(self.target_discord_id)
					except Exception:
						target_user = None
				if target_user is not None:
					try:
						get_or_create_discord_user(
							discord_id=str(target_user.id),
							discord_username=target_user.name,
							avatar_url=str(target_user.display_avatar.url),
						)
					except Exception:
						pass
					recipient_lookup = find_user_by_discord_id(str(self.target_discord_id))

		if recipient_lookup is None:
			recipient_lookup = find_user_by_global_id(self.target_user_id)

		if not recipient_lookup:
			await interaction.response.send_message("❌ No se pudo registrar al destinatario.", ephemeral=True)
			return

		if sender_lookup.user_id == recipient_lookup.user_id:
			await interaction.response.send_message("No puedes donarte a ti mismo.", ephemeral=True)
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
				f"Has donado **{_fmt_amount(self.amount)} {self.currency_symbol}** a {self.target_label}\n"
				f"💸 Tu nuevo balance: **{_fmt_amount(float(result['from_balance']))} {self.currency_symbol}**"
			),
			color=discord.Color.green()
		)
		embed.set_footer(text=f"Donación • {datetime.now().strftime('%d/%m/%Y %H:%M')}")
		await interaction.response.send_message(embed=embed, ephemeral=True)

		if self.target_discord_id is not None:
			try:
				target_user = interaction.client.get_user(self.target_discord_id)
				if target_user is None:
					target_user = await interaction.client.fetch_user(self.target_discord_id)
				notify_embed = discord.Embed(
					title="🎁 Has recibido una donación",
					description=(
						f"{interaction.user.mention} te donó **{_fmt_amount(self.amount)} {self.currency_symbol}**\n"
						f"💰 Tu nuevo balance: **{_fmt_amount(float(result['to_balance']))} {self.currency_symbol}**"
					),
					color=discord.Color.gold()
				)
				notify_embed.set_footer(text=f"Donación • {datetime.now().strftime('%d/%m/%Y %H:%M')}")
				await target_user.send(embed=notify_embed)
			except Exception:
				pass

	@discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
	async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		await interaction.response.send_message("Donación cancelada.", ephemeral=True)


class DonationView(discord.ui.View):
	"""Botón público para que otros usuarios donen el monto fijo."""

	def __init__(
		self,
		*,
		target_user_id: int,
		target_label: str,
		amount: float,
		currency_symbol: str,
		custom_id: str,
		target_discord_id: Optional[int] = None,
	):
		super().__init__(timeout=None)
		self.target_user_id = int(target_user_id)
		self.target_label = target_label
		self.target_discord_id = int(target_discord_id) if target_discord_id is not None else None
		self.amount = round(float(amount), 2)
		self.currency_symbol = currency_symbol
		self.custom_id = custom_id

		donate_button = discord.ui.Button(
			label="💸 Donar",
			style=discord.ButtonStyle.success,
			custom_id=self.custom_id,
		)
		donate_button.callback = self._on_donate_click
		self.add_item(donate_button)

	async def _on_donate_click(self, interaction: discord.Interaction):
		confirm_view = DonationConfirmView(
			target_user_id=self.target_user_id,
			target_label=self.target_label,
			amount=self.amount,
			currency_symbol=self.currency_symbol,
			target_discord_id=self.target_discord_id,
		)
		embed = discord.Embed(
			title="Confirmar donación",
			description=(
				f"¿Seguro que quieres donar **{_fmt_amount(self.amount)} {self.currency_symbol}**"
				f" a {self.target_label}?"
			),
			color=discord.Color.blurple(),
		)
		await interaction.response.send_message(embed=embed, ephemeral=True, view=confirm_view)


def _build_donation_custom_id(guild_id: int, donation_id: str) -> str:
	return f"powerbot:donation:{guild_id}:{donation_id}"


async def register_persistent_donation_buttons(bot: commands.Bot) -> None:
	"""Re-registra vistas persistentes de donación tras reinicios del bot."""
	for guild in bot.guilds:
		for entry in DonationButtonRegistry.list_entries(guild.id):
			try:
				view = DonationView(
					target_user_id=int(entry["target_user_id"]),
					target_label=str(entry["target_label"]),
					amount=float(entry["amount"]),
					currency_symbol=str(entry["currency_symbol"]),
					custom_id=str(entry["custom_id"]),
					target_discord_id=int(entry["target_discord_id"])
					if entry.get("target_discord_id") is not None
					else None,
				)
				bot.add_view(view)
			except Exception:
				continue


async def send_donation_embed(
	interaction: discord.Interaction,
	amount: float,
	target_discord_user: Optional[discord.User] = None,
	target_global_user_id: Optional[int] = None,
) -> discord.Embed:
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

	if target_discord_user is not None and target_global_user_id is not None:
		return discord.Embed(
			title="❌ Parámetros inválidos",
			description="Usa solo @usuario o ID universal, no ambos.",
			color=discord.Color.red(),
		)

	economy_config = get_economy_config(interaction.guild.id)
	currency_symbol = economy_config.get_currency_symbol()

	if target_discord_user is None and target_global_user_id is None:
		target_discord_user = interaction.user

	target_lookup = None
	target_label = ""
	target_avatar_url: Optional[str] = None
	target_discord_id: Optional[int] = None

	if target_discord_user is not None:
		target_discord_id = int(target_discord_user.id)
		target_lookup = find_user_by_discord_id(str(target_discord_user.id))
		if not target_lookup:
			try:
				get_or_create_discord_user(
					discord_id=str(target_discord_user.id),
					discord_username=target_discord_user.name,
					avatar_url=str(target_discord_user.display_avatar.url),
				)
			except Exception:
				pass
			target_lookup = find_user_by_discord_id(str(target_discord_user.id))

		if not target_lookup:
			return discord.Embed(
				title="❌ Error",
				description="No se pudo registrar al destinatario de la donación.",
				color=discord.Color.red(),
			)

		target_label = target_discord_user.mention
	else:
		candidate_id = int(target_global_user_id)
		target_lookup = find_user_by_global_id(candidate_id)

		# Fallback: permitir que el campo user_id acepte también Discord ID.
		if not target_lookup:
			discord_lookup = find_user_by_discord_id(str(candidate_id))
			if discord_lookup:
				target_lookup = discord_lookup

		if not target_lookup:
			return discord.Embed(
				title="❌ Usuario no encontrado",
				description=(
					f"No existe ningún usuario con ID universal `{target_global_user_id}` "
					"ni con ese Discord ID."
				),
				color=discord.Color.red(),
			)

		if target_lookup.discord_profile:
			target_discord_id = int(target_lookup.discord_profile.discord_id)
			target_label = f"<@{target_discord_id}>"
		else:
			target_label = f"**{target_lookup.display_name}**"

	target_avatar_file = await _resolve_avatar_url_for_target(
		target_lookup=target_lookup,
		target_discord_user=target_discord_user,
	)

	target_user_id = int(target_lookup.user_id)
	donation_id = uuid.uuid4().hex[:12]
	custom_id = _build_donation_custom_id(interaction.guild.id, donation_id)

	embed = discord.Embed(
		title="🎁 Donación abierta",
		description=(
			f"**Destino:** `ID:{target_user_id}` {target_label}\n"
			f"**Monto por click:** **{_fmt_amount(amount)} {currency_symbol}**\n\n"
			"Pulsa el botón para donar ese monto."
		),
		color=discord.Color.gold(),
	)
	files: list[discord.File] = []
	if target_avatar_file is not None:
		embed.set_thumbnail(url=f"attachment://{target_avatar_file.filename}")
		files.append(target_avatar_file)
	embed.set_footer(text=f"Creado • {datetime.now().strftime('%d/%m/%Y %H:%M')}")

	view = DonationView(
		target_user_id=target_user_id,
		target_label=target_label,
		amount=amount,
		currency_symbol=currency_symbol,
		custom_id=custom_id,
		target_discord_id=target_discord_id,
	)
	if interaction.channel is None:
		return discord.Embed(
			title="❌ Error",
			description="No se pudo publicar el panel en este canal.",
			color=discord.Color.red(),
		)

	message = await interaction.channel.send(
		embed=embed,
		view=view,
		files=files if files else None,
	)

	entry = {
		"donation_id": donation_id,
		"custom_id": custom_id,
		"owner_user_id": target_user_id,
		"target_user_id": target_user_id,
		"target_label": target_label,
		"target_discord_id": target_discord_id,
		"amount": amount,
		"currency_symbol": currency_symbol,
		"channel_id": int(message.channel.id),
		"message_id": int(message.id),
		"created_by_discord_id": int(interaction.user.id),
		"created_ts": time.time(),
	}
	removed = await DonationButtonRegistry.register(
		bot=interaction.client,
		guild_id=interaction.guild.id,
		entry=entry,
		max_active_per_owner=2,
	)
	interaction.client.add_view(view)

	confirm_text = "Tu panel de donación se publicó en este canal."
	if removed > 0:
		confirm_text += " Se reemplazó el panel más antiguo para respetar el límite de 2 activos."
	return discord.Embed(
		title="✅ Publicado",
		description=confirm_text,
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
