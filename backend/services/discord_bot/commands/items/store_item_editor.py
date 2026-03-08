"""Editor administrativo de items de tienda para /admin_store editor."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import discord
from discord import app_commands
from discord.ext import commands

from backend.managers import store_manager
from backend.services.discord_bot.store.store_packager import DiscordStorePackager


@dataclass
class EditableStoreItem:
	item_key: str
	internal_id: str
	config_path: Path
	item_data: dict[str, Any]


def _normalize_internal_id(raw: str) -> Optional[str]:
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


def _load_item_by_internal_id(raw_item_id: str) -> Optional[EditableStoreItem]:
	target_id = _normalize_internal_id(raw_item_id)
	if target_id is None:
		return None

	store_manager.refresh_store_items()
	items = store_manager.get_store_items()

	selected: Optional[dict[str, Any]] = None
	for item in items:
		item_id = _normalize_internal_id(str(item.get("internal_id") or ""))
		if item_id == target_id:
			selected = item
			break

	if selected is None:
		return None

	config_rel = str(selected.get("config_file") or "").strip()
	if not config_rel:
		return None

	config_path = store_manager.PROJECT_ROOT / config_rel
	return EditableStoreItem(
		item_key=str(selected.get("item_key") or ""),
		internal_id=target_id,
		config_path=config_path,
		item_data=selected,
	)


def _read_item_config(path: Path) -> dict[str, Any]:
	with open(path, "r", encoding="utf-8") as file:
		data = json.load(file)
	if not isinstance(data, dict):
		raise ValueError("config.json debe ser un objeto JSON")
	return data


def _write_item_config(path: Path, data: dict[str, Any]) -> None:
	with open(path, "w", encoding="utf-8") as file:
		json.dump(data, file, indent=2, ensure_ascii=False)


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


def _build_editor_embed(item: EditableStoreItem) -> discord.Embed:
	data = item.item_data
	name = str(data.get("nombre") or item.item_key)
	rareza = str(data.get("rareza") or "common")
	base_price = float(data.get("base_price", 0.0) or 0.0)
	ip_percent = float(data.get("ip_percent", data.get("ip%", 0.0)) or 0.0)
	cooldown = int(data.get("cooldown", 0) or 0)
	global_cd = int(data.get("global_cooldown", 0) or 0)
	raw_quantity = data.get("quantity", -1)
	quantity = int(raw_quantity) if raw_quantity is not None else -1
	quantity_text = "infinito" if quantity == -1 else str(max(0, quantity))
	description = str(data.get("descripcion") or "")

	embed = discord.Embed(
		title=f"Editor Store `ID:{item.internal_id}`",
		description=f"Item: `{item.item_key}`",
		color=discord.Color.blurple(),
	)
	embed.add_field(name="Nombre", value=name[:1024] or "-", inline=False)
	embed.add_field(name="Rareza", value=rareza, inline=True)
	embed.add_field(name="Precio Base", value=f"{base_price}", inline=True)
	embed.add_field(name="ip%", value=f"{ip_percent}", inline=True)
	embed.add_field(name="Cooldown", value=_format_seconds(cooldown), inline=True)
	embed.add_field(name="Cooldown Global", value=_format_seconds(global_cd), inline=True)
	embed.add_field(name="Cantidad", value=quantity_text, inline=True)
	embed.add_field(name="Descripcion", value=(description[:1024] or "-"), inline=False)
	embed.set_footer(text="Cada cambio se guarda en config.json y sincroniza este item en el foro")
	return embed


class _FieldModal(discord.ui.Modal):
	def __init__(
		self,
		*,
		title: str,
		label: str,
		placeholder: str,
		default_value: str,
		max_length: int,
		parser: Callable[[str], Any],
		on_parsed: Callable[[Any], Any],
		is_long: bool = False,
	):
		super().__init__(title=title)
		self._parser = parser
		self._on_parsed = on_parsed
		self.input = discord.ui.TextInput(
			label=label,
			placeholder=placeholder,
			default=default_value,
			max_length=max_length,
			style=discord.TextStyle.paragraph if is_long else discord.TextStyle.short,
			required=True,
		)
		self.add_item(self.input)

	async def on_submit(self, interaction: discord.Interaction) -> None:
		# Acknowledge modal immediately to avoid timeout while saving/syncing.
		await interaction.response.defer(ephemeral=True, thinking=False)
		try:
			parsed = self._parser(str(self.input.value))
			await self._on_parsed(parsed)
		except Exception as exc:
			await interaction.followup.send(f"❌ {exc}", ephemeral=True)
			return


class StoreItemEditorView(discord.ui.View):
	def __init__(self, *, bot: commands.Bot, guild_id: int, item_id: str):
		super().__init__(timeout=900)
		self.bot = bot
		self.guild_id = int(guild_id)
		self.item_id = str(item_id)

	def _reload(self) -> EditableStoreItem:
		item = _load_item_by_internal_id(self.item_id)
		if item is None:
			raise RuntimeError(f"No se encontró item con ID `{self.item_id}`")
		return item

	async def _save_and_sync(
		self,
		*,
		interaction: discord.Interaction,
		mutate: Callable[[dict[str, Any]], None],
		ok_message: str,
	) -> None:
		item = self._reload()
		cfg = _read_item_config(item.config_path)
		mutate(cfg)
		_write_item_config(item.config_path, cfg)

		# Refrescar caché y sincronizar solo el item editado.
		store_manager.refresh_store_items()
		sync_result = await DiscordStorePackager.publish_store_for_guild(
			bot=self.bot,
			guild_id=self.guild_id,
			force_republish=False,
			item_id=item.internal_id,
		)

		fresh = self._reload()
		embed = _build_editor_embed(fresh)
		sync_line = (
			f"Sync -> publicados: {sync_result.get('published', 0)}, "
			f"actualizados: {sync_result.get('updated', 0)}, "
			f"fallidos: {sync_result.get('failed', 0)}"
		)
		embed.add_field(name="Ultimo cambio", value=f"{ok_message}\n{sync_line}", inline=False)

		# For ephemeral responses, edit_original_response is the reliable endpoint.
		try:
			await interaction.edit_original_response(embed=embed, view=self)
		except discord.NotFound:
			# Message might no longer exist (dismissed/expired). Changes were already saved.
			pass
		except discord.HTTPException:
			# Avoid surfacing noisy transport errors after successful save/sync.
			pass

	async def _open_modal(self, interaction: discord.Interaction, modal: discord.ui.Modal) -> None:
		await interaction.response.send_modal(modal)

	@discord.ui.button(label="Nombre", style=discord.ButtonStyle.primary, row=0)
	async def edit_name(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		item = self._reload()

		async def _apply(parsed: Any) -> None:
			await self._save_and_sync(
				interaction=interaction,
				mutate=lambda cfg: cfg.__setitem__("nombre", str(parsed).strip()),
				ok_message="Nombre actualizado",
			)

		modal = _FieldModal(
			title="Editar nombre",
			label="Nombre",
			placeholder="Nuevo nombre",
			default_value=str(item.item_data.get("nombre") or ""),
			max_length=120,
			parser=lambda raw: raw.strip() or (_ for _ in ()).throw(ValueError("El nombre no puede estar vacío")),
			on_parsed=_apply,
		)
		await self._open_modal(interaction, modal)

	@discord.ui.button(label="Rareza", style=discord.ButtonStyle.primary, row=0)
	async def edit_rarity(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		item = self._reload()

		def _parse(raw: str) -> str:
			value = raw.strip().lower()
			allowed = {"common", "uncommon", "rare", "epic", "legendary"}
			if value not in allowed:
				raise ValueError("Rareza inválida. Usa: common, uncommon, rare, epic, legendary")
			return value

		async def _apply(parsed: Any) -> None:
			await self._save_and_sync(
				interaction=interaction,
				mutate=lambda cfg: cfg.__setitem__("rareza", str(parsed)),
				ok_message="Rareza actualizada",
			)

		modal = _FieldModal(
			title="Editar rareza",
			label="Rareza",
			placeholder="common | uncommon | rare | epic | legendary",
			default_value=str(item.item_data.get("rareza") or "common"),
			max_length=20,
			parser=_parse,
			on_parsed=_apply,
		)
		await self._open_modal(interaction, modal)

	@discord.ui.button(label="Precio Base", style=discord.ButtonStyle.primary, row=0)
	async def edit_base_price(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		item = self._reload()

		def _parse(raw: str) -> float:
			value = float(raw.strip())
			if value < 0:
				raise ValueError("El precio base no puede ser negativo")
			return round(value, 2)

		async def _apply(parsed: Any) -> None:
			await self._save_and_sync(
				interaction=interaction,
				mutate=lambda cfg: cfg.__setitem__("base_price", float(parsed)),
				ok_message="Precio base actualizado",
			)

		modal = _FieldModal(
			title="Editar precio base",
			label="Precio base",
			placeholder="Ej: 50",
			default_value=str(item.item_data.get("base_price") or 0),
			max_length=32,
			parser=_parse,
			on_parsed=_apply,
		)
		await self._open_modal(interaction, modal)

	@discord.ui.button(label="Cooldown", style=discord.ButtonStyle.secondary, row=1)
	async def edit_cooldown(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		item = self._reload()

		def _parse(raw: str) -> int:
			value = int(raw.strip())
			if value < 0:
				raise ValueError("El cooldown no puede ser negativo")
			return value

		async def _apply(parsed: Any) -> None:
			await self._save_and_sync(
				interaction=interaction,
				mutate=lambda cfg: cfg.__setitem__("cooldown", int(parsed)),
				ok_message="Cooldown actualizado",
			)

		modal = _FieldModal(
			title="Editar cooldown",
			label="Cooldown (segundos)",
			placeholder="Ej: 120",
			default_value=str(item.item_data.get("cooldown") or 0),
			max_length=16,
			parser=_parse,
			on_parsed=_apply,
		)
		await self._open_modal(interaction, modal)

	@discord.ui.button(label="Cooldown Global", style=discord.ButtonStyle.secondary, row=1)
	async def edit_global_cooldown(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		item = self._reload()

		def _parse(raw: str) -> int:
			value = int(raw.strip())
			if value < 0:
				raise ValueError("El cooldown global no puede ser negativo")
			return value

		async def _apply(parsed: Any) -> None:
			await self._save_and_sync(
				interaction=interaction,
				mutate=lambda cfg: cfg.__setitem__("global_cooldown", int(parsed)),
				ok_message="Cooldown global actualizado",
			)

		modal = _FieldModal(
			title="Editar cooldown global",
			label="Cooldown global (segundos)",
			placeholder="Ej: 300",
			default_value=str(item.item_data.get("global_cooldown") or 0),
			max_length=16,
			parser=_parse,
			on_parsed=_apply,
		)
		await self._open_modal(interaction, modal)

	@discord.ui.button(label="ip%", style=discord.ButtonStyle.secondary, row=1)
	async def edit_ip_percent(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		item = self._reload()

		def _parse(raw: str) -> float:
			value = float(raw.strip().replace("%", ""))
			if value < 0:
				raise ValueError("ip% no puede ser negativo")
			return round(value, 4)

		async def _apply(parsed: Any) -> None:
			def _mutate(cfg: dict[str, Any]) -> None:
				cfg["ip%"] = float(parsed)
				cfg["ip_percent"] = float(parsed)

			await self._save_and_sync(
				interaction=interaction,
				mutate=_mutate,
				ok_message="ip% actualizado",
			)

		modal = _FieldModal(
			title="Editar ip%",
			label="ip%",
			placeholder="Ej: 2.5",
			default_value=str(item.item_data.get("ip_percent", item.item_data.get("ip%", 0.0)) or 0.0),
			max_length=24,
			parser=_parse,
			on_parsed=_apply,
		)
		await self._open_modal(interaction, modal)

	@discord.ui.button(label="Cantidad", style=discord.ButtonStyle.secondary, row=1)
	async def edit_quantity(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		item = self._reload()

		def _parse(raw: str) -> int:
			value = int(raw.strip())
			if value < -1:
				raise ValueError("Cantidad inválida. Usa -1 (infinito) o 0..N")
			return value

		async def _apply(parsed: Any) -> None:
			await self._save_and_sync(
				interaction=interaction,
				mutate=lambda cfg: cfg.__setitem__("quantity", int(parsed)),
				ok_message="Cantidad actualizada",
			)

		modal = _FieldModal(
			title="Editar cantidad",
			label="Cantidad (-1 = infinito)",
			placeholder="Ej: 7, 0 o -1",
			default_value=(
				str(item.item_data.get("quantity"))
				if item.item_data.get("quantity") is not None
				else "-1"
			),
			max_length=16,
			parser=_parse,
			on_parsed=_apply,
		)
		await self._open_modal(interaction, modal)

	@discord.ui.button(label="Descripcion", style=discord.ButtonStyle.secondary, row=2)
	async def edit_description(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		item = self._reload()

		async def _apply(parsed: Any) -> None:
			await self._save_and_sync(
				interaction=interaction,
				mutate=lambda cfg: cfg.__setitem__("descripcion", str(parsed)),
				ok_message="Descripcion actualizada",
			)

		modal = _FieldModal(
			title="Editar descripcion",
			label="Descripcion",
			placeholder="Descripcion del item",
			default_value=str(item.item_data.get("descripcion") or ""),
			max_length=1200,
			parser=lambda raw: raw.strip(),
			on_parsed=_apply,
			is_long=True,
		)
		await self._open_modal(interaction, modal)

	@discord.ui.button(label="Refrescar", style=discord.ButtonStyle.success, row=2)
	async def refresh_editor(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		item = self._reload()
		embed = _build_editor_embed(item)
		await interaction.response.edit_message(embed=embed, view=self)

	@discord.ui.button(label="Cerrar", style=discord.ButtonStyle.danger, row=2)
	async def close_editor(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
		for child in self.children:
			child.disabled = True
		await interaction.response.edit_message(view=self)


def setup_store_item_editor_command(bot: commands.Bot, admin_store_group: app_commands.Group) -> None:
	"""Agrega /admin_store editor al grupo existente de tienda."""

	@admin_store_group.command(name="editor", description="Abre editor administrativo de item por ID interno")
	@app_commands.describe(item_id="ID interno del item (ej: S1)")
	async def admin_store_editor(interaction: discord.Interaction, item_id: str) -> None:
		if interaction.guild is None:
			await interaction.response.send_message(
				"Este comando solo puede ejecutarse dentro de un servidor.",
				ephemeral=True,
			)
			return

		if not interaction.user.guild_permissions.administrator:
			embed = discord.Embed(
				title="Permiso denegado",
				description="Solo administradores pueden usar /admin_store editor.",
				color=discord.Color.red(),
			)
			await interaction.response.send_message(embed=embed, ephemeral=True)
			return

		item = _load_item_by_internal_id(item_id)
		if item is None:
			await interaction.response.send_message(
				f"No se encontro item con ID `{item_id}`.",
				ephemeral=True,
			)
			return

		view = StoreItemEditorView(bot=bot, guild_id=interaction.guild.id, item_id=item.internal_id)
		embed = _build_editor_embed(item)
		await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


__all__ = ["setup_store_item_editor_command"]

