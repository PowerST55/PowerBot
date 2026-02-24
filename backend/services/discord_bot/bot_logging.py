"""
Sistema de logging centralizado para PowerBot Discord.
Envía logs con embeds al canal de logs configurado.

Uso:
    from backend.services.discord_bot.bot_logging import log_info, log_error, log_warning
    
    await log_info(bot, guild_id, "Usuario conectado", "Usuario123 inició sesión")
    await log_error(bot, guild_id, "Error de base de datos", str(error))
"""
import discord
from discord.ext import commands
from typing import Optional
from datetime import datetime
from backend.services.discord_bot.config import get_channels_config


class LogType:
    """Tipos de logs disponibles"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    MODERATION = "moderation"
    ECONOMY = "economy"
    COMMAND = "command"


class LogColor:
    """Colores para cada tipo de log"""
    INFO = discord.Color.blue()
    SUCCESS = discord.Color.green()
    WARNING = discord.Color.gold()
    ERROR = discord.Color.red()
    MODERATION = discord.Color.orange()
    ECONOMY = discord.Color.purple()
    COMMAND = discord.Color.teal()


class LogEmoji:
    """Emojis para cada tipo de log"""
    INFO = "ℹ️"
    SUCCESS = "✅"
    WARNING = "⚠️"
    ERROR = "❌"
    MODERATION = "🔨"
    ECONOMY = "💰"
    COMMAND = "⚙️"


async def send_log(
    bot: commands.Bot,
    guild_id: int,
    log_type: str,
    title: str,
    description: str,
    fields: Optional[dict] = None,
    user: Optional[discord.User] = None,
    channel: Optional[discord.TextChannel] = None
) -> bool:
    """
    Envía un log al canal de logs configurado.
    
    Args:
        bot: Instancia del bot
        guild_id: ID del servidor
        log_type: Tipo de log (usar LogType.*)
        title: Título del log
        description: Descripción del log
        fields: Diccionario de campos adicionales {nombre: valor}
        user: Usuario relacionado con el log (opcional)
        channel: Canal relacionado con el log (opcional)
    
    Returns:
        bool: True si se envió correctamente, False si hubo error
    
    Ejemplo:
        await send_log(
            bot, guild_id, LogType.INFO,
            "Nuevo usuario",
            "Un usuario se unió al servidor",
            fields={"Usuario": "John#1234", "ID": "123456789"}
        )
    """
    try:
        # Obtener canal de logs
        channels_config = get_channels_config(guild_id)
        logs_channel_id = channels_config.get_channel("logs_channel")
        
        if not logs_channel_id:
            # No hay canal configurado, no hacer nada (silencioso)
            return False
        
        logs_channel = bot.get_channel(logs_channel_id)
        if not logs_channel:
            return False
        
        # Determinar color y emoji según tipo
        color_map = {
            LogType.INFO: LogColor.INFO,
            LogType.SUCCESS: LogColor.SUCCESS,
            LogType.WARNING: LogColor.WARNING,
            LogType.ERROR: LogColor.ERROR,
            LogType.MODERATION: LogColor.MODERATION,
            LogType.ECONOMY: LogColor.ECONOMY,
            LogType.COMMAND: LogColor.COMMAND,
        }
        
        emoji_map = {
            LogType.INFO: LogEmoji.INFO,
            LogType.SUCCESS: LogEmoji.SUCCESS,
            LogType.WARNING: LogEmoji.WARNING,
            LogType.ERROR: LogEmoji.ERROR,
            LogType.MODERATION: LogEmoji.MODERATION,
            LogType.ECONOMY: LogEmoji.ECONOMY,
            LogType.COMMAND: LogEmoji.COMMAND,
        }
        
        color = color_map.get(log_type, LogColor.INFO)
        emoji = emoji_map.get(log_type, LogEmoji.INFO)
        
        # Crear embed
        embed = discord.Embed(
            title=f"{emoji} {title}",
            description=description,
            color=color,
            timestamp=datetime.now()
        )
        
        # Agregar campos adicionales
        if fields:
            for field_name, field_value in fields.items():
                embed.add_field(
                    name=field_name,
                    value=str(field_value),
                    inline=True
                )
        
        # Agregar información del usuario si está disponible
        if user:
            embed.set_author(
                name=str(user),
                icon_url=user.display_avatar.url if user.display_avatar else None
            )
        
        # Agregar información del canal si está disponible
        if channel:
            embed.add_field(
                name="Canal",
                value=channel.mention,
                inline=True
            )
        
        # Enviar al canal de logs
        print(f"[DISCORD_LOG][{log_type.upper()}] {title} | {description}", flush=True)
        await logs_channel.send(embed=embed)
        return True
        
    except discord.Forbidden:
        print(f"⚠️ Sin permisos para enviar logs en el servidor {guild_id}")
        return False
    except Exception as e:
        print(f"❌ Error enviando log: {e}")
        return False


# Funciones auxiliares para tipos específicos de logs

async def log_info(
    bot: commands.Bot,
    guild_id: int,
    title: str,
    description: str,
    fields: Optional[dict] = None,
    user: Optional[discord.User] = None
) -> bool:
    """Envía un log de tipo INFO"""
    return await send_log(bot, guild_id, LogType.INFO, title, description, fields, user)


async def log_success(
    bot: commands.Bot,
    guild_id: int,
    title: str,
    description: str,
    fields: Optional[dict] = None,
    user: Optional[discord.User] = None
) -> bool:
    """Envía un log de tipo SUCCESS"""
    return await send_log(bot, guild_id, LogType.SUCCESS, title, description, fields, user)


async def log_warning(
    bot: commands.Bot,
    guild_id: int,
    title: str,
    description: str,
    fields: Optional[dict] = None,
    user: Optional[discord.User] = None
) -> bool:
    """Envía un log de tipo WARNING"""
    return await send_log(bot, guild_id, LogType.WARNING, title, description, fields, user)


async def log_error(
    bot: commands.Bot,
    guild_id: int,
    title: str,
    description: str,
    fields: Optional[dict] = None,
    user: Optional[discord.User] = None
) -> bool:
    """Envía un log de tipo ERROR"""
    return await send_log(bot, guild_id, LogType.ERROR, title, description, fields, user)


async def log_moderation(
    bot: commands.Bot,
    guild_id: int,
    title: str,
    description: str,
    fields: Optional[dict] = None,
    user: Optional[discord.User] = None,
    moderator: Optional[discord.User] = None
) -> bool:
    """Envía un log de tipo MODERATION"""
    if moderator and fields:
        fields["Moderador"] = str(moderator)
    elif moderator:
        fields = {"Moderador": str(moderator)}
    
    return await send_log(bot, guild_id, LogType.MODERATION, title, description, fields, user)


async def log_economy(
    bot: commands.Bot,
    guild_id: int,
    title: str,
    description: str,
    fields: Optional[dict] = None,
    user: Optional[discord.User] = None
) -> bool:
    """Envía un log de tipo ECONOMY"""
    return await send_log(bot, guild_id, LogType.ECONOMY, title, description, fields, user)


async def log_command(
    bot: commands.Bot,
    guild_id: int,
    command_name: str,
    user: discord.User,
    channel: discord.TextChannel,
    success: bool = True,
    error: Optional[str] = None
) -> bool:
    """
    Envía un log de ejecución de comando.
    
    Args:
        bot: Instancia del bot
        guild_id: ID del servidor
        command_name: Nombre del comando ejecutado
        user: Usuario que ejecutó el comando
        channel: Canal donde se ejecutó
        success: Si el comando se ejecutó correctamente
        error: Mensaje de error si hubo alguno
    """
    log_type = LogType.SUCCESS if success else LogType.ERROR
    
    if success:
        description = f"Comando `/{command_name}` ejecutado correctamente"
    else:
        description = f"Error al ejecutar `/{command_name}`"
        if error:
            description += f"\n**Error:** {error}"
    
    return await send_log(
        bot, guild_id, log_type,
        f"Comando: {command_name}",
        description,
        user=user,
        channel=channel
    )
