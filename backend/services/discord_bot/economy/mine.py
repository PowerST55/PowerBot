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
from backend.services.discord_bot.config import get_channels_config
from backend.services.discord_bot.config.economy import get_economy_config
from backend.services.discord_bot.config.mine_config import get_mine_config
from backend.services.discord_bot.economy.economy_channel import register_mine_depleted


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
					data.setdefault("mine_depleted_announced", False)
					return data
		except Exception:
			pass
	return {"cooldowns": {}, "mine_depleted_announced": False}


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


def _to_discord_timestamp(unix_timestamp: int, style: str = "R") -> str:
	return f"<t:{int(unix_timestamp)}:{style}>"


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


def _calculate_mine_ip_amount(user_balance: float, ip_percent: float) -> float:
	return round(max(0.0, float(user_balance)) * (max(0.0, float(ip_percent)) / 100.0), 2)


def _get_mine_fund_balance() -> float:
	return float(economy_manager.get_mine_fund_balance())


def _mine_has_operable_items(items: list[dict[str, Any]], mine_fund_balance: float) -> bool:
	if mine_fund_balance <= 0:
		return False
	for item in items:
		probability_value = float(item.get("probability", 0) or 0)
		price_value = float(item.get("price", 0) or 0)
		if probability_value <= 0:
			continue
		if price_value > 0 and price_value > mine_fund_balance:
			continue
		return True
	return False


def _set_mine_depleted_announced(guild_id: int, value: bool) -> None:
	state = _load_state(guild_id)
	state["mine_depleted_announced"] = bool(value)
	_save_state(guild_id, state)


def _clear_mine_depleted_announcement(guild_id: int) -> None:
	state = _load_state(guild_id)
	if state.get("mine_depleted_announced"):
		state["mine_depleted_announced"] = False
		_save_state(guild_id, state)


def _sync_mine_depleted_state(guild_id: int, items: list[dict[str, Any]] | None = None, mine_fund_balance: float | None = None) -> bool:
	if items is None:
		items = get_mine_config(guild_id).list_items()
	if mine_fund_balance is None:
		mine_fund_balance = _get_mine_fund_balance()
	can_operate = _mine_has_operable_items(items, mine_fund_balance)
	if can_operate:
		_clear_mine_depleted_announcement(guild_id)
	return can_operate


async def _announce_mine_depleted_if_needed(guild: discord.Guild) -> None:
	state = _load_state(guild.id)
	if state.get("mine_depleted_announced"):
		return

	channels_config = get_channels_config(guild.id)
	economy_channel_id = channels_config.get_channel("economy_channel")
	if not economy_channel_id:
		return

	channel = guild.get_channel(int(economy_channel_id))
	if not isinstance(channel, discord.TextChannel):
		return

	embed = discord.Embed(
		title="⛏️ Mina Agotada",
		description="La mina se ha quedado sin minerales. Esperando explosivos para ampliar la excavación y reanudar las extracciones.",
		color=0xC0392B,
	)
	embed.add_field(
		name="Estado",
		value="Las excavaciones quedan detenidas hasta que vuelva a haber material explotable.",
		inline=False,
	)
	embed.set_footer(text="Economía central • Estado de la mina")
	register_mine_depleted(guild_id=guild.id, source="depleted")
	await channel.send(embed=embed)
	_set_mine_depleted_announced(guild.id, True)


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

		mine_fund_balance = _get_mine_fund_balance()
		mine_is_operable = _sync_mine_depleted_state(interaction.guild.id, items, mine_fund_balance)
		if not mine_is_operable:
			await _announce_mine_depleted_if_needed(interaction.guild)
			await interaction.response.send_message(
				"⛔ La mina se ha quedado sin minerales.",
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
			cooldown_end_ts = last_ts + rate_seconds
			cooldown_embed = discord.Embed(
				title="⏳ Mina en cooldown",
				description=(
					f"⏳ Debes esperar {_to_discord_timestamp(cooldown_end_ts, 'R')} "
					"para volver a minar."
				),
				color=discord.Color.orange(),
			)
			cooldown_embed.add_field(
				name="Disponible de nuevo",
				value=_to_discord_timestamp(cooldown_end_ts, "R"),
				inline=False,
			)
			cooldown_embed.add_field(
				name="Hora exacta",
				value=_to_discord_timestamp(cooldown_end_ts, "F"),
				inline=False,
			)
			cooldown_embed.set_footer(text=f"Cooldown total: {_format_seconds(rate_seconds)}")
			await interaction.response.send_message(embed=cooldown_embed, ephemeral=True)
			return

		valid_items = []
		for item in items:
			probability_value = float(item.get("probability", 0) or 0)
			price_value = float(item.get("price", 0) or 0)
			if probability_value <= 0:
				continue
			if price_value > 0 and price_value > mine_fund_balance:
				continue
			valid_items.append(item)
		if not valid_items:
			await _announce_mine_depleted_if_needed(interaction.guild)
			await interaction.response.send_message(
				"⛔ La mina se ha quedado sin minerales.",
				ephemeral=True,
			)
			return

		weights = [float(item.get("probability", 0)) for item in valid_items]
		selected = random.choices(valid_items, weights=weights, k=1)[0]

		item_name = str(selected.get("name") or "objeto")
		reward = float(selected.get("price") or 0)
		probability = float(selected.get("probability") or 0)
		item_ip_percent = float(selected.get("ip_percent", selected.get("ip%", 0.0)) or 0.0)

		user, _, _ = get_or_create_discord_user(
			discord_id=str(interaction.user.id),
			discord_username=interaction.user.name,
			avatar_url=str(interaction.user.display_avatar.url),
		)
		previous_balance = float(economy_manager.get_total_balance(user.user_id))
		ip_amount = _calculate_mine_ip_amount(previous_balance, item_ip_percent) if reward < 0 else 0.0
		base_loss = abs(reward) if reward < 0 else 0.0
		total_delta = reward if reward >= 0 else -min(previous_balance, round(base_loss + ip_amount, 2))
		actual_loss = abs(total_delta) if total_delta < 0 else 0.0

		new_balance = float(
			economy_manager.apply_balance_delta(
				user_id=user.user_id,
				delta=total_delta,
				reason="mine_reward",
				platform="discord",
				guild_id=str(interaction.guild.id),
				channel_id=str(interaction.channel_id),
				source_id=f"mine:{interaction.id}",
				system_account=economy_manager.MINE_FUND_ACCOUNT,
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
		is_bad_item = total_delta < 0
		notify_embed = discord.Embed(
			title="⛏️ Registro de mina",
			description=(
				(
					f"{user_display} ha conseguido **{item_name}** "
					f"por **{_format_currency(reward, currency_symbol)}**"
					if not is_bad_item
					else f"{user_display} activó **{item_name}** y perdió **{_format_currency(actual_loss, currency_symbol)}**"
				)
			),
			color=discord.Color.red() if is_bad_item else _get_rarity_color(probability),
		)
		notify_embed.add_field(name="🎲 Probabilidad", value=f"`{_format_probability(probability)}`", inline=True)
		if is_bad_item:
			notify_embed.add_field(
				name="💥 Pérdida",
				value=f"`{_format_currency(base_loss, currency_symbol)} - {_format_value(item_ip_percent)} ip%`",
				inline=True,
			)
		else:
			notify_embed.add_field(name="💎 Recompensa", value=f"`{_format_currency(reward, currency_symbol)}`", inline=True)
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
		if not _sync_mine_depleted_state(interaction.guild.id):
			await _announce_mine_depleted_if_needed(interaction.guild)
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
	mine_fund_balance = _get_mine_fund_balance()
	mine_is_open = _sync_mine_depleted_state(guild_id, items, mine_fund_balance)

	embed = discord.Embed(
		title="💎 Powerbot Mina",
		description=(
			"Pulsa el botón para minar un objeto aleatorio según su probabilidad."
			if mine_is_open
			else "La mina se ha quedado sin minerales."
		),
		color=discord.Color.blurple() if mine_is_open else discord.Color.red(),
	)
	# Cooldown destacado
	embed.add_field(name="⏱️ Tiempo de espera", value=f"`{_format_seconds(rate_seconds)}` por usuario", inline=True)

	if items:
		# Obtener símbolo de moneda
		from backend.services.discord_bot.config.economy import get_economy_config
		economy_cfg = get_economy_config(guild_id)
		currency_symbol = economy_cfg.get_currency_symbol()
		mineral_rows = []
		danger_rows = []
		for item in items[:8]:
			name = str(item.get("name") or "objeto")
			price = float(item.get("price") or 0)
			prob = float(item.get("probability") or 0)
			if price < 0:
				ip_percent = float(item.get("ip_percent", item.get("ip%", 0.0)) or 0.0)
				label = f"-{_format_currency(abs(price), currency_symbol)}"
				if ip_percent > 0:
					label = f"{label} + ip {_format_value(ip_percent)}%"
				danger_rows.append(f"• {name} — `{label}` | `{_format_probability(prob)}`")
			else:
				label = _format_currency(price, currency_symbol)
				mineral_rows.append(f"• {name} — `{label}` | `{_format_probability(prob)}`")

		embed.add_field(
			name="🪨 Tabla de minerales",
			value="\n".join(mineral_rows) if mineral_rows else "Sin minerales configurados.",
			inline=True,
		)
		embed.add_field(
			name="🧨 Tabla de peligros",
			value="\n".join(danger_rows) if danger_rows else "Sin peligros configurados.",
			inline=True,
		)

	# Pie: cantidad de minerales disponibles
	embed.set_footer(text=f"{len(items)} minerales disponibles")
	return embed
