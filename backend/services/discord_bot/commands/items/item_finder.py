"""
Comandos para gestionar y consultar items en PowerBot Discord.
/lista_de_items - Muestra todos los items disponibles
/item <id o name> - Muestra detalles de un item específico
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Tuple
from pathlib import Path
from backend.managers import items_manager


def setup_item_commands(bot: commands.Bot):
    """Registra comandos de items"""
    
    # ============================================================
    # COMANDO: /lista_de_items
    # ============================================================
    
    @bot.tree.command(
        name="lista_de_items",
        description="Muestra todos los items disponibles en PowerBot"
    )
    @app_commands.describe(
        source="Filtrar por origen (gacha/store) o mostrar todos"
    )
    async def lista_de_items(
        interaction: discord.Interaction,
        source: Optional[str] = None
    ):
        """Muestra una lista de todos los items disponibles con selector"""
        
        await interaction.response.defer()
        
        try:
            # Obtener items según el filtro
            if source and source.lower() in ["gacha", "store"]:
                all_items = items_manager.get_all_items(source=source.lower())
                source_text = f"Filtrando por: {source.upper()}"
            else:
                all_items = items_manager.get_all_items()
                source_text = "Mostrando todos los items"
            
            if not all_items:
                embed = discord.Embed(
                    title="❌ Sin items",
                    description="No hay items disponibles en el catálogo.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Crear opciones del select menu
            select_options = []
            for item in all_items[:25]:  # Discord limita a 25 opciones
                rarity_emoji = {
                    "common": "⚪",
                    "uncommon": "🟢",
                    "rare": "🔵",
                    "epic": "🟣",
                    "legendary": "🟡"
                }.get(item.get("rareza", "common"), "⚪")
                
                label = f"{rarity_emoji} {item['nombre']}"
                description = item['descripcion'][:50] + "..." if len(item['descripcion']) > 50 else item['descripcion']
                
                select_options.append(
                    discord.SelectOption(
                        label=label[:100],
                        value=str(item['item_id']),
                        description=description[:100]
                    )
                )
            
            # Crear embed principal
            embed = discord.Embed(
                title="📦 Lista de Items",
                description=f"{source_text}\n\nSelecciona un item para ver sus detalles.",
                color=discord.Color.blue()
            )
            
            # Agregar estadísticas
            stats = items_manager.get_items_stats()
            embed.add_field(
                name="📊 Estadísticas",
                value=f"Total: {stats['total_items']}\n"
                      f"Gacha: {stats['gacha_items']}\n"
                      f"Tienda: {stats['store_items']}",
                inline=False
            )
            
            # Crear select menu
            class ItemSelect(discord.ui.Select):
                def __init__(self, items_list):
                    self.items_list = {str(item['item_id']): item for item in items_list}
                    super().__init__(
                        placeholder="Selecciona un item...",
                        min_values=1,
                        max_values=1,
                        options=select_options
                    )
                
                async def callback(self, select_interaction: discord.Interaction):
                    item_id = int(self.values[0])
                    item = self.items_list.get(str(item_id))
                    
                    if not item:
                        await select_interaction.response.send_message(
                            "❌ Item no encontrado",
                            ephemeral=True
                        )
                        return
                    
                    # Mostrar detalles del item
                    embed = _create_item_embed(item)
                    image_file = _get_item_image_file(item)
                    
                    if image_file:
                        await select_interaction.response.send_message(
                            embed=embed,
                            file=image_file,
                            ephemeral=False
                        )
                    else:
                        await select_interaction.response.send_message(
                            embed=embed,
                            ephemeral=False
                        )
            
            class ItemView(discord.ui.View):
                def __init__(self, items_list):
                    super().__init__(timeout=300)
                    self.add_item(ItemSelect(items_list))
            
            # Enviar mensaje con select
            view = ItemView(all_items[:25])
            await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error al obtener items: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    
    # ============================================================
    # COMANDO: /item
    # ============================================================
    
    @bot.tree.command(
        name="item",
        description="Muestra detalles de un item específico"
    )
    @app_commands.describe(
        id_o_nombre="ID del item (número) o nombre para buscar"
    )
    async def item_command(
        interaction: discord.Interaction,
        id_o_nombre: Optional[str] = None
    ):
        """
        Muestra detalles de un item específico.
        Si no se proporciona ID o nombre, muestra selector de items.
        """
        
        await interaction.response.defer()
        
        try:
            # Si no proporciona búsqueda, mostrar selector
            if not id_o_nombre:
                all_items = items_manager.get_all_items()
                
                if not all_items:
                    embed = discord.Embed(
                        title="❌ Sin items",
                        description="No hay items disponibles en el catálogo.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                
                # Crear opciones del select menu
                select_options = []
                for item in all_items[:25]:
                    rarity_emoji = {
                        "common": "⚪",
                        "uncommon": "🟢",
                        "rare": "🔵",
                        "epic": "🟣",
                        "legendary": "🟡"
                    }.get(item.get("rareza", "common"), "⚪")
                    
                    label = f"{rarity_emoji} {item['nombre']}"
                    description = item['descripcion'][:50] + "..." if len(item['descripcion']) > 50 else item['descripcion']
                    
                    select_options.append(
                        discord.SelectOption(
                            label=label[:100],
                            value=str(item['item_id']),
                            description=description[:100]
                        )
                    )
                
                # Crear embed con instrucciones
                embed = discord.Embed(
                    title="🔍 Buscar o Seleccionar Item",
                    description="**Usa uno de estos métodos:**\n\n"
                                "`/item <ID>`\n"
                                "Ej: `/item 1`\n\n"
                                "`/item <nombre>`\n"
                                "Ej: `/item poción`\n\n"
                                "`/item <key>`\n"
                                "Ej: `/item sword_dragon_001`\n\n"
                                "O selecciona del menú de abajo:",
                    color=discord.Color.blue()
                )
                
                # Estadísticas
                stats = items_manager.get_items_stats()
                embed.add_field(
                    name="📊 Total de items",
                    value=f"🎲 Gacha: {stats['gacha_items']}\n"
                          f"🏪 Tienda: {stats['store_items']}\n"
                          f"📦 Total: {stats['total_items']}",
                    inline=False
                )
                
                # Crear select
                class ItemSelect(discord.ui.Select):
                    def __init__(self, items_list):
                        self.items_list = {str(item['item_id']): item for item in items_list}
                        super().__init__(
                            placeholder="Selecciona un item...",
                            min_values=1,
                            max_values=1,
                            options=select_options
                        )
                    
                    async def callback(self, select_interaction: discord.Interaction):
                        item_id = int(self.values[0])
                        item = self.items_list.get(str(item_id))
                        
                        if not item:
                            await select_interaction.response.send_message(
                                "❌ Item no encontrado",
                                ephemeral=True
                            )
                            return
                        
                        embed = _create_item_embed(item)
                        image_file = _get_item_image_file(item)
                        
                        if image_file:
                            await select_interaction.response.send_message(
                                embed=embed,
                                file=image_file,
                                ephemeral=False
                            )
                        else:
                            await select_interaction.response.send_message(
                                embed=embed,
                                ephemeral=False
                            )
                
                class ItemView(discord.ui.View):
                    def __init__(self, items_list):
                        super().__init__(timeout=300)
                        self.add_item(ItemSelect(items_list))
                
                view = ItemView(all_items[:25])
                await interaction.followup.send(embed=embed, view=view)
                return
            
            # Intentar parsear como ID
            item = None
            try:
                item_id = int(id_o_nombre)
                item = items_manager.get_item_by_id(item_id)
            except ValueError:
                pass
            
            # Si no encontró por ID, buscar por nombre o key
            if not item:
                # Primero intentar por key exacto
                item = items_manager.get_item_by_key(id_o_nombre)
                
                # Si no, buscar entre todos los items
                if not item:
                    all_items = items_manager.get_all_items()
                    search_lower = id_o_nombre.lower()
                    
                    # Buscar coincidencias exactas primero
                    matches = [
                        i for i in all_items 
                        if search_lower == i['nombre'].lower() or search_lower == i['item_key'].lower()
                    ]
                    
                    if not matches:
                        # Buscar coincidencias parciales
                        matches = [
                            i for i in all_items 
                            if search_lower in i['nombre'].lower() or search_lower in i['item_key'].lower()
                        ]
                    
                    if matches:
                        # Si hay una sola coincidencia, mostrarla
                        if len(matches) == 1:
                            item = matches[0]
                        else:
                            # Si hay múltiples, mostrar selector
                            select_options = []
                            for m in matches[:25]:
                                rarity_emoji = {
                                    "common": "⚪",
                                    "uncommon": "🟢",
                                    "rare": "🔵",
                                    "epic": "🟣",
                                    "legendary": "🟡"
                                }.get(m.get("rareza", "common"), "⚪")
                                
                                label = f"{rarity_emoji} {m['nombre']}"
                                select_options.append(
                                    discord.SelectOption(
                                        label=label[:100],
                                        value=str(m['item_id']),
                                        description=m['descripcion'][:100]
                                    )
                                )
                            
                            embed = discord.Embed(
                                title="🔍 Múltiples Resultados",
                                description=f"Se encontraron {len(matches)} items. Selecciona uno:",
                                color=discord.Color.blue()
                            )
                            
                            class ItemSelect(discord.ui.Select):
                                def __init__(self, items_list):
                                    self.items_list = {str(item['item_id']): item for item in items_list}
                                    super().__init__(
                                        placeholder="Selecciona un item...",
                                        min_values=1,
                                        max_values=1,
                                        options=select_options
                                    )
                                
                                async def callback(self, select_interaction: discord.Interaction):
                                    item_id = int(self.values[0])
                                    item = self.items_list.get(str(item_id))
                                    
                                    if not item:
                                        await select_interaction.response.send_message(
                                            "❌ Item no encontrado",
                                            ephemeral=True
                                        )
                                        return
                                    
                                    embed = _create_item_embed(item)
                                    image_file = _get_item_image_file(item)
                                    
                                    if image_file:
                                        await select_interaction.response.send_message(
                                            embed=embed,
                                            file=image_file,
                                            ephemeral=False
                                        )
                                    else:
                                        await select_interaction.response.send_message(
                                            embed=embed,
                                            ephemeral=False
                                        )
                            
                            class ItemView(discord.ui.View):
                                def __init__(self, items_list):
                                    super().__init__(timeout=300)
                                    self.add_item(ItemSelect(items_list))
                            
                            view = ItemView(matches[:25])
                            await interaction.followup.send(embed=embed, view=view)
                            return
            
            # Si encontró el item, mostrarlo
            if item:
                embed = _create_item_embed(item)
                image_file = _get_item_image_file(item)
                
                if image_file:
                    await interaction.followup.send(embed=embed, file=image_file)
                else:
                    await interaction.followup.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ Item no encontrado",
                    description=f"No se encontró el item: **{id_o_nombre}**\n"
                                "Usa `/lista_de_items` para ver todos los items disponibles.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error al buscar item: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


def _create_item_embed(item: dict) -> discord.Embed:
    """
    Crea un embed decorativo con los detalles del item.
    
    Args:
        item: Dict del item con todos sus datos
        
    Returns:
        discord.Embed con el item formateado
    """
    
    # Emojis por rareza
    rarity_emoji = {
        "common": "⚪",
        "uncommon": "🟢",
        "rare": "🔵",
        "epic": "🟣",
        "legendary": "🟡"
    }.get(item.get("rareza", "common"), "⚪")
    
    # Colores por rareza
    rarity_color = {
        "common": discord.Color.greyple(),
        "uncommon": discord.Color.green(),
        "rare": discord.Color.blue(),
        "epic": discord.Color.purple(),
        "legendary": discord.Color.gold()
    }.get(item.get("rareza", "common"), discord.Color.greyple())
    
    # Emoji por source
    source_emoji = "🎲" if item.get("source") == "gacha" else "🏪"
    
    # Crear embed
    embed = discord.Embed(
        title=f"{rarity_emoji} {item['nombre']}",
        description=item['descripcion'],
        color=rarity_color
    )
    
    # Información básica
    embed.add_field(
        name="ℹ️ Información",
        value=f"**ID:** `{item['item_id']}`\n"
              f"**Key:** `{item['item_key']}`\n"
              f"**Rareza:** {rarity_emoji} {item['rareza'].capitalize()}\n"
              f"**Origen:** {source_emoji} {'Gacha' if item.get('source') == 'gacha' else 'Tienda'}",
        inline=False
    )
    
    # Stats
    stats_text = (
        f"⚔️ **Ataque:** {item['ataque']}\n"
        f"🛡️ **Defensa:** {item['defensa']}\n"
        f"❤️ **Vida:** {item['vida']}\n"
        f"🔗 **Armadura:** {item['armadura']}\n"
        f"🔧 **Mantenimiento:** {item['mantenimiento']}"
    )
    
    embed.add_field(
        name="⚙️ Stats",
        value=stats_text,
        inline=False
    )
    
    # Agregar imagen si existe
    if item.get("imagen_local"):
        PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent
        image_path = PROJECT_ROOT / item['imagen_local']
        
        if image_path.exists():
            # Usar attachment:// para referenciar la imagen adjunta
            embed.set_image(url="attachment://item_image.png")
    
    # Footer
    embed.set_footer(
        text=f"PowerBot • ID: {item['item_id']}",
        icon_url="https://cdn.discordapp.com/emojis/1234567890.png"
    )
    
    return embed


def _get_item_image_file(item: dict) -> Optional[discord.File]:
    """
    Obtiene el archivo de imagen de un item si existe.
    
    Args:
        item: Dict del item
        
    Returns:
        discord.File si existe, None en caso contrario
    """
    if not item.get("imagen_local"):
        return None
    
    try:
        PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent
        image_path = PROJECT_ROOT / item['imagen_local']
        
        if image_path.exists():
            # Retornar como discord.File con nombre genérico
            return discord.File(str(image_path), filename="item_image.png")
    except Exception as e:
        print(f"⚠️ Error cargando imagen: {e}")
    
    return None
