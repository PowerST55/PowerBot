"""
Lógica de mina (panel + botón de minado).
"""

from __future__ import annotations

import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import discord

from backend.managers import economy_manager, get_or_create_discord_user
from backend.services.discord_bot.config.economy import get_economy_config
from backend.services.discord_bot.config.mine_config import get_mine_config


def _state_file(guild_id: int) -> Path:
	data_dir = Path(__file__).resolve().parents[3] / "data" / "discord_bot"
	return data_dir / f"guild_{guild_id}_mine_state.json"


def _load_state(guild_id: int) -> dict[str, Any]:
	file_path = _state_file(guild_id)
	if file_path.exists():
		try:
			with open(file_path, "r", encoding="utf-8") as file:
				data = json.load(file)
				if isinstance(data, dict):
					data.setdefault("cooldowns", {})
					return data
		except Exception:
			pass
	return {"cooldowns": {}}


def _save_state(guild_id: int, state: dict[str, Any]) -> None:
	file_path = _state_file(guild_id)
	file_path.parent.mkdir(parents=True, exist_ok=True)
	with open(file_path, "w", encoding="utf-8") as file:
		json.dump(state, file, indent=2, ensure_ascii=False)


def _format_seconds(seconds: int) -> str:
	if seconds < 60:
		return f"{seconds}s"
	minutes = seconds // 60
	remain = seconds % 60
	if remain == 0:
		return f"{minutes}m"
	return f"{minutes}m {remain}s"


def _format_timestamp(prefix: str) -> str:
	now = datetime.now().strftime("%d/%m/%Y %H:%M")
	return f"{prefix} • {now}"


def _format_value(value: float, max_decimals: int = 2) -> str:
	formatted = f"{value:,.{max_decimals}f}"
	if "." in formatted:
		formatted = formatted.rstrip("0").rstrip(".")
	return formatted


def _format_currency(value: float, currency_symbol: str) -> str:
	amount = _format_value(value, max_decimals=2)
	return f"{amount} {currency_symbol}".strip()


def _format_probability(value: float) -> str:
	return f"{_format_value(value, max_decimals=2)}%"


def _get_rarity_color(probability: float) -> discord.Color:
	"""
	Reglas solicitadas por el usuario:
	>5% morado, >10% azul, >30% dorado, >50% verde, >100% gris.
	Se evalúa de mayor a menor para evitar solapamiento.
	"""
	if probability > 100:
		return discord.Color.light_grey()
	if probability > 50:
		return discord.Color.green()
	if probability > 30:
		return discord.Color.gold()
	if probability > 10:
		return discord.Color.blue()
	if probability > 5:
		return discord.Color.purple()
	return discord.Color.dark_grey()



def _panel_state_file(guild_id: int) -> Path:
	data_dir = Path(__file__).resolve().parents[3] / "data" / "discord_bot"
	return data_dir / f"guild_{guild_id}_mine_panel.json"


def _save_panel_location(guild_id: int, channel_id: int, message_id: int) -> None:
	file_path = _panel_state_file(guild_id)
	file_path.parent.mkdir(parents=True, exist_ok=True)
	data = {
		"channel_id": int(channel_id),
		"message_id": int(message_id),
		"saved_at": int(time.time()),
	}
	with open(file_path, "w", encoding="utf-8") as file:
		json.dump(data, file, indent=2, ensure_ascii=False)
	print(f"[MINE] Panel registrado guild={guild_id} channel={channel_id} message={message_id}")


def _load_panel_location(guild_id: int) -> tuple[int | None, int | None]:
	file_path = _panel_state_file(guild_id)
	if not file_path.exists():
		print(f"[MINE] No hay panel guardado para guild={guild_id}")
		return None, None
	try:
		with open(file_path, "r", encoding="utf-8") as file:
			data = json.load(file)
			channel_id = int(data.get("channel_id")) if data.get("channel_id") else None
			message_id = int(data.get("message_id")) if data.get("message_id") else None
			print(f"[MINE] Panel cargado guild={guild_id} channel={channel_id} message={message_id}")
			return channel_id, message_id
	except Exception as exc:
		print(f"[MINE] Error leyendo panel guardado guild={guild_id}: {exc}")
		return None, None


class MineView(discord.ui.View):
	def __init__(self):
		super().__init__(timeout=None)

	@discord.ui.button(label="⛏️ Minar", style=discord.ButtonStyle.primary, custom_id="powerbot:mine:button")
	async def mine_button(self, interaction: discord.Interaction, button: discord.ui.Button):
		if interaction.guild is None:
			await interaction.response.send_message("Este botón solo funciona en servidor.", ephemeral=True)
			return

		mine_config = get_mine_config(interaction.guild.id)
		configured_channel = mine_config.get_mine_channel_id()
		if configured_channel and interaction.channel_id != configured_channel:
			await interaction.response.send_message(
				f"La mina solo puede usarse en <#{configured_channel}>.",
				ephemeral=True,
			)
			return

		items = mine_config.list_items()
		if not items:
			await interaction.response.send_message(
				"No hay ítems configurados para la mina. Un admin debe usar `/mine add`.",
				ephemeral=True,
			)
			return

		rate_seconds = mine_config.get_rate_seconds()
		now_ts = int(time.time())
		state = _load_state(interaction.guild.id)
		cooldowns: dict[str, Any] = state.setdefault("cooldowns", {})
		user_key = str(interaction.user.id)
		last_ts = int(cooldowns.get(user_key, 0) or 0)

		elapsed = now_ts - last_ts
		if last_ts > 0 and elapsed < rate_seconds:
			remaining = rate_seconds - elapsed
			await interaction.response.send_message(
				f"⏳ Debes esperar `{_format_seconds(remaining)}` para volver a minar.",
				ephemeral=True,
			)
			return

		valid_items = [
			item
			for item in items
			if float(item.get("probability", 0)) > 0
		]
		if not valid_items:
			await interaction.response.send_message(
				"Los ítems de mina tienen probabilidades inválidas (deben ser > 0).",
				ephemeral=True,
			)
			return

		weights = [float(item.get("probability", 0)) for item in valid_items]
		selected = random.choices(valid_items, weights=weights, k=1)[0]

		item_name = str(selected.get("name") or "objeto")
		reward = float(selected.get("price") or 0)
		probability = float(selected.get("probability") or 0)

		user, _, _ = get_or_create_discord_user(
			discord_id=str(interaction.user.id),
			discord_username=interaction.user.name,
			avatar_url=str(interaction.user.display_avatar.url),
		)

		new_balance = float(
			economy_manager.apply_balance_delta(
				user_id=user.user_id,
				delta=reward,
				reason="mine_reward",
				platform="discord",
				guild_id=str(interaction.guild.id),
				channel_id=str(interaction.channel_id),
				source_id=f"mine:{interaction.id}",
			)
		)

		cooldowns[user_key] = now_ts
		_save_state(interaction.guild.id, state)

		economy_cfg = get_economy_config(interaction.guild.id)
		currency_symbol = economy_cfg.get_currency_symbol()
		currency_name = economy_cfg.get_currency_name()

		await interaction.response.defer()

		# 1) Borrar panel anterior para que no queden paneles viejos arriba
		try:
			if interaction.message is not None:
				await interaction.message.delete()
		except Exception:
			pass

		# 2) Publicar notificación del minado (mensaje de registro)
		# Mostrar primero la ID universal y luego el @usuario
		universal_id = getattr(user, 'user_id', None)
		if universal_id is not None:
			user_display = f"`ID:{universal_id}` {interaction.user.mention}"
		else:
			user_display = f"{interaction.user.mention}"
		notify_embed = discord.Embed(
			title="⛏️ Registro de mina",
			description=(
				f"{user_display} ha conseguido **{item_name}** "
				f"por **{_format_currency(reward, currency_symbol)}**"
			),
			color=_get_rarity_color(probability),
		)
		notify_embed.add_field(name="🎲 Probabilidad", value=f"`{_format_probability(probability)}`", inline=True)
		notify_embed.add_field(
			name="💰 Balance actual",
			value=f"`{_format_currency(new_balance, currency_symbol)}`",
			inline=False,
		)
		notify_embed.set_footer(text=_format_timestamp("Mina"))

		if interaction.channel is None:
			await interaction.followup.send("No se pudo publicar el resultado en el canal.", ephemeral=True)
			return

		await interaction.channel.send(embed=notify_embed)

		# 3) Volver a publicar panel para que quede siempre al final
		panel_embed = _build_mine_panel_embed(interaction.guild.id)
		panel_msg = await interaction.channel.send(embed=panel_embed, view=MineView())
		_save_panel_location(interaction.guild.id, interaction.channel.id, panel_msg.id)
		print(f"[MINE] Panel regenerado con botón persistente guild={interaction.guild.id} channel={interaction.channel.id}")

	@staticmethod
	async def register_persistent(bot: discord.Client):
		"""
		Registra la view persistente para el botón de mina tras reinicio del bot.
		Debe llamarse una vez en on_ready.
		Reancla el botón al último panel registrado por cada servidor.
		"""
		for guild in bot.guilds:
			channel_id, message_id = _load_panel_location(guild.id)
			if not channel_id or not message_id:
				continue
			channel = bot.get_channel(channel_id)
			if channel is None:
				try:
					channel = await bot.fetch_channel(channel_id)
				except Exception as exc:
					print(f"[MINE] No pude obtener canal {channel_id} para guild={guild.id}: {exc}")
					continue
			try:
				message = await channel.fetch_message(message_id)
				await message.edit(view=MineView())
				print(f"[MINE] Botón reanclado guild={guild.id} channel={channel_id} message={message_id}")
			except Exception as exc:
				print(f"[MINE] No pude reanclar botón guild={guild.id} message={message_id}: {exc}")
		# Registrar la view global para que nuevas publicaciones del panel sigan usando el mismo botón
		bot.add_view(MineView())


async def send_mine_panel(interaction: discord.Interaction) -> None:
	"""Envía el panel de mina con botón de minado."""
	if interaction.guild is None:
		await interaction.response.send_message("Este comando solo funciona en servidor.", ephemeral=True)
		return

	mine_config = get_mine_config(interaction.guild.id)
	configured_channel = mine_config.get_mine_channel_id()
	if configured_channel and interaction.channel_id != configured_channel:
		await interaction.response.send_message(
			f"El panel de mina solo puede publicarse en <#{configured_channel}>.",
			ephemeral=True,
		)
		return

	embed = _build_mine_panel_embed(interaction.guild.id)
	await interaction.response.send_message(embed=embed, view=MineView())
	try:
		response_msg = await interaction.original_response()
		_save_panel_location(interaction.guild.id, response_msg.channel.id, response_msg.id)
		print(f"[MINE] Panel enviado manualmente y registrado guild={interaction.guild.id} channel={response_msg.channel.id}")
	except Exception:
		pass


def _build_mine_panel_embed(guild_id: int) -> discord.Embed:
	mine_config = get_mine_config(guild_id)
	items = mine_config.list_items()
	rate_seconds = mine_config.get_rate_seconds()
	configured_channel = mine_config.get_mine_channel_id()

	embed = discord.Embed(
		title="💎 Powerbot Mina",
		description="Pulsa el botón para minar un objeto aleatorio según su probabilidad.",
		color=discord.Color.blurple(),
	)
	# Cooldown destacado
	embed.add_field(name="⏱️ Tiempo de espera", value=f"`{_format_seconds(rate_seconds)}` por usuario", inline=True)

	if items:
		# Obtener símbolo de moneda
		from backend.services.discord_bot.config.economy import get_economy_config
		economy_cfg = get_economy_config(guild_id)
		currency_symbol = economy_cfg.get_currency_symbol()
		preview_rows = []
		for item in items[:8]:
			name = str(item.get("name") or "objeto")
			price = float(item.get("price") or 0)
			prob = float(item.get("probability") or 0)
			preview_rows.append(
				f"• {name} — `{_format_currency(price, currency_symbol)}` | "
				f"`{_format_probability(prob)}`"
			)
		embed.add_field(name="🪨 Tabla de minerales", value="\n".join(preview_rows), inline=False)

	# Pie: cantidad de minerales disponibles
	embed.set_footer(text=f"{len(items)} minerales disponibles")
	return embed
