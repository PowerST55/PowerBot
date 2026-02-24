"""
Comandos administrativos de vinculación forzada para Discord.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from backend.managers.link_manager import force_link_discord_to_universal, force_unlink_discord
from backend.managers.user_lookup_manager import find_user_by_global_id
from backend.services.discord_bot.bot_logging import log_moderation
from backend.services.discord_bot.config.roles import get_roles_config


def _is_moderator(interaction: discord.Interaction) -> bool:
	if not interaction.guild or not isinstance(interaction.user, discord.Member):
		return False

	member: discord.Member = interaction.user
	perms = member.guild_permissions
	if perms.administrator or perms.manage_guild:
		return True

	cfg = get_roles_config(interaction.guild.id)
	mod_roles = {int(role_id) for role_id in cfg.get_mod_roles()}
	if not mod_roles:
		return False

	user_roles = {role.id for role in member.roles}
	return bool(mod_roles.intersection(user_roles))


def moderator_only():
	async def predicate(interaction: discord.Interaction) -> bool:
		return _is_moderator(interaction)
	return app_commands.check(predicate)


def setup_link_admin_commands(bot: commands.Bot) -> None:
	"""Registra comandos slash administrativos para force link/unlink."""

	@bot.tree.command(
		name="force_link",
		description="(MOD) Vincula forzadamente un Discord a un ID universal de YouTube",
	)
	@app_commands.describe(
		usuario="Usuario de Discord a vincular",
		id_universal="ID universal correspondiente a YouTube",
	)
	@moderator_only()
	async def force_link(
		interaction: discord.Interaction,
		usuario: discord.Member,
		id_universal: str,
	):
		if not interaction.guild:
			await interaction.response.send_message("❌ Este comando solo funciona en servidor.", ephemeral=True)
			return

		id_token = str(id_universal).strip()
		if not id_token.isdigit():
			await interaction.response.send_message("❌ El ID universal debe ser numérico.", ephemeral=True)
			return

		target_id = int(id_token)
		lookup = find_user_by_global_id(target_id)
		if not lookup:
			await interaction.response.send_message(
				f"❌ No existe usuario con ID universal `{target_id}`.",
				ephemeral=True,
			)
			return

		if not lookup.youtube_profile:
			await interaction.response.send_message(
				"❌ Ese ID universal no corresponde a una cuenta de YouTube.",
				ephemeral=True,
			)
			return

		result = force_link_discord_to_universal(
			discord_user_id=str(usuario.id),
			discord_user_name=usuario.name,
			universal_user_id=target_id,
		)

		if not result.success:
			await interaction.response.send_message(f"❌ {result.message}", ephemeral=True)
			await log_moderation(
				bot=bot,
				guild_id=interaction.guild.id,
				title="Force Link fallido",
				description=result.message,
				fields={
					"Discord objetivo": f"{usuario} ({usuario.id})",
					"ID universal": str(target_id),
				},
				user=usuario,
				moderator=interaction.user,
			)
			return

		await interaction.response.send_message(
			f"✅ Vinculación forzada completada: {usuario.mention} → ID `{target_id}`",
			ephemeral=True,
		)
		await log_moderation(
			bot=bot,
			guild_id=interaction.guild.id,
			title="Force Link ejecutado",
			description="Se vinculó forzadamente un usuario.",
			fields={
				"Discord objetivo": f"{usuario} ({usuario.id})",
				"ID universal": str(target_id),
				"Resultado": result.message,
			},
			user=usuario,
			moderator=interaction.user,
		)

	@bot.tree.command(
		name="force_unlink",
		description="(MOD) Desvincula forzadamente una cuenta de Discord",
	)
	@app_commands.describe(usuario="Usuario de Discord a desvincular")
	@moderator_only()
	async def force_unlink(interaction: discord.Interaction, usuario: discord.Member):
		if not interaction.guild:
			await interaction.response.send_message("❌ Este comando solo funciona en servidor.", ephemeral=True)
			return

		result = force_unlink_discord(str(usuario.id))
		if not result.success:
			await interaction.response.send_message(f"❌ {result.message}", ephemeral=True)
			await log_moderation(
				bot=bot,
				guild_id=interaction.guild.id,
				title="Force Unlink fallido",
				description=result.message,
				fields={
					"Discord objetivo": f"{usuario} ({usuario.id})",
				},
				user=usuario,
				moderator=interaction.user,
			)
			return

		await interaction.response.send_message(
			f"✅ Desvinculación forzada completada para {usuario.mention}",
			ephemeral=True,
		)
		await log_moderation(
			bot=bot,
			guild_id=interaction.guild.id,
			title="Force Unlink ejecutado",
			description=result.message,
			fields={
				"Discord objetivo": f"{usuario} ({usuario.id})",
			},
			user=usuario,
			moderator=interaction.user,
		)

	@force_link.error
	async def on_force_link_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
		if isinstance(error, app_commands.CheckFailure):
			if interaction.response.is_done():
				await interaction.followup.send("❌ Solo moderadores pueden usar este comando.", ephemeral=True)
			else:
				await interaction.response.send_message("❌ Solo moderadores pueden usar este comando.", ephemeral=True)

	@force_unlink.error
	async def on_force_unlink_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
		if isinstance(error, app_commands.CheckFailure):
			if interaction.response.is_done():
				await interaction.followup.send("❌ Solo moderadores pueden usar este comando.", ephemeral=True)
			else:
				await interaction.response.send_message("❌ Solo moderadores pueden usar este comando.", ephemeral=True)
