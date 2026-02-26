"""Comandos administrativos de impuestos (/tax) en Discord.

Solo moderadores pueden usar estos comandos.

/tax add <porcentaje> <intervalo_segundos> <usuario_opcional> <top_objetivo_opcional> <razon_opcional>
/tax remove <tax_id>
/tax list

Reglas:
- Se debe especificar UN objetivo: o usuario o Top (Top 1/2/3).
- Si se especifica usuario, no se admite objetivo Top.
- El porcentaje admite decimales.
- El intervalo es en segundos.
"""

from __future__ import annotations

from typing import Optional
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from backend.managers import get_or_create_discord_user
from backend.managers.user_lookup_manager import (
	find_user_by_global_id,
	get_user_platform_ids,
)
from backend.managers.economy_manager import get_global_leaderboard
from backend.services.activities.taxes import taxes_config
from backend.services.discord_bot.bot_logging import log_economy


def setup_taxes_admin_commands(bot: commands.Bot) -> None:
	"""Registra comandos administrativos de impuestos."""

	tax_group = _get_or_create_tax_group(bot)

	@tax_group.command(name="add", description="Añade un impuesto recurrente")
	@app_commands.describe(
		percent="Porcentaje de impuesto (ej: 5.5 para 5.5%)",
		interval_seconds="Intervalo de cobro en segundos",
		target_user="Usuario objetivo (opcional)",
		target_top="Objetivo Top (Top 1, Top 2 o Top 3)",
		reason="Razón o nota opcional",
	)
	@app_commands.choices(
		target_top=[
			app_commands.Choice(name="Top 1", value="top1"),
			app_commands.Choice(name="Top 2", value="top2"),
			app_commands.Choice(name="Top 3", value="top3"),
		]
	)
	async def tax_add(
		interaction: discord.Interaction,
		percent: float,
		interval_seconds: int,
		target_user: Optional[discord.Member] = None,
		target_top: Optional[app_commands.Choice[str]] = None,
		reason: Optional[str] = None,
	) -> None:
		if not _is_moderator(interaction):
			await _deny_permission(interaction)
			return

		if percent <= 0:
			await _send_error(interaction, "El porcentaje debe ser mayor que 0.")
			return

		if interval_seconds <= 0:
			await _send_error(interaction, "El intervalo debe ser mayor que 0 segundos.")
			return

		if target_user and target_top is not None:
			await _send_error(interaction, "Debes elegir un usuario O un objetivo Top, no ambos.")
			return

		if not target_user and target_top is None:
			await _send_error(interaction, "Debes especificar un usuario o un objetivo Top.")
			return

		# Determinar tipo de objetivo
		target_type = "user"
		target_user_id: int | None = None
		target_top_rank: int | None = None

		if target_user is not None:
			# Obtener/crear usuario global
			user, _, _ = get_or_create_discord_user(
				discord_id=str(target_user.id),
				discord_username=target_user.name,
				avatar_url=str(target_user.display_avatar.url),
			)
			target_user_id = int(user.user_id)
			target_type = "user"
		else:
			# Objetivo Top
			if target_top is None:
				await _send_error(interaction, "Debes especificar un objetivo Top válido.")
				return
			value = (target_top.value or "").lower()
			if value not in {"top1", "top2", "top3"}:
				await _send_error(interaction, "Objetivo Top inválido. Usa Top 1, Top 2 o Top 3.")
				return
			if value == "top1":
				target_top_rank = 1
			elif value == "top2":
				target_top_rank = 2
			else:
				target_top_rank = 3
			target_type = "top"

		clean_reason = (reason or "").strip() or None

		new_tax = taxes_config.add_tax(
			percent=percent,
			interval_seconds=interval_seconds,
			target_type=target_type,
			target_user_id=target_user_id,
			target_top_rank=target_top_rank,
			reason=clean_reason,
		)

		desc_lines = [
			f"ID: `{new_tax.id}`",
			f"Porcentaje: `{new_tax.percent:.2f}%`",
			f"Intervalo: `{new_tax.interval_seconds}s`",
		]
		if target_type == "user":
			user_label = f"`ID:{target_user_id}`"
			if target_user is not None:
				user_label = f"{target_user.mention} (`ID:{target_user_id}`)"
			desc_lines.append(f"Objetivo: {user_label}")
		else:
			desc_lines.append(f"Objetivo: Top {new_tax.target_top_rank} global")
		if clean_reason:
			desc_lines.append(f"Razón: {clean_reason}")

		embed = discord.Embed(
			title="Impuesto añadido",
			description="\n".join(desc_lines),
			color=discord.Color.green(),
		)
		await interaction.response.send_message(embed=embed, ephemeral=True)

		if interaction.guild is not None:
			await log_economy(
				bot,
				interaction.guild.id,
				"Impuesto creado",
				f"{interaction.user.mention} creó un impuesto `{new_tax.id}`.",
				fields={
					"Tax ID": new_tax.id,
					"Porcentaje": f"{new_tax.percent:.2f}%",
					"Intervalo": f"{new_tax.interval_seconds}s",
					"Tipo": target_type,
					"Objetivo": (
						f"user:{target_user_id}" if target_type == "user" else f"top:{new_tax.target_top_rank}"
					),
					"Razón": clean_reason or "-",
				},
				user=interaction.user,
			)

	@tax_group.command(name="remove", description="Elimina un impuesto por ID")
	@app_commands.describe(tax_id="ID del impuesto a eliminar (ej: T1)")
	async def tax_remove(
		interaction: discord.Interaction,
		tax_id: str,
	) -> None:
		if not _is_moderator(interaction):
			await _deny_permission(interaction)
			return

		ok = taxes_config.remove_tax(tax_id)
		if not ok:
			await _send_error(interaction, f"No se encontró ningún impuesto con ID `{tax_id}`.")
			return

		embed = discord.Embed(
			title="Impuesto eliminado",
			description=f"Se eliminó el impuesto `{tax_id}`.",
			color=discord.Color.green(),
		)
		await interaction.response.send_message(embed=embed, ephemeral=True)

		if interaction.guild is not None:
			await log_economy(
				bot,
				interaction.guild.id,
				"Impuesto eliminado",
				f"{interaction.user.mention} eliminó el impuesto `{tax_id}`.",
				fields={"Tax ID": tax_id},
				user=interaction.user,
			)

	@tax_group.command(name="list", description="Lista los impuestos configurados")
	async def tax_list(interaction: discord.Interaction) -> None:
		if not _is_moderator(interaction):
			await _deny_permission(interaction)
			return

		all_taxes = taxes_config.list_taxes()
		if not all_taxes:
			embed = discord.Embed(
				title="Impuestos",
				description="No hay impuestos configurados.",
				color=discord.Color.orange(),
			)
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		now_ts = datetime.now(timezone.utc).timestamp()
		embed = discord.Embed(
			title="Impuestos configurados",
			color=discord.Color.blurple(),
		)

		guild = interaction.guild
		for tax in all_taxes[:20]:
			# Título del campo: ID + resumen corto
			interval_human = _format_interval_short(tax.interval_seconds)
			field_name = f"{tax.id} — {tax.percent:.2f}% cada {interval_human}"

			# Resolver objetivo actual (ID universal + posible @usuario)
			if tax.target_type == "user" and tax.target_user_id is not None:
				objective = _describe_global_user(tax.target_user_id, guild)
				objective_prefix = "Usuario asignado"
			elif tax.target_type == "top" and tax.target_top_rank is not None:
				current_user_label = _describe_top_user(tax.target_top_rank, guild)
				objective_prefix = f"Top {tax.target_top_rank} global"
				objective = current_user_label
			else:
				objective_prefix = "Objetivo desconocido"
				objective = "-"

			# Próximo cobro (tiempo restante)
			remaining_label = _format_next_run(
				now_ts, tax.interval_seconds, tax.last_run, tax.percent
			)

			lines: list[str] = [
				f"**Selector:** {objective_prefix}",
				f"**Objetivo actual:** {objective}",
				f"**Próximo cobro:** {remaining_label}",
			]
			if tax.reason:
				lines.append(f"**Razón:** {tax.reason}")

			embed.add_field(
				name=field_name,
				value="\n".join(lines),
				inline=False,
			)

		await interaction.response.send_message(embed=embed, ephemeral=True)


def _get_or_create_tax_group(bot: commands.Bot) -> app_commands.Group:
	existing = bot.tree.get_command("tax")
	if isinstance(existing, app_commands.Group):
		return existing

	group = app_commands.Group(name="tax", description="Configuración de impuestos")
	bot.tree.add_command(group)
	return group


def _is_moderator(interaction: discord.Interaction) -> bool:
	perms = interaction.user.guild_permissions
	return perms.administrator or perms.manage_guild


async def _deny_permission(interaction: discord.Interaction) -> None:
	embed = discord.Embed(
		title="Acceso denegado",
		description="Solo moderadores pueden usar este comando.",
		color=discord.Color.red(),
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)


async def _send_error(interaction: discord.Interaction, message: str) -> None:
	embed = discord.Embed(
		title="Error",
		description=message,
		color=discord.Color.red(),
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)


def _format_interval_short(seconds: int) -> str:
	"""Convierte segundos en un texto corto (ej: 1h 20m, 45s)."""
	try:
		seconds_int = int(seconds)
	except Exception:
		seconds_int = 0
	if seconds_int <= 0:
		return "0s"
	mins, secs = divmod(seconds_int, 60)
	if mins == 0:
		return f"{secs}s"
	hours, mins = divmod(mins, 60)
	parts: list[str] = []
	if hours:
		parts.append(f"{hours}h")
	if mins:
		parts.append(f"{mins}m")
	if not parts:
		parts.append(f"{secs}s")
	return " ".join(parts)


def _format_next_run(now_ts: float, interval_seconds: int, last_run: float, percent: float) -> str:
	"""Texto legible de cuánto falta para el próximo cobro."""
	if interval_seconds <= 0 or percent <= 0:
		return "No se cobrará (intervalo/porcentaje inválido)"

	if last_run <= 0:
		# Nunca se ha cobrado, está listo para ejecutarse cuando el scheduler quiera
		return "Listo para cobrarse (nunca se ha cobrado)"

	elapsed = max(0.0, float(now_ts) - float(last_run))
	remaining = int(interval_seconds - elapsed)
	if remaining <= 0:
		return "Listo para cobrarse"
	return f"En {_format_interval_short(remaining)}"


def _describe_global_user(global_user_id: int | str, guild: discord.Guild | None) -> str:
	"""Devuelve una etiqueta tipo 'ID:1234 @user (Nombre)' para un usuario global."""
	try:
		uid = int(global_user_id)
	except Exception:
		return f"ID:? (usuario desconocido)"

	# ID en formato de código para que se vea más estético en Discord
	label_parts: list[str] = [f"`ID:{uid}`"]

	lookup = None
	try:
		lookup = find_user_by_global_id(uid)
	except Exception:
		lookup = None
	if lookup is not None and getattr(lookup, "display_name", None):
		label_parts.append(str(lookup.display_name))

	# Intentar obtener Discord ID para mostrar @mención
	discord_id: str | None = None
	try:
		platform_ids = get_user_platform_ids(uid)
		discord_id = platform_ids.get("discord")
	except Exception:
		discord_id = None

	if discord_id:
		label_parts.append(f"<@{discord_id}>")

	return " ".join(label_parts)


def _describe_top_user(rank: int, guild: discord.Guild | None) -> str:
	"""Devuelve etiqueta para el usuario actual en el Top N global."""
	try:
		limit = max(1, int(rank))
	except Exception:
		return "(Top sin datos)"

	try:
		rows = get_global_leaderboard(limit=limit)
		if not rows or len(rows) < limit:
			return "(Top sin usuario activo)"
		row = rows[limit - 1]
		uid = int(row.get("user_id"))
		user_label = _describe_global_user(uid, guild)
		return user_label
	except Exception:
		return "(Error obteniendo usuario Top)"

