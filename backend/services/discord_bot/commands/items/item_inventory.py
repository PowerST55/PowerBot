"""
Comandos para gestionar y ver inventarios en PowerBot Discord.
/inventory - Ver tu inventario o el de alguien más
/inventory @user - Ver inventario de un usuario específico
/inventory <ID> - Ver inventario por ID universal
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
from pathlib import Path

from backend.managers import inventory_manager, user_manager, items_manager
from backend.services.discord_bot.config.economy import get_economy_config


def setup_inventory_commands(bot: commands.Bot):
    """Registra comandos de inventario"""
    
    @bot.tree.command(
        name="inventory",
        description="Ver tu inventario o el de alguien más"
    )
    @app_commands.describe(
        usuario="Usuario Discord (@user) o ID universal para ver inventario"
    )
    async def inventory_command(
        interaction: discord.Interaction,
        usuario: Optional[str] = None
    ):
        """
        Muestra el inventario de un usuario.
        - Sin parámetro: Tu inventario
        - @user: Inventario de ese usuario de Discord
        - ID número: Inventario por ID universal
        """
        await interaction.response.defer()
        
        try:
            target_user_id = None
            target_discord_profile = None
            
            # Determinar qué usuario ver
            if usuario is None:
                # Self
                discord_id = str(interaction.user.id)
                discord_profile = user_manager.get_discord_profile_by_discord_id(discord_id)
                
                if not discord_profile:
                    embed = discord.Embed(
                        title="❌ Usuario no registrado",
                        description=f"Primero necesitas ejecutar un comando para registrarte.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                target_user_id = discord_profile.user_id
                target_discord_profile = discord_profile
                
            elif usuario.startswith("<@") and usuario.endswith(">"):
                # Mención de usuario Discord
                discord_id_str = usuario.strip("<@!>")
                discord_profile = user_manager.get_discord_profile_by_discord_id(discord_id_str)
                
                if not discord_profile:
                    embed = discord.Embed(
                        title="❌ Usuario no encontrado",
                        description=f"Ese usuario no está registrado en PowerBot.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                target_user_id = discord_profile.user_id
                target_discord_profile = discord_profile
                
            else:
                # ID universal
                try:
                    target_user_id = int(usuario)
                    user = user_manager.get_user_by_id(target_user_id)
                    if not user:
                        embed = discord.Embed(
                            title="❌ Usuario no encontrado",
                            description=f"No existe usuario con ID universal: {target_user_id}",
                            color=discord.Color.red()
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                        return
                except ValueError:
                    embed = discord.Embed(
                        title="❌ Parámetro inválido",
                        description="Usa: `/inventory` (self), `/inventory @user` o `/inventory <ID>",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
            
            # Obtener inventario
            inventory = inventory_manager.get_user_inventory(target_user_id)
            
            if not inventory:
                embed = discord.Embed(
                    title="📦 Inventario Vacío",
                    description="Este usuario no tiene items en su inventario.",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Ordenar por mejores stats primero
            inventory = _sort_inventory_by_stats(inventory)

            # Obtener información del usuario
            user = user_manager.get_user_by_id(target_user_id)
            user_display_name = user.username if user else f"Usuario {target_user_id}"

            currency_symbol = ""
            try:
                if interaction.guild is not None:
                    currency_symbol = get_economy_config(interaction.guild.id).get_currency_symbol()
            except Exception:
                currency_symbol = ""
            
            # Crear embeds (con paginación si es necesario)
            pages = _create_inventory_embeds(
                inventory=inventory,
                user_id=target_user_id,
                user_display_name=user_display_name,
                discord_profile=target_discord_profile,
                currency_symbol=currency_symbol,
            )
            
            if len(pages) == 1:
                payload = _build_page_payload(pages[0], for_edit=False)
                await interaction.followup.send(**payload)
            else:
                # Crear botones de navegación si hay múltiples embeds
                view = _create_pagination_view(pages, owner_id=interaction.user.id)
                payload = _build_page_payload(pages[0], view=view, for_edit=False)
                await interaction.followup.send(**payload)
        
        except Exception as e:
            print(f"❌ Error en inventario: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description=f"Ocurrió un error: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


def _create_inventory_embeds(
    inventory: List[dict],
    user_id: int,
    user_display_name: str,
    discord_profile = None,
    currency_symbol: str = "",
) -> List[dict]:
    """
    Crea embeds para mostrar el inventario con paginación por item.
    
    Args:
        inventory: Lista de items del inventario
        user_id: ID del usuario
        user_display_name: Nombre del usuario
        discord_profile: Perfil Discord del usuario (opcional)
        currency_symbol: Símbolo de moneda configurado para mantenimiento
    Returns:
        List[dict]: Lista de paginas con embed y metadata de imagen
    """
    pages = []
    total_pages = len(inventory)

    for page, item in enumerate(inventory):
        rarity_emoji = {
            "common": "⚪",
            "uncommon": "🟢",
            "rare": "🔵",
            "epic": "🟣",
            "legendary": "🟡"
        }.get(item.get("rareza", "common"), "⚪")

        rarity_text = {
            "common": "comun",
            "uncommon": "poco comun",
            "rare": "raro",
            "epic": "epico",
            "legendary": "legendario",
        }.get(item.get("rareza", "common"), str(item.get("rareza", "common")))

        title = f"{rarity_emoji} {item['nombre']} ({page + 1}/{total_pages})"

        embed = discord.Embed(
            title=title,
            description=(
                f"**Inventario de:** {_format_inventory_owner(user_display_name, user_id, discord_profile)}\n"
                f"**ID Item:** `{item['item_id']}`\n"
                f"**Cantidad:** x{item['quantity']}\n"
                f"**Rareza:** {rarity_text}"
            ),
            color=_get_rarity_color_for_item(item.get("rareza", "common"))
        )

        image_info = _resolve_item_image(item)
        if image_info["embed_url"]:
            embed.set_image(url=image_info["embed_url"])

        # Stats del item
        stats_text = _format_item_stats(item, currency_symbol=currency_symbol)
        embed.add_field(
            name="⚙️ Stats",
            value=stats_text,
            inline=False
        )

        # Footer con información
        if discord_profile:
            discord_username = discord_profile.discord_username or "Desconocido"
            footer_text = f"🎮 {discord_username} • ID: {user_id}"
        else:
            footer_text = f"ID Universal: {user_id}"

        embed.set_footer(text=footer_text)

        pages.append({
            "embed": embed,
            "image_path": image_info["path"],
            "image_name": image_info["name"]
        })
    
    return pages


def _create_pagination_view(pages: List[dict], owner_id: int) -> discord.ui.View:
    """
    Crea controles de paginación para múltiples embeds.
    
    Args:
        pages: Lista de paginas para paginar
        owner_id: ID del usuario que puede interactuar
        
    Returns:
        discord.ui.View: Vista con botones de navegación
    """
    
    class PaginationView(discord.ui.View):
        def __init__(self, pages_list, owner_id_value: int):
            super().__init__(timeout=300)
            self.pages = pages_list
            self.current_page = 0
            self.owner_id = owner_id_value

        async def _reject_interaction(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message(
                    "Solo el usuario que envio el comando puede usar estos botones.",
                    ephemeral=True
                )
                return True
            return False
        
        @discord.ui.button(label="◄", style=discord.ButtonStyle.blurple)
        async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if await self._reject_interaction(interaction):
                return
            if self.current_page == 0:
                self.current_page = len(self.pages) - 1
            else:
                self.current_page -= 1
            payload = _build_page_payload(self.pages[self.current_page], view=self, for_edit=True)
            await interaction.response.edit_message(**payload)
        
        @discord.ui.button(label="►", style=discord.ButtonStyle.blurple)
        async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if await self._reject_interaction(interaction):
                return
            if self.current_page == len(self.pages) - 1:
                self.current_page = 0
            else:
                self.current_page += 1
            payload = _build_page_payload(self.pages[self.current_page], view=self, for_edit=True)
            await interaction.response.edit_message(**payload)
        
        @discord.ui.button(label="❌", style=discord.ButtonStyle.red)
        async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if await self._reject_interaction(interaction):
                return
            await interaction.response.defer()
            await interaction.delete_original_response()
    
    return PaginationView(pages, owner_id)


def _build_page_payload(page: dict, view: Optional[discord.ui.View] = None, for_edit: bool = False) -> dict:
    payload = {
        "embed": page["embed"]
    }

    if view is not None:
        payload["view"] = view

    image_path = page.get("image_path")
    image_name = page.get("image_name")
    if image_path and image_name:
        file_obj = discord.File(image_path, filename=image_name)
        if for_edit:
            payload["attachments"] = [file_obj]
        else:
            payload["files"] = [file_obj]
    elif for_edit:
        payload["attachments"] = []

    return payload


def _resolve_item_image(item: dict) -> dict:
    image_url = item.get("imagen_local")
    if not image_url:
        return {"embed_url": None, "path": None, "name": None}

    if _is_http_url(image_url):
        return {"embed_url": image_url, "path": None, "name": None}

    path = _resolve_local_image_path(image_url)
    if not path:
        return {"embed_url": None, "path": None, "name": None}

    filename = path.name
    return {
        "embed_url": f"attachment://{filename}",
        "path": str(path),
        "name": filename
    }


def _is_http_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _resolve_local_image_path(image_url: str) -> Optional[Path]:
    raw_path = Path(image_url)
    if raw_path.is_absolute() and raw_path.is_file():
        return raw_path

    if raw_path.is_file():
        return raw_path

    project_root = Path(__file__).resolve().parents[6]
    candidate = project_root / raw_path
    if candidate.is_file():
        return candidate

    backend_root = Path(__file__).resolve().parents[5]
    candidate = backend_root / raw_path
    if candidate.is_file():
        return candidate

    return None


def _format_item_stats(item: dict, currency_symbol: str = "") -> str:
    stats_parts = []
    if item.get("ataque", 0) > 0:
        stats_parts.append(f"⚔️ **Ataque:** {item['ataque']}")
    if item.get("defensa", 0) > 0:
        stats_parts.append(f"🛡️ **Defensa:** {item['defensa']}")
    if item.get("vida", 0) > 0:
        stats_parts.append(f"❤️ **Vida:** {item['vida']}")
    if item.get("armadura", 0) > 0:
        stats_parts.append(f"🔗 **Armadura:** {item['armadura']}")
    if item.get("mantenimiento", 0) > 0:
        symbol_suffix = f" {currency_symbol}" if currency_symbol else ""
        stats_parts.append(f"🔧 **Mantenimiento:** {item['mantenimiento']}{symbol_suffix}")

    return "\n".join(stats_parts) if stats_parts else "Sin stats"


def _format_inventory_owner(user_display_name: str, user_id: int, discord_profile = None) -> str:
    """Construye la línea de propietario: `ID:X` @usuario (si existe mención)."""
    if discord_profile is not None:
        discord_id = getattr(discord_profile, "discord_id", None)
        if discord_id:
            return f"`ID:{user_id}` <@{discord_id}>"
    return f"`ID:{user_id}` {user_display_name}"


def _get_rarity_color_for_item(rareza: str) -> discord.Color:
    """
    Aplica la misma escala visual usada en mina.py, mapeada a rareza.

    common -> dark_grey
    uncommon -> purple
    rare -> blue
    epic -> gold
    legendary -> green
    """
    color_map = {
        "common": discord.Color.dark_grey(),
        "uncommon": discord.Color.purple(),
        "rare": discord.Color.blue(),
        "epic": discord.Color.gold(),
        "legendary": discord.Color.green(),
    }
    return color_map.get(str(rareza).lower(), discord.Color.dark_grey())


def _sort_inventory_by_stats(inventory: List[dict]) -> List[dict]:
    def stats_total(item: dict) -> int:
        return (
            item.get("ataque", 0)
            + item.get("defensa", 0)
            + item.get("vida", 0)
            + item.get("armadura", 0)
            + item.get("mantenimiento", 0)
        )

    return sorted(inventory, key=stats_total, reverse=True)
