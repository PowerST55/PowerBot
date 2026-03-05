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
		# Placeholder para implementar la compra real más adelante.
		await interaction.response.send_message(
			f"La compra de `{self.item_key}` todavía no está implementada.",
			ephemeral=True,
		)


class DiscordStorePackager:
	"""Puente entre StoreManager y el foro de tienda en Discord."""

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
	def _build_embed(
		item: Dict[str, Any],
		currency_symbol: str,
		currency_name: str,
	) -> discord.Embed:
		base_price = float(item.get("base_price", 0.0))
		ip_percent = float(item.get("ip_percent", item.get("ip%", 0.0)))

		embed = discord.Embed(
			title=f"🛒 {item.get('nombre', item.get('item_key'))}",
			description=str(item.get("descripcion") or "Sin descripción."),
			color=discord.Color.blurple(),
		)

		embed.add_field(
			name="Precio Base",
			value=f"{DiscordStorePackager._format_number(base_price)} {currency_symbol}",
			inline=True,
		)
		embed.add_field(name="ip%", value=f"{DiscordStorePackager._format_number(ip_percent)}%", inline=True)

		return embed

	@staticmethod
	def _build_files(item: Dict[str, Any]) -> list[discord.File]:
		files: list[discord.File] = []

		thumbnail_path = DiscordStorePackager._resolve_abs(str(item.get("thumbnail", "")))
		video_path = DiscordStorePackager._resolve_abs(str(item.get("video", "")))
		audio_path = DiscordStorePackager._resolve_abs(str(item.get("audio", "")))

		if thumbnail_path.exists() and thumbnail_path.is_file():
			files.append(discord.File(thumbnail_path, filename=thumbnail_path.name))
		if video_path.exists() and video_path.is_file():
			files.append(discord.File(video_path, filename=video_path.name))
		if audio_path.exists() and audio_path.is_file():
			files.append(discord.File(audio_path, filename=audio_path.name))

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
	) -> Dict[str, Any]:
		"""
		Publica el catálogo de la tienda en el foro configurado para un servidor.
		
		- Lee items desde store_manager.
		- Publica cada item como hilo de foro.
		- Evita duplicados usando índice local por guild.
		"""
		guild = bot.get_guild(int(guild_id))
		if guild is None:
			return {
				"success": False,
				"message": f"Guild no encontrada: {guild_id}",
				"published": 0,
				"skipped": 0,
				"failed": 0,
			}

		forum_channel = DiscordStorePackager._get_forum_channel(bot, guild)
		if forum_channel is None:
			return {
				"success": False,
				"message": "No hay foro de tienda configurado en channels.py (store_forum_channel)",
				"published": 0,
				"skipped": 0,
				"failed": 0,
			}

		sync_result = store_manager.refresh_store_items()
		items = store_manager.get_store_items()
		index = DiscordStorePackager._load_posts_index(guild.id)
		posts_index: Dict[str, Any] = index.get("posts", {})
		store_config = get_store_config(guild.id)
		economy_config = get_economy_config(guild.id)
		currency_symbol = economy_config.get_currency_symbol()
		currency_name = economy_config.get_currency_name()

		published = 0
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
			thread_exists = False
			if known_thread_id and not force_republish:
				thread = guild.get_thread(int(known_thread_id))
				if thread is None:
					thread = bot.get_channel(int(known_thread_id))
				if isinstance(thread, discord.Thread):
					thread_exists = True

			if thread_exists and not force_republish:
				skipped += 1
				continue

			embed = DiscordStorePackager._build_embed(
				item,
				currency_symbol=currency_symbol,
				currency_name=currency_name,
			)
			buy_view = DiscordStorePackager._build_buy_view(guild_id=guild.id, item_key=item_key)
			files = DiscordStorePackager._build_files(item)
			if files:
				embed.set_thumbnail(url=f"attachment://{Path(str(item.get('thumbnail'))).name}")

			thread_name = f"🛍️ {item.get('nombre', item_key)}"
			if len(thread_name) > 100:
				thread_name = thread_name[:100]

			try:
				created = await forum_channel.create_thread(
					name=thread_name,
					content="Publicación automática de catálogo store.",
					embed=embed,
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
			"message": "Store publicado" if failed == 0 else "Store publicado con errores",
			"forum_channel_id": forum_channel.id,
			"sync": sync_result,
			"published": published,
			"skipped": skipped,
			"failed": failed,
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

