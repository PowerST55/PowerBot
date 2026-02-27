"""
Comandos generales para PowerBot Discord.
"""
import discord
import asyncio
from discord import app_commands
from discord.ext import commands
from typing import Optional

from backend.managers.user_lookup_manager import find_user_by_discord_id, find_user_by_global_id
from backend.managers.economy_manager import get_user_balance_by_id
from backend.managers import inventory_manager
from backend.services.discord_bot.commands.economy.user_economy import send_donation_embed


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
		await interaction.response.defer()
		result_embed = await send_donation_embed(interaction, amount)
		await interaction.followup.send(embed=result_embed, ephemeral=True)

	bot.tree.add_command(crear_group)

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

		# **AQUÍ en el thread principal: si es búsqueda por ID de Discord, obtener avatar en tiempo real**
		if target is None and lookup.has_discord and lookup.discord_profile:
			try:
				# Obtener usuario de Discord en tiempo real del cache del bot
				discord_user = interaction.client.get_user(int(lookup.discord_profile.discord_id))
				if discord_user:
					user_info['avatar_url'] = str(discord_user.display_avatar.url)
			except (ValueError, TypeError):
				pass  # Usar lo que esté en user_info['avatar_url'] (de BD, si existe)

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
