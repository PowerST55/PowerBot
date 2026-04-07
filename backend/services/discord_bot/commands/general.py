"""
Comandos generales para PowerBot Discord.
"""
import discord
import asyncio
from discord import app_commands
from discord.ext import commands
from typing import Optional

from backend.managers.avatar_manager import AvatarManager
from backend.managers.user_lookup_manager import find_user_by_discord_id, find_user_by_global_id
from backend.managers.economy_manager import get_user_balance_by_id
from backend.managers import inventory_manager
from backend.managers.user_manager import update_youtube_profile
from backend.services.discord_bot.commands.economy.user_economy import send_donation_embed
from backend.services.discord_bot.discord_avatar_packager import DiscordAvatarPackager
from backend.services.discord_bot.config.roles import get_roles_config


def setup_general_commands(bot: commands.Bot) -> None:
	"""Registra comandos generales"""

	crear_group = app_commands.Group(
		name="crear",
		description="Crear acciones públicas (ej. donación)"
	)

	@crear_group.command(
		name="donacion",
		description="Crea un panel para que otros te donen puntos"
	)
	@app_commands.describe(
		amount="Monto fijo que se donará al pulsar el botón"
	)
	async def crear_donacion(
		interaction: discord.Interaction,
		amount: float,
	):
		await interaction.response.defer(ephemeral=True)
		result_embed = await send_donation_embed(interaction, amount)
		await interaction.followup.send(embed=result_embed, ephemeral=True)

	bot.tree.add_command(crear_group)

	@bot.tree.command(
		name="stream",
		description="Solicita por MD que el/los streamer(s) inicien stream"
	)
	@app_commands.describe(
		tematica="Temática opcional del stream (ej: roblox)"
	)
	async def stream_command(
		interaction: discord.Interaction,
		tematica: Optional[str] = None,
	):
		"""Envía un DM al usuario (o usuarios) con rol streamer configurado."""
		if interaction.guild is None:
			embed = discord.Embed(
				title="❌ Comando no disponible",
				description="Este comando solo se puede usar dentro de un servidor.",
				color=discord.Color.red(),
			)
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		roles_config = get_roles_config(interaction.guild.id)
		streamer_role_id = roles_config.get_role("streamer")
		if not streamer_role_id:
			embed = discord.Embed(
				title="⚠ Rol streamer no configurado",
				description="Primero configura el rol con `/set role streamer @rol`.",
				color=discord.Color.orange(),
			)
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		streamer_role = interaction.guild.get_role(int(streamer_role_id))
		if streamer_role is None:
			embed = discord.Embed(
				title="❌ Rol streamer inválido",
				description="El rol streamer guardado no existe en este servidor. Configúralo de nuevo con `/set role streamer @rol`.",
				color=discord.Color.red(),
			)
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		streamer_members = [member for member in streamer_role.members if not member.bot]
		if not streamer_members:
			embed = discord.Embed(
				title="⚠ No hay streamers disponibles",
				description=f"No encontré usuarios con el rol {streamer_role.mention}.",
				color=discord.Color.orange(),
			)
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		requester_mention = interaction.user.mention
		tematica_clean = str(tematica or "").strip()
		if tematica_clean:
			description = (
				f"{requester_mention} está solicitando que inicies un stream de la temática `{tematica_clean}`."
			)
		else:
			description = f"{requester_mention} te está pidiendo que inicies un stream."

		dm_embed = discord.Embed(
			title="📣 Solicitud de stream",
			description=description,
			color=discord.Color.blurple(),
		)
		dm_embed.add_field(name="Servidor", value=interaction.guild.name, inline=False)
		dm_embed.set_footer(text="PowerBot")

		sent_to: list[str] = []
		failed_to: list[str] = []

		for member in streamer_members:
			try:
				await member.send(embed=dm_embed)
				sent_to.append(member.mention)
			except discord.Forbidden:
				failed_to.append(member.mention)
			except Exception:
				failed_to.append(member.mention)

		if sent_to:
			confirm = discord.Embed(
				title="✅ Solicitud enviada",
				description="Se envió la solicitud de stream por MD.",
				color=discord.Color.green(),
			)
			confirm.add_field(name="Enviado a", value="\n".join(sent_to), inline=False)
			if failed_to:
				confirm.add_field(
					name="No se pudo enviar a",
					value="\n".join(failed_to),
					inline=False,
				)
			await interaction.response.send_message(embed=confirm, ephemeral=True)
			return

		error_embed = discord.Embed(
			title="❌ No se pudo enviar la solicitud",
			description="Ningún streamer acepta MDs o hubo un error al enviar.",
			color=discord.Color.red(),
		)
		error_embed.add_field(name="Usuarios", value="\n".join(failed_to), inline=False)
		await interaction.response.send_message(embed=error_embed, ephemeral=True)

	@bot.tree.command(
		name="say",
		description="Envía un mensaje como el bot en MD o, en servidor, solo para mods"
	)
	@app_commands.allowed_installs(guilds=True, users=True)
	@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
	@app_commands.describe(mensaje="El mensaje que enviará el bot")
	async def say_command(interaction: discord.Interaction, mensaje: str):
		"""Envía un mensaje como el bot: libre en MD y restringido a mods en servidor."""
		if interaction.guild is not None:
			member = interaction.user
			if not isinstance(member, discord.Member) or not (
				member.guild_permissions.administrator
				or member.guild_permissions.moderate_members
			):
				embed = discord.Embed(
					title="❌ Acceso denegado",
					description="Solo los moderadores pueden usar este comando dentro del servidor.",
					color=discord.Color.red(),
				)
				await interaction.response.send_message(embed=embed, ephemeral=True)
				return

		try:
			channel_label = "este chat MD"
			if interaction.guild is not None and interaction.channel is not None:
				channel_label = interaction.channel.mention

			confirm_embed = discord.Embed(
				title="✅ Mensaje enviado",
				description=f"Tu mensaje ha sido publicado en {channel_label}.",
				color=discord.Color.green(),
			)
			await interaction.response.send_message(embed=confirm_embed, ephemeral=True)
			await interaction.channel.send(mensaje)
		except discord.Forbidden:
			embed = discord.Embed(
				title="❌ Error de permisos",
				description="El bot no pudo enviar el mensaje en este chat.",
				color=discord.Color.red(),
			)
			if interaction.response.is_done():
				await interaction.followup.send(embed=embed, ephemeral=True)
			else:
				await interaction.response.send_message(embed=embed, ephemeral=True)
		except Exception as e:
			embed = discord.Embed(
				title="❌ Error",
				description=f"Ocurrió un error: {str(e)}",
				color=discord.Color.red(),
			)
			if interaction.response.is_done():
				await interaction.followup.send(embed=embed, ephemeral=True)
			else:
				await interaction.response.send_message(embed=embed, ephemeral=True)

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

		# Función helper para cargar datos de forma síncrona
		def load_user_data(target_id=None, user_global_id=None):
			if target_id is not None:
				return find_user_by_discord_id(target_id)
			else:
				return find_user_by_global_id(user_global_id)
		
		def get_user_info(lookup, target_obj=None):
			"""Carga TODA la información del usuario aquí en el executor"""
			if target_obj is not None:
				display_name = target_obj.display_name
				avatar_url = str(target_obj.display_avatar.url)
			else:
				display_name = lookup.display_name
				avatar_url = None
				
				# Prioridad: Discord > YouTube para el avatar del embed
				# Nota: Para usuarios de Discord buscados por ID, se obtiene el avatar en el thread principal
				if lookup.discord_profile and lookup.discord_profile.avatar_url:
					avatar_url = lookup.discord_profile.avatar_url
				elif lookup.youtube_profile and lookup.youtube_profile.channel_avatar_url:
					avatar_url = lookup.youtube_profile.channel_avatar_url
			
			balance = get_user_balance_by_id(lookup.user_id)
			points = balance.get("global_points", 0) if balance.get("user_exists") else 0
			points = round(float(points), 2)
			
			inventory_stats = inventory_manager.get_inventory_stats(lookup.user_id)
			total_quantity = inventory_stats.get("total_quantity", 0)
			
			# Precargar información de plataformas aquí
			has_discord = lookup.has_discord
			has_youtube = lookup.has_youtube
			
			discord_info = None
			if lookup.discord_profile:
				discord_info = {
					'username': lookup.discord_profile.discord_username or "Desconocido",
					'id': lookup.discord_profile.discord_id
				}
			
			youtube_info = None
			if lookup.youtube_profile:
				youtube_info = {
					'username': lookup.youtube_profile.youtube_username or "Desconocido",
					'channel_id': lookup.youtube_profile.youtube_channel_id or "Desconocido"
				}
			
			return {
				'user_id': lookup.user_id,
				'display_name': display_name,
				'avatar_url': avatar_url,
				'points': points,
				'total_quantity': total_quantity,
				'has_discord': has_discord,
				'has_youtube': has_youtube,
				'discord_info': discord_info,
				'youtube_info': youtube_info
			}

		async def resolve_discord_user(lookup_obj):
			"""Resuelve el usuario de Discord en tiempo real para refrescar avatar."""
			if target is not None:
				return target

			if not lookup_obj or not lookup_obj.has_discord or not lookup_obj.discord_profile:
				return None

			try:
				discord_id = int(lookup_obj.discord_profile.discord_id)
			except (TypeError, ValueError):
				return None

			if interaction.guild is not None:
				member = interaction.guild.get_member(discord_id)
				if member is not None:
					return member

			cached_user = interaction.client.get_user(discord_id)
			if cached_user is not None:
				return cached_user

			try:
				return await interaction.client.fetch_user(discord_id)
			except Exception:
				return None

		async def refresh_avatar_cache(lookup_obj) -> Optional[str]:
			"""Fuerza descarga/actualización del avatar al consultar /id."""
			discord_user = await resolve_discord_user(lookup_obj)
			if discord_user is not None and lookup_obj.discord_profile:
				fresh_avatar_url = str(discord_user.display_avatar.url)
				await asyncio.to_thread(
					DiscordAvatarPackager.download_and_update_avatar,
					lookup_obj.user_id,
					str(discord_user.id),
					fresh_avatar_url,
				)
				return fresh_avatar_url

			if lookup_obj.youtube_profile and lookup_obj.youtube_profile.channel_avatar_url:
				yt_avatar_url = str(lookup_obj.youtube_profile.channel_avatar_url).strip()
				if yt_avatar_url.startswith('http://') or yt_avatar_url.startswith('https://'):
					def _refresh_youtube_avatar() -> Optional[str]:
						cached_avatar = AvatarManager.download_avatar(
							user_id=str(lookup_obj.youtube_profile.youtube_channel_id),
							avatar_url_remote=yt_avatar_url,
							platform="youtube",
						)
						if cached_avatar:
							update_youtube_profile(
								user_id=lookup_obj.user_id,
								channel_avatar_url=cached_avatar,
							)
						return cached_avatar

					refreshed_yt_avatar = await asyncio.to_thread(_refresh_youtube_avatar)
					if refreshed_yt_avatar:
						return refreshed_yt_avatar

				return yt_avatar_url

			return None

		# Ejecutar las operaciones síncronas en un thread para no bloquear el bot
		loop = asyncio.get_event_loop()
		
		# Cargar lookup del usuario
		lookup = await loop.run_in_executor(None, load_user_data, 
			str(target.id) if target else None, user_id)
		
		if not lookup:
			embed = discord.Embed(
				title="❌ Usuario no encontrado",
				description=f"No existe registro para {target.mention if target else f'ID universal: {user_id}'}.",
				color=discord.Color.red()
			)
			await interaction.followup.send(embed=embed, ephemeral=True)
			return
		
		# Cargar info del usuario (TODA la información aquí, sin lazy loading después)
		user_info = await loop.run_in_executor(None, get_user_info, lookup, target)

		# Forzar descarga/actualización del avatar al consultar /id.
		refreshed_avatar_url = await refresh_avatar_cache(lookup)
		if refreshed_avatar_url:
			user_info['avatar_url'] = refreshed_avatar_url

		# Ya NO accedemos a los perfiles en el thread principal, usamos los datos precargados
		platforms = []
		if user_info['has_discord']:
			platforms.append("Discord")
		if user_info['has_youtube']:
			platforms.append("YouTube")

		platforms_text = " y ".join(platforms) if platforms else "Sin plataformas"

		embed = discord.Embed(
			title=f"🧾 ID de {user_info['display_name']}",
			description=f"**ID Universal:** `{user_info['user_id']}`",
			color=discord.Color.blue()
		)

		embed.add_field(
			name="💰 Puntos",
			value=f"{user_info['points']:,.2f}",
			inline=True
		)
		embed.add_field(
			name="🎒 Inventario",
			value=f"{user_info['total_quantity']} items",
			inline=True
		)
		embed.add_field(
			name="🔗 Plataformas",
			value=platforms_text,
			inline=False
		)

		# Usar datos precargados, NO acceder a los perfiles aquí
		if user_info['discord_info']:
			embed.add_field(
				name="Discord",
				value=f"{user_info['discord_info']['username']} (`{user_info['discord_info']['id']}`)",
				inline=False
			)

		if user_info['youtube_info']:
			embed.add_field(
				name="YouTube",
				value=f"{user_info['youtube_info']['username']} (`{user_info['youtube_info']['channel_id']}`)",
				inline=False
			)

		if user_info['avatar_url']:
			# Solo establecer thumbnail si es una URL válida (http/https)
			if user_info['avatar_url'].startswith('http://') or user_info['avatar_url'].startswith('https://'):
				embed.set_thumbnail(url=user_info['avatar_url'])

		await interaction.followup.send(embed=embed)
