"""
Discord Store Packager.
Publica el catálogo de backend.managers.store_manager en el foro de tienda configurado.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import discord
from discord.ext import commands

from backend.managers import store_manager
from backend.services.discord_bot.config import get_channels_config
from backend.services.discord_bot.config.economy import get_economy_config
from backend.services.discord_bot.config.store import get_store_config
from backend.services.discord_bot.store.store_sales import process_item_purchase

logger = logging.getLogger(__name__)


class StoreBuyButtonView(discord.ui.View):
	"""Vista persistente para el botón de compra de un item."""

	def __init__(self, item_key: str, custom_id: str):
		super().__init__(timeout=None)
		self.item_key = str(item_key)
		self.custom_id = str(custom_id)

		buy_button = discord.ui.Button(
			label="Comprar",
			style=discord.ButtonStyle.success,
			custom_id=self.custom_id,
			emoji="🛍️",
		)
		buy_button.callback = self._on_buy_click
		self.add_item(buy_button)

	async def _on_buy_click(self, interaction: discord.Interaction) -> None:
		await process_item_purchase(interaction=interaction, item_key=self.item_key)


class DiscordStorePackager:
	"""Puente entre StoreManager y el foro de tienda en Discord."""

	@staticmethod
	def _normalize_internal_id(raw: Any) -> Optional[str]:
		value = str(raw or "").strip().upper()
		if not value:
			return None
		if value.startswith("ID:"):
			value = value[3:].strip().upper()
		if value.startswith("S") and value[1:].isdigit():
			return value
		if value.isdigit():
			return f"S{value}"
		return None

	@staticmethod
	def _normalize_item_type(item: Dict[str, Any]) -> Optional[str]:
		metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
		raw = str(metadata.get("tipo") or "").strip().lower()
		if raw in {"consumable", "consumible"}:
			return "consumible"
		if raw in {"static", "estatico", "estático"}:
			return "estatico"
		return None

	@staticmethod
	def _normalize_rarity(rareza: Any) -> Optional[str]:
		raw = str(rareza or "").strip().lower()
		if not raw:
			return None
		mapping = {
			"common": "comun",
			"comun": "comun",
			"uncommon": "poco comun",
			"poco comun": "poco comun",
			"rare": "raro",
			"raro": "raro",
			"epic": "epico",
			"epico": "epico",
			"legendary": "legendario",
			"legendario": "legendario",
		}
		return mapping.get(raw)

	@staticmethod
	def _build_item_tag_specs(item: Dict[str, Any]) -> list[tuple[str, Optional[str]]]:
		try:
			raw_quantity = item.get("quantity", -1)
			quantity = int(raw_quantity) if raw_quantity is not None else -1
		except Exception:
			quantity = -1

		if quantity == 0:
			# Cuando no hay unidades, forzar etiqueta única de agotado.
			return [("agotado", "📦")]

		tag_specs: list[tuple[str, Optional[str]]] = []

		category = DiscordStorePackager._normalize_item_category(item)
		if category == "sound":
			tag_specs.append(("sonido", "🎧"))
		elif category == "card":
			tag_specs.append(("carta", "⭐"))

		item_type = DiscordStorePackager._normalize_item_type(item)
		if item_type == "consumible":
			tag_specs.append(("consumible", "⬆️"))
		elif item_type == "estatico":
			tag_specs.append(("estatico", "🧱"))

		rareza_tag = DiscordStorePackager._normalize_rarity(item.get("rareza"))
		if rareza_tag:
			tag_specs.append((rareza_tag, None))

		return tag_specs

	@staticmethod
	async def _ensure_forum_tags(
		forum_channel: discord.ForumChannel,
		required_tags: list[tuple[str, Optional[str]]],
	) -> Dict[str, discord.ForumTag]:
		existing_by_name: Dict[str, discord.ForumTag] = {
			tag.name.lower(): tag for tag in forum_channel.available_tags
		}

		missing: list[tuple[str, Optional[str]]] = []
		for name, emoji in required_tags:
			if name.lower() not in existing_by_name:
				missing.append((name, emoji))

		if missing:
			updated_tags = list(forum_channel.available_tags)
			for name, emoji in missing:
				emoji_obj = discord.PartialEmoji.from_str(emoji) if isinstance(emoji, str) and emoji else None
				updated_tags.append(discord.ForumTag(name=name, emoji=emoji_obj))

			try:
				await forum_channel.edit(available_tags=updated_tags, reason="PowerBot store: auto-create forum tags")
			except Exception as exc:
				logger.warning(f"No se pudieron crear tags de foro en guild={forum_channel.guild.id}: {exc}")

			try:
				refreshed = await forum_channel.guild.fetch_channel(forum_channel.id)
				if isinstance(refreshed, discord.ForumChannel):
					forum_channel = refreshed
			except Exception:
				pass

		# Refrescar vista de tags después de crear (si aplica)
		return {tag.name.lower(): tag for tag in forum_channel.available_tags}

	@staticmethod
	def _normalize_item_category(item: Dict[str, Any]) -> str:
		metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
		raw = str(metadata.get("categoria") or metadata.get("category") or "sound").strip().lower()
		if raw in {"card", "cards", "carrd"}:
			return "card"
		if raw in {"sound", "audio", "sfx"}:
			return "sound"
		return "sound"

	@staticmethod
	def _get_rarity_color(rareza: str) -> discord.Color:
		color_map = {
			"common": discord.Color.dark_grey(),
			"uncommon": discord.Color.purple(),
			"rare": discord.Color.blue(),
			"epic": discord.Color.gold(),
			"legendary": discord.Color.green(),
		}
		return color_map.get(str(rareza).lower(), discord.Color.dark_grey())

	@staticmethod
	def _format_card_stats(item: Dict[str, Any], currency_symbol: str) -> str:
		stats_parts: list[str] = []
		if int(item.get("ataque", 0) or 0) > 0:
			stats_parts.append(f"⚔️ **Ataque:** {int(item.get('ataque', 0) or 0)}")
		if int(item.get("defensa", 0) or 0) > 0:
			stats_parts.append(f"🛡️ **Defensa:** {int(item.get('defensa', 0) or 0)}")
		if int(item.get("vida", 0) or 0) > 0:
			stats_parts.append(f"❤️ **Vida:** {int(item.get('vida', 0) or 0)}")
		if int(item.get("armadura", 0) or 0) > 0:
			stats_parts.append(f"🔗 **Armadura:** {int(item.get('armadura', 0) or 0)}")
		if int(item.get("mantenimiento", 0) or 0) > 0:
			symbol_suffix = f" {currency_symbol}" if currency_symbol else ""
			stats_parts.append(
				f"🔧 **Mantenimiento:** {int(item.get('mantenimiento', 0) or 0)}{symbol_suffix}"
			)

		return "\n".join(stats_parts) if stats_parts else "Sin stats"

	@staticmethod
	def _build_sound_embed(
		item: Dict[str, Any],
		currency_symbol: str,
	) -> discord.Embed:
		base_price = float(item.get("base_price", 0.0))
		ip_percent = float(item.get("ip_percent", item.get("ip%", 0.0)))
		raw_quantity = item.get("quantity", -1)
		quantity = int(raw_quantity) if raw_quantity is not None else -1
		internal_id = str(item.get("internal_id") or "S?").upper()
		item_name = str(item.get("nombre", item.get("item_key")))
		rareza_value = item.get("rareza")
		has_rareza = isinstance(rareza_value, str) and rareza_value.strip() != ""
		embed_color = discord.Color.red() if quantity == 0 else (
			DiscordStorePackager._get_rarity_color(str(rareza_value).lower()) if has_rareza else discord.Color.blurple()
		)

		embed = discord.Embed(
			title=f"🎵 `ID:{internal_id}` {item_name}",
			description=str(item.get("descripcion") or "Sin descripción."),
			color=embed_color,
		)

		embed.add_field(name="Tipo", value="sonido", inline=True)

		embed.add_field(
			name="Precio Base",
			value=f"{DiscordStorePackager._format_number(base_price)} {currency_symbol}",
			inline=True,
		)
		embed.add_field(name="ip%", value=f"{DiscordStorePackager._format_number(ip_percent)}%", inline=True)
		embed.add_field(
			name="Cooldown",
			value=DiscordStorePackager._format_seconds(item.get("cooldown", 0)),
			inline=True,
		)
		embed.add_field(
			name="Cooldown Global",
			value=DiscordStorePackager._format_seconds(item.get("global_cooldown", 0)),
			inline=True,
		)
		stock_text = DiscordStorePackager._stock_text(item)
		if stock_text is not None:
			embed.set_footer(text=f"Disponibilidad:\n{stock_text}")
		if has_rareza:
			embed.add_field(name="Rareza", value=str(rareza_value).lower(), inline=True)
		return embed

	@staticmethod
	def _build_card_embed(
		item: Dict[str, Any],
		currency_symbol: str,
	) -> discord.Embed:
		rareza = str(item.get("rareza") or "common").lower()
		raw_quantity = item.get("quantity", -1)
		quantity = int(raw_quantity) if raw_quantity is not None else -1
		internal_id = str(item.get("internal_id") or "S?").upper()
		item_name = str(item.get("nombre", item.get("item_key")))

		base_price = float(item.get("base_price", 0.0))
		ip_percent = float(item.get("ip_percent", item.get("ip%", 0.0)))

		embed = discord.Embed(
			title=f"🃏 `ID:{internal_id}` {item_name}",
			description=str(item.get("descripcion") or "Sin descripción."),
			color=discord.Color.red() if quantity == 0 else DiscordStorePackager._get_rarity_color(rareza),
		)

		embed.add_field(name="Tipo", value="carta", inline=True)
		embed.add_field(name="Rareza", value=rareza, inline=True)
		embed.add_field(
			name="Precio Base",
			value=f"{DiscordStorePackager._format_number(base_price)} {currency_symbol}",
			inline=True,
		)
		embed.add_field(name="ip%", value=f"{DiscordStorePackager._format_number(ip_percent)}%", inline=True)
		embed.add_field(
			name="Cooldown",
			value=DiscordStorePackager._format_seconds(item.get("cooldown", 0)),
			inline=True,
		)
		embed.add_field(
			name="Cooldown Global",
			value=DiscordStorePackager._format_seconds(item.get("global_cooldown", 0)),
			inline=True,
		)
		stock_text = DiscordStorePackager._stock_text(item)
		if stock_text is not None:
			embed.set_footer(text=f"Disponibilidad:\n{stock_text}")
		embed.add_field(
			name="⚙️ Stats",
			value=DiscordStorePackager._format_card_stats(item, currency_symbol=currency_symbol),
			inline=False,
		)

		return embed

	@staticmethod
	def _project_root() -> Path:
		return Path(__file__).resolve().parents[4]

	@staticmethod
	def _data_dir() -> Path:
		path = DiscordStorePackager._project_root() / "backend" / "data" / "discord_bot"
		path.mkdir(parents=True, exist_ok=True)
		return path

	@staticmethod
	def _index_file(guild_id: int) -> Path:
		return DiscordStorePackager._data_dir() / f"guild_{guild_id}_store_posts.json"

	@staticmethod
	def _load_posts_index(guild_id: int) -> Dict[str, Any]:
		path = DiscordStorePackager._index_file(guild_id)
		if not path.exists():
			return {"posts": {}}

		try:
			with open(path, "r", encoding="utf-8") as file:
				data = json.load(file)
				if isinstance(data, dict):
					posts = data.get("posts") if isinstance(data.get("posts"), dict) else {}
					return {"posts": posts}
		except Exception as exc:
			logger.warning(f"Store post index corrupto en guild {guild_id}: {exc}")

		return {"posts": {}}

	@staticmethod
	def _save_posts_index(guild_id: int, data: Dict[str, Any]) -> None:
		path = DiscordStorePackager._index_file(guild_id)
		payload = {
			"posts": data.get("posts", {}),
		}
		with open(path, "w", encoding="utf-8") as file:
			json.dump(payload, file, indent=2, ensure_ascii=False)

	@staticmethod
	def _resolve_abs(asset_rel_or_abs: str) -> Path:
		path = Path(asset_rel_or_abs)
		if path.is_absolute():
			return path
		return DiscordStorePackager._project_root() / path

	@staticmethod
	def _build_buy_custom_id(guild_id: int, item_key: str) -> str:
		safe_key = str(item_key).strip().lower()
		hash_suffix = hashlib.sha1(safe_key.encode("utf-8")).hexdigest()[:12]
		return f"powerbot:store:buy:{guild_id}:{hash_suffix}"

	@staticmethod
	def _build_buy_view(guild_id: int, item_key: str) -> StoreBuyButtonView:
		custom_id = DiscordStorePackager._build_buy_custom_id(guild_id=guild_id, item_key=item_key)
		return StoreBuyButtonView(item_key=item_key, custom_id=custom_id)

	@staticmethod
	def _format_number(value: float) -> str:
		"""Formato con máximo 2 decimales, omitiendo ceros innecesarios."""
		return f"{float(value):,.2f}".rstrip("0").rstrip(".")

	@staticmethod
	def _format_seconds(seconds: Any) -> str:
		try:
			total = max(0, int(seconds or 0))
		except Exception:
			total = 0

		hours = total // 3600
		minutes = (total % 3600) // 60
		secs = total % 60
		parts: list[str] = []
		if hours > 0:
			parts.append(f"{hours}h")
		if minutes > 0:
			parts.append(f"{minutes}m")
		if secs > 0 or not parts:
			parts.append(f"{secs}s")
		return " ".join(parts)

	@staticmethod
	def _stock_text(item: Dict[str, Any]) -> Optional[str]:
		try:
			raw_quantity = item.get("quantity", -1)
			quantity = int(raw_quantity) if raw_quantity is not None else -1
		except Exception:
			quantity = -1

		if quantity < 0:
			return None
		if quantity == 0:
			return "Agotado"
		if quantity == 1:
			return "1 unidad"
		return f"{quantity} unidades"

	@staticmethod
	def _build_embed(
		item: Dict[str, Any],
		currency_symbol: str,
		currency_name: str,
	) -> discord.Embed:
		_ = currency_name  # reservado para usos futuros
		item_category = DiscordStorePackager._normalize_item_category(item)
		if item_category == "card":
			return DiscordStorePackager._build_card_embed(item=item, currency_symbol=currency_symbol)
		return DiscordStorePackager._build_sound_embed(item=item, currency_symbol=currency_symbol)

	@staticmethod
	def _build_files(item: Dict[str, Any]) -> list[discord.File]:
		files: list[discord.File] = []

		for key in ("thumbnail", "video", "audio"):
			raw_value = item.get(key)
			if not isinstance(raw_value, str) or not raw_value.strip():
				continue
			path = DiscordStorePackager._resolve_abs(raw_value)
			if path.exists() and path.is_file():
				files.append(discord.File(path, filename=path.name))

		return files

	@staticmethod
	def _get_forum_channel(bot: commands.Bot, guild: discord.Guild) -> Optional[discord.ForumChannel]:
		channels_config = get_channels_config(guild.id)
		forum_channel_id = channels_config.get_channel("store_forum_channel")
		if not forum_channel_id:
			return None

		channel = guild.get_channel(int(forum_channel_id)) or bot.get_channel(int(forum_channel_id))
		if isinstance(channel, discord.ForumChannel):
			return channel
		return None

	@staticmethod
	async def publish_store_for_guild(
		bot: commands.Bot,
		guild_id: int,
		force_republish: bool = False,
		item_id: Optional[str] = None,
	) -> Dict[str, Any]:
		"""
		Publica o actualiza el catálogo de la tienda en el foro configurado para un servidor.
		
		- Lee items desde store_manager.
		- Si el hilo ya existe, lo actualiza (embed, tags, botón).
		- Si no existe, lo publica.
		- Permite filtrar por internal_id (S1, S2, ...).
		"""
		guild = bot.get_guild(int(guild_id))
		if guild is None:
			return {
				"success": False,
				"message": f"Guild no encontrada: {guild_id}",
				"published": 0,
				"updated": 0,
				"skipped": 0,
				"failed": 0,
			}

		forum_channel = DiscordStorePackager._get_forum_channel(bot, guild)
		if forum_channel is None:
			return {
				"success": False,
				"message": "No hay foro de tienda configurado en channels.py (store_forum_channel)",
				"published": 0,
				"updated": 0,
				"skipped": 0,
				"failed": 0,
			}

		sync_result = store_manager.refresh_store_items()
		items = store_manager.get_store_items()
		requested_internal_id = DiscordStorePackager._normalize_internal_id(item_id)
		if item_id is not None and requested_internal_id is None:
			return {
				"success": False,
				"message": f"ID de item inválido: {item_id}. Usa formato S1, S2, ...",
				"published": 0,
				"updated": 0,
				"skipped": 0,
				"failed": 0,
				"errors": [],
			}

		if requested_internal_id is not None:
			items = [
				item
				for item in items
				if DiscordStorePackager._normalize_internal_id(item.get("internal_id")) == requested_internal_id
			]
			if not items:
				return {
					"success": False,
					"message": f"No existe item con ID `{requested_internal_id}`",
					"published": 0,
					"updated": 0,
					"skipped": 0,
					"failed": 0,
					"errors": [],
				}

		index = DiscordStorePackager._load_posts_index(guild.id)
		posts_index: Dict[str, Any] = index.get("posts", {})
		store_config = get_store_config(guild.id)
		economy_config = get_economy_config(guild.id)
		currency_symbol = economy_config.get_currency_symbol()
		currency_name = economy_config.get_currency_name()

		published = 0
		updated = 0
		skipped = 0
		failed = 0
		errors: list[str] = []

		for item in items:
			item_key = str(item.get("item_key") or "").strip()
			if not item_key:
				failed += 1
				errors.append("Item sin item_key")
				continue

			known_thread_id = posts_index.get(item_key)
			if not known_thread_id:
				for _, info in store_config.list_purchase_buttons().items():
					if str(info.get("item_key") or "").strip() == item_key and info.get("thread_id") is not None:
						known_thread_id = int(info.get("thread_id"))
						posts_index[item_key] = known_thread_id
						break

			thread_obj: Optional[discord.Thread] = None
			if known_thread_id and not force_republish:
				thread_obj = guild.get_thread(int(known_thread_id))
				if thread_obj is None:
					thread_obj = bot.get_channel(int(known_thread_id))

			embed = DiscordStorePackager._build_embed(
				item,
				currency_symbol=currency_symbol,
				currency_name=currency_name,
			)
			tag_specs = DiscordStorePackager._build_item_tag_specs(item)
			tags_by_name = await DiscordStorePackager._ensure_forum_tags(forum_channel, tag_specs)
			applied_tags = [tags_by_name[name.lower()] for name, _ in tag_specs if name.lower() in tags_by_name]
			buy_view = DiscordStorePackager._build_buy_view(guild_id=guild.id, item_key=item_key)
			files = DiscordStorePackager._build_files(item)
			if files:
				item_category = DiscordStorePackager._normalize_item_category(item)
				thumbnail_name = Path(str(item.get("thumbnail"))).name
				if item_category == "card":
					embed.set_image(url=f"attachment://{thumbnail_name}")
				else:
					embed.set_thumbnail(url=f"attachment://{thumbnail_name}")

			thread_name = f"{item.get('nombre', item_key)}"
			if len(thread_name) > 100:
				thread_name = thread_name[:100]

			if isinstance(thread_obj, discord.Thread) and not force_republish:
				try:
					await thread_obj.edit(
						name=thread_name,
						applied_tags=applied_tags if applied_tags else [],
						reason="PowerBot store sync: actualizar item",
					)

					buttons = store_config.list_purchase_buttons()
					custom_id = DiscordStorePackager._build_buy_custom_id(guild_id=guild.id, item_key=item_key)
					message_id: Optional[int] = None
					for saved_custom_id, info in buttons.items():
						if str(info.get("item_key") or "").strip() != item_key:
							continue
						if info.get("thread_id") is not None and int(info.get("thread_id")) != int(thread_obj.id):
							continue
						custom_id = saved_custom_id
						if info.get("message_id") is not None:
							message_id = int(info.get("message_id"))
						break

					buy_view = StoreBuyButtonView(item_key=item_key, custom_id=custom_id)
					starter_message: Optional[discord.Message] = None

					if message_id is not None:
						try:
							starter_message = await thread_obj.fetch_message(message_id)
						except Exception:
							starter_message = None

					if starter_message is None:
						async for msg in thread_obj.history(limit=1, oldest_first=True):
							starter_message = msg
							break

					if starter_message is None:
						raise RuntimeError("No se encontró mensaje inicial del hilo para actualizar")

					if files:
						try:
							await starter_message.edit(embed=embed, view=buy_view, attachments=files)
						except TypeError:
							await starter_message.edit(embed=embed, view=buy_view)
					else:
						try:
							await starter_message.edit(embed=embed, view=buy_view, attachments=[])
						except TypeError:
							await starter_message.edit(embed=embed, view=buy_view)

					store_config.set_purchase_button(
						custom_id=custom_id,
						item_key=item_key,
						thread_id=int(thread_obj.id),
						message_id=int(starter_message.id),
					)
					bot.add_view(buy_view)
					updated += 1
					continue
				except Exception as exc:
					failed += 1
					errors.append(f"{item_key}: {exc}")
					logger.error(f"Error actualizando item {item_key} en guild {guild.id}: {exc}")
					continue

			try:
				created = await forum_channel.create_thread(
					name=thread_name,
					embed=embed,
					applied_tags=applied_tags if applied_tags else None,
					view=buy_view,
					files=files if files else None,
				)
				thread_obj = created.thread if hasattr(created, "thread") else created
				message_obj = created.message if hasattr(created, "message") else None
				starter_message_id = int(message_obj.id) if message_obj is not None else None
				if isinstance(thread_obj, discord.Thread):
					posts_index[item_key] = int(thread_obj.id)
					if starter_message_id is None:
						starter_message_id = int(thread_obj.id)

				custom_id = buy_view.custom_id
				store_config.set_purchase_button(
					custom_id=custom_id,
					item_key=item_key,
					thread_id=int(thread_obj.id) if isinstance(thread_obj, discord.Thread) else None,
					message_id=starter_message_id,
				)
				bot.add_view(buy_view)
				published += 1
			except Exception as exc:
				failed += 1
				errors.append(f"{item_key}: {exc}")
				logger.error(f"Error publicando item {item_key} en guild {guild.id}: {exc}")

		DiscordStorePackager._save_posts_index(guild.id, {"posts": posts_index})

		return {
			"success": failed == 0,
			"message": "Store sincronizado" if failed == 0 else "Store sincronizado con errores",
			"forum_channel_id": forum_channel.id,
			"sync": sync_result,
			"published": published,
			"updated": updated,
			"skipped": skipped,
			"failed": failed,
			"filtered_item_id": requested_internal_id,
			"errors": errors,
		}

	@staticmethod
	async def publish_store_all_guilds(bot: commands.Bot, force_republish: bool = False) -> Dict[int, Dict[str, Any]]:
		"""Publica la tienda en todos los guilds conectados donde exista store_forum_channel."""
		results: Dict[int, Dict[str, Any]] = {}
		for guild in bot.guilds:
			results[guild.id] = await DiscordStorePackager.publish_store_for_guild(
				bot=bot,
				guild_id=guild.id,
				force_republish=force_republish,
			)
		return results

	@staticmethod
	async def register_persistent_buy_buttons(bot: commands.Bot) -> None:
		"""Re-registra en memoria los botones de compra guardados para sobrevivir reinicios."""
		for guild in bot.guilds:
			store_config = get_store_config(guild.id)
			buttons = store_config.list_purchase_buttons()
			for custom_id, info in buttons.items():
				item_key = str(info.get("item_key") or "").strip()
				if not item_key:
					continue
				try:
					bot.add_view(StoreBuyButtonView(item_key=item_key, custom_id=custom_id))
				except Exception as exc:
					logger.warning(
						f"No se pudo re-registrar botón de store guild={guild.id} custom_id={custom_id}: {exc}"
					)

