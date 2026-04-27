"""Comando /avi para el minijuego Aviator en Discord."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from backend.managers import get_or_create_discord_user
from backend.managers import economy_manager
from backend.services.activities import aviator, casino_master, cooldown_manager, games_config
from backend.services.discord_bot.config.economy import get_economy_config
from backend.services.discord_bot.economy.economy_channel import (
	get_casino_bankruptcy_state,
	register_casino_bankruptcy,
)


ACTIVE_AVIATOR_SESSIONS: dict[int, "AviatorView"] = {}


class AviatorView(discord.ui.View):
	def __init__(
		self,
		*,
		player: discord.abc.User,
		user_id: int,
		bet_amount: float,
		reach_multiplier: float,
		currency_symbol: str,
		currency_name: str,
		guild_id: int | None,
		channel_id: int | None,
		source_id: int,
		cooldown_key: str = "aviator",
		timeout: float = 90,
	):
		super().__init__(timeout=timeout)
		self.player = player
		self.user_id = user_id
		self.bet_amount = round(float(bet_amount), 2)
		self.reach_multiplier = round(float(reach_multiplier), 1)
		self.currency_symbol = currency_symbol
		self.currency_name = currency_name
		self.guild_id = str(guild_id) if guild_id else None
		self.channel_id = str(channel_id) if channel_id else None
		self.source_id = source_id
		self.round_number = 1
		self.cooldown_key = cooldown_key
		self.current_multiplier = 1.0
		self.state = "flying"
		self.delta = 0.0
		self.final_balance: float | None = None
		self.bankruptcy_triggered = False
		self.casino_balance_after: float | None = None
		self.casino_balance_before: float | None = None
		self.settlement_error: str | None = None
		self.note = ""
		self.message: Optional[discord.Message] = None
		self.processing = False
		self.resolved = False
		self._sync_buttons()

	def _sync_buttons(self) -> None:
		if self.resolved and self.state in {"crashed", "timeout"} and not self.settlement_error:
			self._set_buttons([self.replay_button])
			return

		if self.resolved:
			self._set_buttons([])
			return

		if self.current_multiplier <= 1.0:
			self.advance_button.label = "Comenzar"
			self.advance_button.style = discord.ButtonStyle.success
		else:
			self.advance_button.label = "►"
			self.advance_button.style = discord.ButtonStyle.primary

		self.cashout_button.style = discord.ButtonStyle.secondary
		self.advance_button.disabled = not aviator.can_advance(self.current_multiplier)

		if self.current_multiplier > 1.0:
			self.cashout_button.disabled = False
			self._set_buttons([self.cashout_button, self.advance_button])
		else:
			self._set_buttons([self.advance_button])

	def _set_buttons(self, buttons: list[discord.ui.Button]) -> None:
		for button in (self.cashout_button, self.advance_button, self.replay_button):
			if button in self.children:
				self.remove_item(button)
		for button in buttons:
			self.add_item(button)

	def _show_button(self, button: discord.ui.Button) -> None:
		if button not in self.children:
			self.add_item(button)

	def _hide_button(self, button: discord.ui.Button) -> None:
		if button in self.children:
			self.remove_item(button)

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		if interaction.user.id != self.player.id:
			await interaction.response.send_message("❌ Esta partida no es tuya.", ephemeral=True)
			return False
		return True

	def build_embed(self) -> discord.Embed:
		summary = aviator.get_aviator_summary(
			username=self.player.name,
			bet_amount=self.bet_amount,
			current_multiplier=self.current_multiplier,
			reach_multiplier=self.reach_multiplier,
			state="crashed" if self.state == "timeout" else self.state,
			delta=self.delta,
			final_balance=self.final_balance,
		)

		color_map = {
			"verde": discord.Color.green(),
			"rojo": discord.Color.red(),
			"azul": discord.Color.blurple(),
		}
		embed = discord.Embed(
			title="Aviator",
			description=(
				f"{_build_scene_line(self.current_multiplier, self.state)}\n"
				f"{_build_payout_line(self.bet_amount, self.current_multiplier, self.currency_symbol, self.state, summary['delta_text'])}"
			),
			color=color_map.get(str(summary["color"]), discord.Color.blurple()),
		)

		if self.resolved:
			embed.add_field(name="Vuelo real", value=f"x{self.reach_multiplier:.1f}", inline=True)
			if self.final_balance is not None:
				embed.add_field(name="Saldo final", value=f"{self.final_balance:,.2f}{self.currency_symbol}", inline=True)
			if self.bankruptcy_triggered:
				embed.add_field(
					name="🚨 Evento crítico",
					value="Esta jugada dejó al casino en bancarrota. Las mesas quedan cerradas hasta recargar el fondo.",
					inline=False,
				)

		if self.settlement_error:
			embed.add_field(name="Error", value=self.settlement_error, inline=False)

		embed.set_footer(text=f"Jugador: {self.player.name}  •  Tu apuesta: {self.bet_amount:,.2f}{self.currency_symbol}")
		embed.timestamp = datetime.now(timezone.utc)
		return embed

	async def _finalize(self, state: str, interaction: discord.Interaction | None = None) -> None:
		if self.resolved:
			return

		self.resolved = True
		self.state = state
		if state == "cashed":
			self.delta = aviator.calculate_cashout_delta(self.bet_amount, self.current_multiplier)
		elif state in {"crashed", "timeout"}:
			self.delta = -self.bet_amount

		settlement = economy_manager.settle_casino_bet(
			user_id=self.user_id,
			delta=self.delta,
			reason="aviator",
			platform="discord",
			guild_id=self.guild_id,
			channel_id=self.channel_id,
			source_id=f"aviator:{self.source_id}:{self.round_number}:{state}",
			allow_negative_casino_fund=True,
		)

		if settlement.get("success"):
			self.final_balance = float(settlement["user_balance"])
			self.casino_balance_after = float(settlement["casino_balance_after"])
			self.casino_balance_before = float(settlement["casino_balance_before"])
			self.bankruptcy_triggered = bool(settlement.get("bankruptcy_triggered"))
			cooldown_manager.update_cooldown(str(self.player.id), self.cooldown_key)

			if self.bankruptcy_triggered and interaction is not None:
				register_casino_bankruptcy(
					cause_display=interaction.user.mention,
					cause_platform="discord",
					cause_user_id=str(interaction.user.id),
					game_name="aviator",
					previous_balance=float(settlement["casino_balance_before"]),
					new_balance=float(settlement["casino_balance_after"]),
					bet_amount=float(self.bet_amount),
					net_result=float(self.delta),
				)
		else:
			self.settlement_error = str(settlement.get("error", "No se pudo liquidar la jugada."))
			self.note = "La partida terminó, pero hubo un problema al registrar el resultado."

		ACTIVE_AVIATOR_SESSIONS.pop(self.player.id, None)
		self._sync_buttons()

	def _reset_for_replay(self, reach_multiplier: float) -> None:
		self.round_number += 1
		self.reach_multiplier = round(float(reach_multiplier), 1)
		self.current_multiplier = 1.0
		self.state = "flying"
		self.delta = 0.0
		self.final_balance = None
		self.bankruptcy_triggered = False
		self.casino_balance_after = None
		self.casino_balance_before = None
		self.settlement_error = None
		self.note = ""
		self.resolved = False
		ACTIVE_AVIATOR_SESSIONS[self.player.id] = self
		self._sync_buttons()

	async def _refresh_message(self, interaction: discord.Interaction | None = None) -> None:
		embed = self.build_embed()
		if interaction is not None:
			if interaction.response.is_done():
				await interaction.edit_original_response(embed=embed, view=self)
			else:
				await interaction.response.edit_message(embed=embed, view=self)
			return

		if self.message is not None:
			await self.message.edit(embed=embed, view=self)

	async def on_timeout(self) -> None:
		if self.resolved:
			return
		self.note = "No retiraste a tiempo."
		await self._finalize("timeout")
		await self._refresh_message()

	@discord.ui.button(label="Retirarse", style=discord.ButtonStyle.secondary, row=0)
	async def cashout_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		if self.processing or self.resolved:
			await interaction.response.send_message("⏳ La jugada se está procesando.", ephemeral=True)
			return

		if self.current_multiplier <= 1.0:
			await interaction.response.send_message("❌ No puedes retirarte en x1.0.", ephemeral=True)
			return

		self.processing = True
		try:
			self.note = "Cobro ejecutado a tiempo."
			await self._finalize("cashed", interaction)
			await self._refresh_message(interaction)
		finally:
			self.processing = False

	@discord.ui.button(label="►", style=discord.ButtonStyle.primary, row=0)
	async def advance_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		if self.processing or self.resolved:
			await interaction.response.send_message("⏳ La jugada se está procesando.", ephemeral=True)
			return

		self.processing = True
		try:
			next_multiplier = aviator.get_next_multiplier(self.current_multiplier)
			if aviator.will_crash_on_advance(next_multiplier, self.reach_multiplier):
				self.note = "El avión desapareció antes de que pudieras asegurar la retirada."
				await self._finalize("crashed", interaction)
				await self._refresh_message(interaction)
				return

			self.current_multiplier = next_multiplier
			self.note = ""
			self._sync_buttons()
			await self._refresh_message(interaction)
		finally:
			self.processing = False

	@discord.ui.button(label="Volver a jugar", style=discord.ButtonStyle.secondary, row=0)
	async def replay_button(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		if self.processing:
			await interaction.response.send_message("⏳ La jugada se está procesando.", ephemeral=True)
			return

		self.processing = True
		try:
			current_balance = _get_current_balance(self.user_id)
			insufficient = _ensure_sufficient_balance(
				current_balance,
				self.bet_amount,
				self.currency_name,
				self.currency_symbol,
			)
			if insufficient:
				await interaction.response.send_message(insufficient, ephemeral=True)
				return

			casino_fund_balance = economy_manager.get_casino_fund_balance()
			if casino_fund_balance <= 0:
				await interaction.response.send_message(
					"❌ El fondo del casino está agotado. No se puede reiniciar el vuelo.",
					ephemeral=True,
				)
				return

			reach_multiplier = aviator.generate_reach_multiplier(self.bet_amount, casino_fund_balance)
			self._reset_for_replay(reach_multiplier)
			await self._refresh_message(interaction)
		finally:
			self.processing = False


def setup_aviator_commands(bot: commands.Bot) -> None:
	@bot.tree.command(name="avi", description="Vuela en Aviator y retírate antes de que desaparezca")
	@app_commands.guild_only()
	@app_commands.describe(cantidad="Cantidad a apostar, 'all' o vacío para auto-mínimo")
	async def avi(interaction: discord.Interaction, cantidad: Optional[str] = None):
		if interaction.guild is None:
			await interaction.response.send_message("❌ Este comando solo funciona dentro de un servidor.", ephemeral=True)
			return

		economy_config = get_economy_config(interaction.guild.id)
		currency_name = economy_config.get_currency_name()
		currency_symbol = economy_config.get_currency_symbol()

		if interaction.user.id in ACTIVE_AVIATOR_SESSIONS:
			await interaction.response.send_message(
				"❌ Ya tienes un vuelo activo. Termínalo antes de iniciar otro.",
				ephemeral=True,
			)
			return

		user, _, _ = get_or_create_discord_user(
			discord_id=str(interaction.user.id),
			discord_username=interaction.user.name,
			avatar_url=str(interaction.user.display_avatar.url),
		)

		config = games_config.get_aviator_config()
		min_limit = float(config.get("min_limit", 0.0) or 0.0)
		max_limit = float(config.get("max_limit", 0.0) or 0.0)
		cooldown_seconds = int(config.get("cooldown", 0) or 0)

		can_play, remaining = cooldown_manager.check_cooldown(str(interaction.user.id), "aviator", cooldown_seconds)
		if not can_play:
			await _send_cooldown_error(interaction, remaining)
			return

		current_balance = _get_current_balance(user.user_id)

		if cantidad is None:
			bet_amount = _resolve_default_bet_amount(min_limit)
		else:
			bet_amount, error = _parse_bet_amount(cantidad, current_balance)
			if error:
				await interaction.response.send_message(error, ephemeral=True)
				return

		if min_limit > 0 and bet_amount < min_limit:
			await _send_min_limit_error(interaction, bet_amount, min_limit, currency_symbol)
			return

		if max_limit > 0 and bet_amount > max_limit:
			await _send_limit_error(interaction, bet_amount, max_limit, currency_symbol)
			return

		insufficient = _ensure_sufficient_balance(current_balance, bet_amount, currency_name, currency_symbol)
		if insufficient:
			await _send_balance_error(interaction, insufficient)
			return

		is_valid, message = aviator.validate_aviator(current_balance, bet_amount)
		if not is_valid:
			await interaction.response.send_message(message, ephemeral=True)
			return

		casino_fund_balance = economy_manager.get_casino_fund_balance()
		if casino_fund_balance <= 0:
			await _send_casino_bankruptcy_error(interaction)
			return

		reach_multiplier = aviator.generate_reach_multiplier(bet_amount, casino_fund_balance)
		view = AviatorView(
			player=interaction.user,
			user_id=user.user_id,
			bet_amount=bet_amount,
			reach_multiplier=reach_multiplier,
			currency_symbol=currency_symbol,
			currency_name=currency_name,
			guild_id=interaction.guild_id,
			channel_id=interaction.channel_id,
			source_id=interaction.id,
		)
		casino_tier = casino_master.get_casino_tier(casino_fund_balance, bet_amount)
		view.note = f"Mesa: {casino_tier}. Retirarse en x1.0 está bloqueado."
		ACTIVE_AVIATOR_SESSIONS[interaction.user.id] = view

		try:
			await interaction.response.send_message(embed=view.build_embed(), view=view)
			view.message = await interaction.original_response()
		except Exception:
			ACTIVE_AVIATOR_SESSIONS.pop(interaction.user.id, None)
			raise


def _resolve_default_bet_amount(min_limit: float) -> float:
	return round(max(float(min_limit or 0.0), 5.0), 2)


def _build_scene_line(current_multiplier: float, state: str) -> str:
	stage = _get_visual_stage(current_multiplier)
	shift = int(round((current_multiplier - 1.0) * 10)) % 4
	space = " "
	wide_space = "  "
	left_sequences = [
		["☁️", "🌲"],
		["🌲", "☁️"],
		["☁️", "🌀"],
		["🌠", "☁️"],
	]
	right_sequences = [
		["☁️", "🌲"],
		["☁️", "🌀"],
		["⭐", "🌀"],
		["⭐", "🌠"],
	]
	plane = _get_plane_icon(state, current_multiplier)
	left = space.join(left_sequences[(stage + shift) % len(left_sequences)])
	right_pool = right_sequences[min(len(right_sequences) - 1, stage)]
	right = space.join(right_pool if shift % 2 == 0 else list(reversed(right_pool)))
	extra = ""
	if stage >= 2:
		extra = space + ("⭐" if shift % 2 == 0 else "🌠")
	if stage >= 4:
		extra += space + "🪐"
	return f"{left}{wide_space}[ x{current_multiplier:.1f} ]{wide_space}{plane}{wide_space}{right}{extra}"


def _build_payout_line(
	bet_amount: float,
	current_multiplier: float,
	currency_symbol: str,
	state: str,
	delta_text: str,
) -> str:
	indent = " " * 5
	if state == "flying":
		current_total = bet_amount + aviator.calculate_cashout_delta(bet_amount, current_multiplier)
		return f"{indent}**{current_total:,.2f}{currency_symbol}**"
	return f"{indent}**{delta_text}{currency_symbol}**"


def _get_visual_stage(current_multiplier: float) -> int:
	if current_multiplier < 1.2:
		return 0
	if current_multiplier < 1.5:
		return 1
	if current_multiplier < 2.0:
		return 2
	if current_multiplier < 3.0:
		return 3
	if current_multiplier < 5.0:
		return 4
	return 5


def _get_plane_icon(state: str, current_multiplier: float) -> str:
	if state == "crashed":
		return "💥"
	if state == "cashed":
		return "🪂"
	if state == "timeout":
		return "🌫️"
	if state == "flying" and current_multiplier <= 1.0:
		return "🛫"
	return "✈️"


def _parse_bet_amount(value: str, current_balance: float) -> tuple[Optional[float], Optional[str]]:
	raw = value.strip().lower()
	if raw == "all":
		return round(float(current_balance), 2), None

	try:
		amount = Decimal(raw)
	except (InvalidOperation, ValueError):
		return None, "❌ Cantidad inválida. Usa un número o 'all'."

	amount = amount.quantize(Decimal("0.01"))
	return float(amount), None


def _ensure_sufficient_balance(
	current_balance: float,
	bet_amount: float,
	currency_name: str,
	currency_symbol: str,
) -> Optional[str]:
	if current_balance <= 0:
		return (
			f"❌ No tienes {currency_name} suficiente para apostar. "
			f"Tienes {current_balance:,.2f}{currency_symbol} y necesitas {bet_amount:,.2f}{currency_symbol}."
		)
	if bet_amount > current_balance:
		faltan = bet_amount - current_balance
		return (
			f"❌ No tienes {currency_name} suficiente para esa apuesta. "
			f"Tienes {current_balance:,.2f}{currency_symbol} y te faltan {faltan:,.2f}{currency_symbol}."
		)
	return None


async def _send_balance_error(interaction: discord.Interaction, message: str) -> None:
	embed = discord.Embed(title="Saldo insuficiente", description=message, color=discord.Color.red())
	await interaction.response.send_message(embed=embed, ephemeral=True)


async def _send_cooldown_error(interaction: discord.Interaction, remaining_seconds: float) -> None:
	minutes = int(remaining_seconds // 60)
	seconds = int(remaining_seconds % 60)
	time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
	embed = discord.Embed(
		title="⏳ Cooldown activo",
		description=f"Debes esperar **{time_str}** antes de iniciar otro vuelo.",
		color=discord.Color.orange(),
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)


async def _send_limit_error(
	interaction: discord.Interaction,
	bet_amount: float,
	limit: float,
	currency_symbol: str,
) -> None:
	embed = discord.Embed(
		title="❌ Límite excedido",
		description=(
			f"La apuesta máxima es **{limit:,.2f}{currency_symbol}**.\n"
			f"Intentaste apostar **{bet_amount:,.2f}{currency_symbol}**."
		),
		color=discord.Color.red(),
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)


async def _send_min_limit_error(
	interaction: discord.Interaction,
	bet_amount: float,
	min_limit: float,
	currency_symbol: str,
) -> None:
	embed = discord.Embed(
		title="❌ Apuesta demasiado baja",
		description=(
			f"La apuesta mínima es **{min_limit:,.2f}{currency_symbol}**.\n"
			f"Intentaste apostar **{bet_amount:,.2f}{currency_symbol}**."
		),
		color=discord.Color.red(),
	)
	await interaction.response.send_message(embed=embed, ephemeral=True)


async def _send_casino_bankruptcy_error(interaction: discord.Interaction) -> None:
	state = get_casino_bankruptcy_state()
	cause_display = str(state.get("cause_display") or "un jugador")
	game_name = str(state.get("game_name") or "casino").upper()

	embed = discord.Embed(
		title="🎰 Casino En Bancarrota",
		description="El fondo del casino está agotado. Aviator no acepta más vuelos hasta recargar fondos.",
		color=discord.Color.red(),
	)
	embed.add_field(name="Causa registrada", value=cause_display, inline=False)
	embed.add_field(name="Último juego", value=game_name, inline=True)
	await interaction.response.send_message(embed=embed, ephemeral=True)


def _get_current_balance(user_id: int) -> float:
	return float(economy_manager.get_total_balance(user_id))
