"""
Admin Item Commands para PowerBot.
Comandos solo para moderadores:
- /item_give <@user o ID> <item_id> <cantidad>: Dar items a un usuario
- /remove_item <@user o ID> <item_id> <cantidad>: Remover items de un usuario
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from backend.managers import inventory_manager, user_manager, items_manager


# ============================================================
# UTILIDADES
# ============================================================

def _is_moderator(interaction: discord.Interaction) -> bool:
    """Verifica si el usuario es moderador (admin en el servidor)"""
    if not interaction.user.guild_permissions.administrator:
        return False
    return True


def _parse_user_identifier(identifier: str, interaction: discord.Interaction) -> Optional[dict]:
    """
    Parsea un identificador de usuario (@mention o ID global).
    
    Args:
        identifier: String que puede ser mención o ID
        interaction: Contexto de Discord
        
    Returns:
        Dict con información del usuario o None
    """
    # Intentar parsear como ID entero
    try:
        user_id = int(identifier.replace("<@", "").replace(">", ""))
        user = user_manager.get_user_by_id(user_id)
        if user:
            return {
                "user_id": user.user_id,
                "username": user.username,
                "source": "universal_id"
            }
    except (ValueError, AttributeError):
        pass
    
    # Si tiene formato de mención, buscar en Discord
    if identifier.startswith("<@") and identifier.endswith(">"):
        try:
            # Extraer ID de Discord: <@123456789>
            discord_id = identifier.replace("<@", "").replace(">", "").replace("!", "")
            
            # Buscar perfil Discord
            discord_profile = user_manager.get_discord_profile_by_discord_id(discord_id)
            if discord_profile:
                user = user_manager.get_user_by_id(discord_profile.user_id)
                if user:
                    return {
                        "user_id": user.user_id,
                        "username": user.username,
                        "discord_username": discord_profile.discord_username,
                        "source": "discord_mention"
                    }
        except (ValueError, AttributeError):
            pass
    
    return None


async def _get_item_image_file(item_id: int) -> Optional[discord.File]:
    """Obtiene el archivo de imagen de un item si existe"""
    try:
        item = items_manager.get_item_by_id(item_id)
        if not item or not item.get("imagen_local"):
            return None
        
        image_path = items_manager.get_item_image_path(item_id)
        if image_path and image_path.exists():
            return discord.File(image_path, filename=f"item_{item_id}.png")
    except Exception as e:
        print(f"⚠️ Error cargando imagen: {e}")
    
    return None


# ============================================================
# COMANDOS
# ============================================================

def setup_admin_item_commands(bot: commands.Bot) -> None:
    """Registra los comandos de admin de items"""
    
    @bot.tree.command(name="item_give", description="Da items a un usuario (MODERADOR)")
    @app_commands.describe(
        usuario="Usuario (@mention o ID global)",
        item_id="ID del item a dar",
        cantidad="Cantidad de items (default: 1)"
    )
    async def item_give(
        interaction: discord.Interaction,
        usuario: str,
        item_id: int,
        cantidad: int = 1
    ):
        """Da items a un usuario - Solo para moderadores"""
        
        # Verificar permisos
        if not _is_moderator(interaction):
            embed = discord.Embed(
                title="❌ Permiso Denegado",
                description="Solo moderadores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Verificar cantidad
        if cantidad <= 0:
            embed = discord.Embed(
                title="❌ Error",
                description="La cantidad debe ser mayor a 0",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Mostrar que está procesando
        await interaction.response.defer()
        
        # Parsear usuario
        user_data = _parse_user_identifier(usuario, interaction)
        if not user_data:
            embed = discord.Embed(
                title="❌ Usuario No Encontrado",
                description=f"No se pudo encontrar el usuario: `{usuario}`\n\nUsa: `@usuario` o `ID_UNIVERSAL`",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Obtener info del item
        item = items_manager.get_item_by_id(item_id)
        if not item:
            embed = discord.Embed(
                title="❌ Item No Encontrado",
                description=f"El item con ID `{item_id}` no existe.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Agregar item al usuario
        result = inventory_manager.add_item_to_user(user_data["user_id"], item_id, cantidad)
        
        if not result["success"]:
            embed = discord.Embed(
                title="❌ Error",
                description=f"No se pudo agregar el item:\n{result['message']}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Crear embed de éxito
        rarity_emoji = {
            "common": "⚪",
            "uncommon": "🟢",
            "rare": "🔵",
            "epic": "🟣",
            "legendary": "🟡"
        }
        
        emoji = rarity_emoji.get(item["rareza"], "❓")
        
        embed = discord.Embed(
            title="✅ Item Entregado",
            description=f"Se entregaron items a **{user_data['username']}** (ID: {user_data['user_id']})",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="📦 Item",
            value=f"{emoji} **{item['nombre']}**\nRareza: `{item['rareza']}`",
            inline=False
        )
        
        embed.add_field(
            name="📊 Stats",
            value=f"ATK: `{item['ataque']}`\nDEF: `{item['defensa']}`\nHP: `{item['vida']}`",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Cantidad",
            value=f"`{cantidad}` items\nTotal en inv: `{result['total_quantity']}`",
            inline=True
        )
        
        embed.add_field(
            name="👤 Usuario",
            value=f"{user_data['username']}\nID: `{user_data['user_id']}`",
            inline=False
        )
        
        embed.add_field(
            name="👮 Moderador",
            value=interaction.user.mention,
            inline=True
        )
        
        embed.set_footer(text="PowerBot Item System")
        
        # Enviar imagen si existe
        image_file = await _get_item_image_file(item_id)
        if image_file:
            embed.set_thumbnail(url=f"attachment://{image_file.filename}")
            await interaction.followup.send(embed=embed, file=image_file)
        else:
            await interaction.followup.send(embed=embed)
    
    
    @bot.tree.command(name="remove_item", description="Remueve items de un usuario (MODERADOR)")
    @app_commands.describe(
        usuario="Usuario (@mention o ID global)",
        item_id="ID del item a remover",
        cantidad="Cantidad de items (default: 1)"
    )
    async def remove_item(
        interaction: discord.Interaction,
        usuario: str,
        item_id: int,
        cantidad: int = 1
    ):
        """Remueve items de un usuario - Solo para moderadores"""
        
        # Verificar permisos
        if not _is_moderator(interaction):
            embed = discord.Embed(
                title="❌ Permiso Denegado",
                description="Solo moderadores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Verificar cantidad
        if cantidad <= 0:
            embed = discord.Embed(
                title="❌ Error",
                description="La cantidad debe ser mayor a 0",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Mostrar que está procesando
        await interaction.response.defer()
        
        # Parsear usuario
        user_data = _parse_user_identifier(usuario, interaction)
        if not user_data:
            embed = discord.Embed(
                title="❌ Usuario No Encontrado",
                description=f"No se pudo encontrar el usuario: `{usuario}`\n\nUsa: `@usuario` o `ID_UNIVERSAL`",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Obtener info del item
        item = items_manager.get_item_by_id(item_id)
        if not item:
            embed = discord.Embed(
                title="❌ Item No Encontrado",
                description=f"El item con ID `{item_id}` no existe.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Remover item del usuario
        result = inventory_manager.remove_item_from_user(user_data["user_id"], item_id, cantidad)
        
        if not result["success"]:
            embed = discord.Embed(
                title="❌ Error",
                description=f"No se pudo remover el item:\n{result['message']}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Crear embed de éxito
        rarity_emoji = {
            "common": "⚪",
            "uncommon": "🟢",
            "rare": "🔵",
            "epic": "🟣",
            "legendary": "🟡"
        }
        
        emoji = rarity_emoji.get(item["rareza"], "❓")
        
        embed = discord.Embed(
            title="✅ Item Removido",
            description=f"Se removieron items de **{user_data['username']}** (ID: {user_data['user_id']})",
            color=discord.Color.orange()
        )
        
        embed.add_field(
            name="📦 Item",
            value=f"{emoji} **{item['nombre']}**\nRareza: `{item['rareza']}`",
            inline=False
        )
        
        embed.add_field(
            name="📊 Stats",
            value=f"ATK: `{item['ataque']}`\nDEF: `{item['defensa']}`\nHP: `{item['vida']}`",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Cantidad",
            value=f"`{cantidad}` items removidos\nRestante en inv: `{result['remaining_quantity']}`",
            inline=True
        )
        
        embed.add_field(
            name="👤 Usuario",
            value=f"{user_data['username']}\nID: `{user_data['user_id']}`",
            inline=False
        )
        
        embed.add_field(
            name="👮 Moderador",
            value=interaction.user.mention,
            inline=True
        )
        
        embed.set_footer(text="PowerBot Item System")
        
        # Enviar imagen si existe
        image_file = await _get_item_image_file(item_id)
        if image_file:
            embed.set_thumbnail(url=f"attachment://{image_file.filename}")
            await interaction.followup.send(embed=embed, file=image_file)
        else:
            await interaction.followup.send(embed=embed)
