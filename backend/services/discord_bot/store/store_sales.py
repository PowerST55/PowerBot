"""Logica de ventas para la tienda de Discord."""

from __future__ import annotations

import os
import discord

from backend.managers import store_manager
from backend.managers.economy_manager import apply_balance_delta, get_user_balance_by_id
from backend.managers.stream_manager import StreamManager
from backend.managers.user_manager import get_discord_profile_by_discord_id
from backend.services.discord_bot.config.economy import get_economy_config
from backend.services.events_websocket.livefeed import notifications as ws_notifications
from backend.services.store.config.cooldown import create_store_cooldown_manager
from backend.services.store.store_core import create_store_toggle_manager


def _closed_store_embed() -> discord.Embed:
	return discord.Embed(
		title="🏪 Tienda cerrada",
		description="La tienda esta cerrada, vuelve a intentarlo mas tarde.",
		color=discord.Color.red(),
	)


def _development_embed(item_key: str) -> discord.Embed:
	return discord.Embed(
		title="🛠️ Tienda en desarrollo",
		description=(
			"La tienda esta en desarrollo.\n"
			f"Item seleccionado: `{item_key}`"
		),
		color=discord.Color.blurple(),
	)


def _development_purchase_embed(item_key: str, remaining_quantity: int, infinite: bool) -> discord.Embed:
	stock_text = "infinito" if infinite else str(max(0, int(remaining_quantity or 0)))
	return discord.Embed(
		title="🛠️ Compra validada (modo desarrollo)",
		description=(
			f"Item seleccionado: `{item_key}`\n"
			f"Stock restante: `{stock_text}`"
		),
		color=discord.Color.blurple(),
	)


def _purchase_success_embed(item_name: str, total_price: float, currency_symbol: str, balance_after: float) -> discord.Embed:
	return discord.Embed(
		title="✅ Compra realizada",
		description=(
			f"Compraste **{item_name}** correctamente.\n"
			f"Costo: `{_format_points(total_price)} {currency_symbol}`\n"
			f"Saldo restante: `{_format_points(balance_after)} {currency_symbol}`"
		),
		color=discord.Color.green(),
	)


def _purchase_cancelled_embed(item_name: str) -> discord.Embed:
	return discord.Embed(
		title="❎ Compra cancelada",
		description=f"La compra de **{item_name}** fue cancelada.",
		color=discord.Color.light_grey(),
	)


def _insufficient_balance_embed(item_name: str, total_price: float, currency_symbol: str, balance: float) -> discord.Embed:
	return discord.Embed(
		title="💸 Saldo insuficiente",
		description=(
			f"No tienes puntos suficientes para comprar **{item_name}**.\n"
			f"Costo: `{_format_points(total_price)} {currency_symbol}`\n"
			f"Tu saldo: `{_format_points(balance)} {currency_symbol}`"
		),
		color=discord.Color.red(),
	)


def _purchase_error_embed(message: str) -> discord.Embed:
	return discord.Embed(
		title="❌ No se pudo completar la compra",
		description=message,
		color=discord.Color.red(),
	)


def _confirm_purchase_embed(item_name: str, total_price: float, currency_symbol: str) -> discord.Embed:
	return discord.Embed(
		title="🛍️ Confirmar compra",
		description=(
			f"Estas seguro que quieres comprar **{item_name}**\n"
			f"Te costara `{_format_points(total_price)} {currency_symbol}`"
		),
		color=discord.Color.blurple(),
	)


def _linked_account_required_embed() -> discord.Embed:
	return discord.Embed(
		title="🔗 Cuenta no vinculada",
		description=(
			"No encontramos tu perfil económico de Discord.\n"
			"Vincula tu cuenta antes de comprar en la tienda."
		),
		color=discord.Color.red(),
	)


def _item_not_found_embed(item_key: str) -> discord.Embed:
	return discord.Embed(
		title="❌ Item no encontrado",
		description=f"No se encontró el item `{item_key}` en el catálogo.",
		color=discord.Color.red(),
	)


def _format_seconds(seconds: int) -> str:
	seconds = max(0, int(seconds or 0))
	hours = seconds // 3600
	minutes = (seconds % 3600) // 60
	secs = seconds % 60

	parts: list[str] = []
	if hours > 0:
		parts.append(f"{hours}h")
	if minutes > 0:
		parts.append(f"{minutes}m")
	if secs > 0 or not parts:
		parts.append(f"{secs}s")
	return " ".join(parts)


def _cooldown_blocked_embed(item_name: str, user_remaining: int, global_remaining: int) -> discord.Embed:
	lines: list[str] = [f"El item **{item_name}** todavía está en cooldown."]
	if user_remaining > 0:
		lines.append(f"- Cooldown personal: `{_format_seconds(user_remaining)}`")
	if global_remaining > 0:
		lines.append(f"- Cooldown global: `{_format_seconds(global_remaining)}`")

	return discord.Embed(
		title="⏳ Cooldown activo",
		description="\n".join(lines),
		color=discord.Color.orange(),
	)


def _out_of_stock_embed(item_name: str) -> discord.Embed:
	return discord.Embed(
		title="📦 Sin stock",
		description=f"El item **{item_name}** ya no tiene unidades disponibles.",
		color=discord.Color.red(),
	)


def _normalize_item_category(item: dict) -> str:
	metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
	raw = str(metadata.get("categoria") or metadata.get("category") or "sound").strip().lower()
	if raw in {"sound", "audio", "sfx"}:
		return "sound"
	if raw in {"card", "cards", "carrd"}:
		return "card"
	return raw


def _stream_required_for_sound_embed() -> discord.Embed:
	return discord.Embed(
		title="📡 Stream requerido",
		description=(
			"Los items de categoría **sound** solo se pueden comprar cuando hay un stream activo.\n"
			"Para solicitar stream usa **`/stream`**."
		),
		color=discord.Color.orange(),
	)


def _only_sound_sales_available_embed() -> discord.Embed:
	return discord.Embed(
		title="🛠️ Venta en desarrollo",
		description="Por ahora solo están habilitadas las ventas para items de categoría **sound**.",
		color=discord.Color.orange(),
	)


def _format_points(value: float | int) -> str:
	return f"{float(value):,.2f}".rstrip("0").rstrip(".")


def _public_asset_url(asset_rel_or_abs: str | None) -> str:
	value = str(asset_rel_or_abs or "").strip()
	if not value:
		return ""

	lower = value.lower()
	if lower.startswith("http://") or lower.startswith("https://"):
		return value

	path = value.replace("\\", "/")
	if not path.startswith("/"):
		path = f"/{path}"

	host = os.getenv("WEB_HOST", "127.0.0.1").strip() or "127.0.0.1"
	if host in {"0.0.0.0", "::", "*"}:
		host = "127.0.0.1"
	port = os.getenv("WEB_PORT", "19131").strip() or "19131"
	scheme = os.getenv("WEB_SCHEME", "http").strip() or "http"
	return f"{scheme}://{host}:{port}{path}"


def _get_currency_symbol_for_guild(interaction: discord.Interaction) -> str:
	if interaction.guild is None:
		return ""
	try:
		return str(get_economy_config(interaction.guild.id).get_currency_symbol() or "")
	except Exception:
		return ""


def _get_user_profile(interaction: discord.Interaction):
	return get_discord_profile_by_discord_id(str(interaction.user.id))


def _get_user_price(item: dict, user_id: int) -> float | None:
	pricing = store_manager.calculate_user_price(item_key=str(item.get("item_key") or ""), user_id=int(user_id))
	if not pricing:
		return None
	return float(pricing.get("final_price", 0.0) or 0.0)


class StorePurchaseConfirmView(discord.ui.View):
	"""Confirmación ephemeral para compras de items sound."""

	def __init__(self, *, item_key: str, buyer_discord_id: int, timeout: float = 45.0):
		super().__init__(timeout=timeout)
		self.item_key = str(item_key)
		self.buyer_discord_id = int(buyer_discord_id)

	async def _reject_other_user(self, interaction: discord.Interaction) -> bool:
		if int(interaction.user.id) == self.buyer_discord_id:
			return False
		await interaction.response.send_message(
			embed=discord.Embed(
				title="🔒 Acción no permitida",
				description="Solo el usuario que inició la compra puede confirmarla.",
				color=discord.Color.red(),
			),
			ephemeral=True,
		)
		return True

	@discord.ui.button(label="Confirmar compra", style=discord.ButtonStyle.success, emoji="✅")
	async def confirm_purchase(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		if await self._reject_other_user(interaction):
			return

		# Ack inmediato para evitar "This interaction failed" en operaciones largas
		# (DB, sync de foro y notificación websocket).
		await interaction.response.defer()
		try:
			embed = await _finalize_sound_purchase(interaction=interaction, item_key=self.item_key)
		except Exception:
			embed = _purchase_error_embed("Ocurrió un error interno procesando la compra. Inténtalo de nuevo.")

		await interaction.edit_original_response(embed=embed, view=None)

	@discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="❌")
	async def cancel_purchase(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		if await self._reject_other_user(interaction):
			return

		item = store_manager.get_store_item(self.item_key) or {}
		item_name = str(item.get("nombre") or item.get("item_key") or self.item_key)
		await interaction.response.edit_message(embed=_purchase_cancelled_embed(item_name), view=None)


async def _sync_store_item_post(interaction: discord.Interaction, item: dict) -> None:
	"""Refresca el hilo del item para reflejar cambios de stock/tags."""
	try:
		from backend.services.discord_bot.store.store_packager import DiscordStorePackager

		bot_client = interaction.client
		if hasattr(bot_client, "get_guild") and interaction.guild is not None:
			await DiscordStorePackager.publish_store_for_guild(
				bot=bot_client,
				guild_id=interaction.guild.id,
				force_republish=False,
				item_id=str(item.get("internal_id") or ""),
			)
	except Exception:
		# No bloquear compra por un fallo de sincronización visual.
		pass


async def _send_sound_purchase_notification(
	interaction: discord.Interaction,
	item: dict,
) -> bool:
	video_url = _public_asset_url(item.get("video"))
	if not video_url:
		return False

	audio_url = _public_asset_url(item.get("audio"))
	item_key = str(item.get("item_key") or "")
	internal_id = str(item.get("internal_id") or "").upper()
	item_name = str(item.get("nombre") or item_key)

	message_text = f"{interaction.user.display_name} compró {item_name}"
	return await ws_notifications.send_store_sound_notification(
		notification_id=item_key,
		internal_id=internal_id,
		item_name=item_name,
		video_path=video_url,
		audio_path=audio_url or None,
		title_text="Compra en tienda",
		message_text=message_text,
		simulation=False,
		source="discord_store_purchase",
	)


async def _finalize_sound_purchase(interaction: discord.Interaction, item_key: str) -> discord.Embed:
	"""Completa compra real de item sound: cobro, stock, cooldown y broadcast."""
	toggle_manager = create_store_toggle_manager()
	if not toggle_manager.is_enabled():
		return _closed_store_embed()

	item = store_manager.get_store_item(str(item_key or ""))
	if not item:
		return _item_not_found_embed(str(item_key or ""))

	item_name = str(item.get("nombre") or item.get("item_key") or "item")
	if _normalize_item_category(item) != "sound":
		return _only_sound_sales_available_embed()

	stream_state = StreamManager().get_status()
	if not bool(stream_state.get("is_live", False)):
		return _stream_required_for_sound_embed()

	raw_quantity = item.get("quantity", -1)
	quantity = int(raw_quantity) if raw_quantity is not None else -1
	if quantity == 0:
		return _out_of_stock_embed(item_name)

	profile = _get_user_profile(interaction)
	if not profile:
		return _linked_account_required_embed()

	user_id = int(profile.user_id)
	total_price = _get_user_price(item=item, user_id=user_id)
	if total_price is None or total_price < 0:
		return _purchase_error_embed("No se pudo calcular el precio del item para tu cuenta.")

	balance_info = get_user_balance_by_id(user_id)
	if not balance_info.get("user_exists"):
		return _linked_account_required_embed()

	user_balance = float(balance_info.get("global_points", 0.0) or 0.0)
	currency_symbol = _get_currency_symbol_for_guild(interaction)
	if user_balance < total_price:
		return _insufficient_balance_embed(item_name, total_price, currency_symbol, user_balance)

	item_cooldown = max(0, int(item.get("cooldown", 0) or 0))
	global_cooldown = max(0, int(item.get("global_cooldown", 0) or 0))
	cooldown_manager = create_store_cooldown_manager()
	status = cooldown_manager.get_cooldown_status(item_key=str(item.get("item_key") or ""), user_id=int(interaction.user.id))
	if status.get("blocked"):
		return _cooldown_blocked_embed(
			item_name=item_name,
			user_remaining=int(status.get("user_remaining", 0) or 0),
			global_remaining=int(status.get("global_remaining", 0) or 0),
		)

	guild_id_text = str(interaction.guild.id) if interaction.guild else None
	channel_id_text = str(interaction.channel_id) if interaction.channel_id else None
	source_id = f"store_purchase:{guild_id_text or 'noguild'}:{item.get('item_key')}:{interaction.id}"

	try:
		balance_after = apply_balance_delta(
			user_id=user_id,
			delta=-total_price,
			reason="store_purchase_sound",
			platform="discord",
			guild_id=guild_id_text,
			channel_id=channel_id_text,
			source_id=source_id,
		)
	except ValueError:
		return _insufficient_balance_embed(item_name, total_price, currency_symbol, user_balance)
	except Exception:
		return _purchase_error_embed("Ocurrió un error descontando puntos. Inténtalo de nuevo.")

	stock_result = store_manager.consume_store_item_stock(
		item_key=str(item.get("item_key") or ""),
		amount=1,
	)
	if not stock_result.get("success"):
		# Reembolso de seguridad si se cobró pero no se pudo descontar stock.
		try:
			apply_balance_delta(
				user_id=user_id,
				delta=total_price,
				reason="store_purchase_refund_stock_failed",
				platform="discord",
				guild_id=guild_id_text,
				channel_id=channel_id_text,
				source_id=f"{source_id}:refund",
			)
		except Exception:
			pass
		return _out_of_stock_embed(item_name)

	cooldown_manager.register_purchase(
		item_key=str(item.get("item_key") or ""),
		user_id=int(interaction.user.id),
		user_cooldown_seconds=item_cooldown,
		global_cooldown_seconds=global_cooldown,
	)

	await _sync_store_item_post(interaction=interaction, item=item)
	await _send_sound_purchase_notification(interaction=interaction, item=item)

	return _purchase_success_embed(
		item_name=item_name,
		total_price=total_price,
		currency_symbol=currency_symbol,
		balance_after=float(balance_after),
	)


async def process_item_purchase(interaction: discord.Interaction, item_key: str) -> None:
	"""Primer paso de compra: valida y pide confirmación con precio personalizado."""
	try:
		toggle_manager = create_store_toggle_manager()
		if not toggle_manager.is_enabled():
			await interaction.response.send_message(embed=_closed_store_embed(), ephemeral=True)
			return

		item = store_manager.get_store_item(str(item_key or ""))
		if not item:
			await interaction.response.send_message(embed=_item_not_found_embed(str(item_key or "")), ephemeral=True)
			return

		item_category = _normalize_item_category(item)
		if item_category != "sound":
			await interaction.response.send_message(embed=_only_sound_sales_available_embed(), ephemeral=True)
			return

		stream_state = StreamManager().get_status()
		if not bool(stream_state.get("is_live", False)):
			await interaction.response.send_message(
				embed=_stream_required_for_sound_embed(),
				ephemeral=True,
			)
			return

		raw_quantity = item.get("quantity", -1)
		quantity = int(raw_quantity) if raw_quantity is not None else -1
		if quantity == 0:
			await interaction.response.send_message(
				embed=_out_of_stock_embed(str(item.get("nombre") or item.get("item_key") or "item")),
				ephemeral=True,
			)
			return

		profile = _get_user_profile(interaction)
		if not profile:
			await interaction.response.send_message(embed=_linked_account_required_embed(), ephemeral=True)
			return

		total_price = _get_user_price(item=item, user_id=int(profile.user_id))
		if total_price is None or total_price < 0:
			await interaction.response.send_message(
				embed=_purchase_error_embed("No se pudo calcular el precio del item para tu cuenta."),
				ephemeral=True,
			)
			return

		currency_symbol = _get_currency_symbol_for_guild(interaction)
		item_name = str(item.get("nombre") or item.get("item_key") or item_key)
		confirm_view = StorePurchaseConfirmView(item_key=str(item.get("item_key") or item_key), buyer_discord_id=int(interaction.user.id))
		await interaction.response.send_message(
			embed=_confirm_purchase_embed(item_name=item_name, total_price=total_price, currency_symbol=currency_symbol),
			view=confirm_view,
			ephemeral=True,
		)
	except Exception:
		if interaction.response.is_done():
			await interaction.followup.send(
				embed=_purchase_error_embed("Error interno procesando la compra. Vuelve a intentarlo."),
				ephemeral=True,
			)
		else:
			await interaction.response.send_message(
				embed=_purchase_error_embed("Error interno procesando la compra. Vuelve a intentarlo."),
				ephemeral=True,
			)
