"""
Comandos administrativos relacionados a la tienda (canal tipo foro).
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from backend.services.discord_bot.config import get_channels_config
from backend.services.discord_bot.config.store import get_store_config
from backend.services.discord_bot.bot_logging import log_success, log_error
from backend.services.discord_bot.store.store_packager import DiscordStorePackager


def setup_store_admin_commands(bot: commands.Bot) -> None:
	"""Registra el grupo /admin_store."""

	admin_store_group = app_commands.Group(
		name="admin_store",
		description="Herramientas de administración para la tienda",
	)

	async def _create_forum_channel_compat(
		guild: discord.Guild,
		*,
		name: str,
		topic: str,
		reason: str,
		default_auto_archive_duration: int,
		default_thread_slowmode_delay: int,
	) -> discord.abc.GuildChannel:
		"""Crea un canal foro y valida compatibilidad con la versión instalada."""
		if not hasattr(guild, "create_forum"):
			raise RuntimeError(
				"Tu versión de discord.py no soporta foros. Actualiza a 2.1+ para usar /admin_store."
			)

		return await guild.create_forum(
			name=name,
			topic=topic,
			reason=reason,
			default_auto_archive_duration=default_auto_archive_duration,
			default_thread_slowmode_delay=default_thread_slowmode_delay,
		)

	@admin_store_group.command(name="create", description="Crea el canal foro oficial de la tienda")
	async def admin_store_create(interaction: discord.Interaction) -> None:
		if interaction.guild is None:
			await interaction.response.send_message(
				"Este comando solo puede ejecutarse dentro de un servidor.",
				ephemeral=True,
			)
			return

		if not interaction.user.guild_permissions.administrator:
			embed = discord.Embed(
				title="❌ Permiso denegado",
				description="Solo administradores pueden usar /admin_store.",
				color=discord.Color.red(),
			)
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		store_config = get_store_config(interaction.guild.id)
		existing_channel_id = store_config.get_forum_channel_id()
		if existing_channel_id:
			existing_channel = interaction.guild.get_channel(existing_channel_id) or interaction.client.get_channel(
				existing_channel_id
			)
			if existing_channel is not None:
				embed = discord.Embed(
					title="ℹ️ Canal ya configurado",
					description=(
						"Ya existe un canal registrado para la tienda."
						" Si deseas recrearlo, elimina el foro actual y borra el archivo de config o"
						" remueve la entrada manualmente."
					),
					color=discord.Color.orange(),
				)
				embed.add_field(name="Canal", value=existing_channel.mention, inline=True)
				embed.add_field(name="ID", value=f"`{existing_channel_id}`", inline=True)
				await interaction.response.send_message(embed=embed, ephemeral=True)
				return
			store_config.clear_forum_channel()

		await interaction.response.defer(ephemeral=True)

		topic = (
			"Foro oficial de la tienda PowerBot. Crea un hilo por cada item,"
			" describe rarezas, precios y adjunta imágenes desde aquí."
		)
		reason = f"Solicitado por {interaction.user} mediante /admin_store create"
		default_archive = 1440
		slowmode = 5

		try:
			forum_channel = await _create_forum_channel_compat(
				interaction.guild,
				name="powerbot-store",
				topic=topic,
				reason=reason,
				default_auto_archive_duration=default_archive,
				default_thread_slowmode_delay=slowmode,
			)
		except discord.Forbidden:
			embed = discord.Embed(
				title="❌ Sin permisos",
				description="No tengo permisos para crear canales. Asegúrate de que el bot pueda gestionar canales.",
				color=discord.Color.red(),
			)
			await interaction.followup.send(embed=embed, ephemeral=True)
			await log_error(
				bot,
				interaction.guild.id,
				"Creación de tienda fallida",
				"El bot no tiene permisos para crear canales.",
				fields={"Comando": "/admin_store create"},
				user=interaction.user,
			)
			return
		except RuntimeError as exc:
			embed = discord.Embed(
				title="⚠️ Versión incompatible",
				description=(
					"El bot necesita una versión de discord.py compatible con foros (2.1+).\n"
					"Mensaje: " + str(exc)
				),
				color=discord.Color.orange(),
			)
			await interaction.followup.send(embed=embed, ephemeral=True)
			await log_error(
				bot,
				interaction.guild.id,
				"Creación de tienda fallida",
				"La librería discord.py instalada no soporta canales tipo foro.",
				fields={"Comando": "/admin_store create"},
				user=interaction.user,
			)
			return
		except discord.HTTPException as exc:
			embed = discord.Embed(
				title="❌ Error creando el foro",
				description=f"Discord respondió con un error: `{exc}`",
				color=discord.Color.red(),
			)
			await interaction.followup.send(embed=embed, ephemeral=True)
			await log_error(
				bot,
				interaction.guild.id,
				"Creación de tienda fallida",
				f"Discord retornó HTTPException: {exc}",
				fields={"Comando": "/admin_store create"},
				user=interaction.user,
			)
			return

		except Exception as exc:
			embed = discord.Embed(
				title="❌ Error inesperado",
				description=(
					"No se pudo crear la tienda. Revisa la consola para más detalles.\n"
					"Error: " + str(exc)
				),
				color=discord.Color.red(),
			)
			print(f"⚠️ Error creando foro de tienda en guild {interaction.guild.id}: {exc}")
			await interaction.followup.send(embed=embed, ephemeral=True)
			await log_error(
				bot,
				interaction.guild.id,
				"Creación de tienda fallida",
				f"Excepción inesperada: {exc}",
				fields={"Comando": "/admin_store create"},
				user=interaction.user,
			)
			return

		store_config.set_forum_channel(
			channel_id=forum_channel.id,
			name=forum_channel.name,
			created_by=interaction.user.id,
			topic=topic,
		)

		try:
			channels_config = get_channels_config(interaction.guild.id)
			channels_config.set_channel("store_forum_channel", forum_channel.id)
		except Exception as exc:  # No queremos romper la experiencia si falla el guardado auxiliar
			print(f"⚠️ No se pudo actualizar store_forum_channel en channels config: {exc}")

		sync_result = None
		sync_error = None
		try:
			sync_result = await DiscordStorePackager.publish_store_for_guild(
				bot=bot,
				guild_id=interaction.guild.id,
				force_republish=False,
			)
		except Exception as exc:
			sync_error = str(exc)

		embed = discord.Embed(
			title="🛒 Foro de tienda creado",
			description="Se configuró el foro oficial de la tienda y se guardó en data/discord_bot.",
			color=discord.Color.green(),
		)
		embed.add_field(name="Canal", value=forum_channel.mention, inline=True)
		embed.add_field(name="ID", value=f"`{forum_channel.id}`", inline=True)
		embed.add_field(
			name="Archivo",
			value=f"`data/discord_bot/guild_{interaction.guild.id}_store.json`",
			inline=False,
		)
		if isinstance(sync_result, dict):
			embed.add_field(
				name="Sync inicial",
				value=(
					f"Publicados: `{sync_result.get('published', 0)}`\n"
					f"Omitidos: `{sync_result.get('skipped', 0)}`\n"
					f"Fallidos: `{sync_result.get('failed', 0)}`"
				),
				inline=False,
			)
			sync_catalog = sync_result.get("sync", {}) if isinstance(sync_result.get("sync"), dict) else {}
			embed.add_field(
				name="Catálogo inicial",
				value=(
					f"Total assets: `{sync_catalog.get('total', 0)}`\n"
					f"Cargados: `{sync_catalog.get('loaded', 0)}`\n"
					f"Inválidos: `{sync_catalog.get('invalid', 0)}`"
				),
				inline=False,
			)
		elif sync_error:
			embed.add_field(
				name="Sync inicial",
				value=f"No se pudo sincronizar automáticamente: `{sync_error}`",
				inline=False,
			)
		embed.set_footer(text="/admin_store create • Configuración guardada")

		await log_success(
			bot,
			interaction.guild.id,
			"Tienda creada",
			f"Se creó {forum_channel.mention} mediante /admin_store create",
			fields={
				"Canal": f"#{forum_channel.name}",
				"Canal ID": forum_channel.id,
			},
			user=interaction.user,
		)

		await interaction.followup.send(embed=embed, ephemeral=True)

	@admin_store_group.command(name="sync", description="Sincroniza/publica los items de la tienda en el foro")
	@app_commands.describe(force="Si es true, vuelve a publicar aunque ya exista hilo")
	async def admin_store_sync(interaction: discord.Interaction, force: bool = False) -> None:
		if interaction.guild is None:
			await interaction.response.send_message(
				"Este comando solo puede ejecutarse dentro de un servidor.",
				ephemeral=True,
			)
			return

		if not interaction.user.guild_permissions.administrator:
			embed = discord.Embed(
				title="❌ Permiso denegado",
				description="Solo administradores pueden usar /admin_store.",
				color=discord.Color.red(),
			)
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		await interaction.response.defer(ephemeral=True)

		try:
			result = await DiscordStorePackager.publish_store_for_guild(
				bot=bot,
				guild_id=interaction.guild.id,
				force_republish=force,
			)
		except Exception as exc:
			embed = discord.Embed(
				title="❌ Error sincronizando tienda",
				description=f"Excepción inesperada: `{exc}`",
				color=discord.Color.red(),
			)
			await interaction.followup.send(embed=embed, ephemeral=True)
			await log_error(
				bot,
				interaction.guild.id,
				"Sync tienda fallida",
				f"Excepción inesperada en /admin_store sync: {exc}",
				fields={"Comando": "/admin_store sync"},
				user=interaction.user,
			)
			return

		if not result.get("success", False):
			embed = discord.Embed(
				title="⚠️ Sync de tienda con problemas",
				description=str(result.get("message", "No se pudo completar la sincronización.")),
				color=discord.Color.orange(),
			)
			embed.add_field(name="Publicados", value=f"`{result.get('published', 0)}`", inline=True)
			embed.add_field(name="Omitidos", value=f"`{result.get('skipped', 0)}`", inline=True)
			embed.add_field(name="Fallidos", value=f"`{result.get('failed', 0)}`", inline=True)
			await interaction.followup.send(embed=embed, ephemeral=True)
			await log_error(
				bot,
				interaction.guild.id,
				"Sync tienda con errores",
				str(result.get("message", "Store sync fallida")),
				fields={
					"Publicados": result.get("published", 0),
					"Omitidos": result.get("skipped", 0),
					"Fallidos": result.get("failed", 0),
				},
				user=interaction.user,
			)
			return

		embed = discord.Embed(
			title="✅ Tienda sincronizada",
			description="Se publicó/sincronizó el catálogo en el foro de tienda.",
			color=discord.Color.green(),
		)
		embed.add_field(name="Publicados", value=f"`{result.get('published', 0)}`", inline=True)
		embed.add_field(name="Omitidos", value=f"`{result.get('skipped', 0)}`", inline=True)
		embed.add_field(name="Fallidos", value=f"`{result.get('failed', 0)}`", inline=True)

		sync = result.get("sync", {}) if isinstance(result.get("sync"), dict) else {}
		embed.add_field(
			name="Catálogo",
			value=(
				f"Total assets: `{sync.get('total', 0)}`\n"
				f"Cargados: `{sync.get('loaded', 0)}`\n"
				f"Inválidos: `{sync.get('invalid', 0)}`"
			),
			inline=False,
		)
		embed.set_footer(text=f"/admin_store sync • force={force}")

		await interaction.followup.send(embed=embed, ephemeral=True)
		await log_success(
			bot,
			interaction.guild.id,
			"Sync tienda completada",
			"Se sincronizó el catálogo de tienda en el foro.",
			fields={
				"Publicados": result.get("published", 0),
				"Omitidos": result.get("skipped", 0),
				"Fallidos": result.get("failed", 0),
				"Force": force,
			},
			user=interaction.user,
		)

	bot.tree.add_command(admin_store_group)


__all__ = ["setup_store_admin_commands"]
