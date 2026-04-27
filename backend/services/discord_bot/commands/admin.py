"""
Comandos de administración para PowerBot Discord.
Solo ejecutables por administradores.
"""
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands
from backend.services.discord_bot.config import get_channels_config, get_economy_config
from backend.services.discord_bot.config.mine_config import get_mine_config
from backend.services.discord_bot.config.roles import get_roles_config
from backend.services.youtube_api.config.economy import get_youtube_economy_config
from backend.services.discord_bot.bot_logging import log_info, log_success, log_moderation


_TEMP_CASTIGO_FILE = Path(__file__).resolve().parents[4] / "data" / "discord_bot" / "temp_castigos.json"
_TEMP_CASTIGO_LOCK = asyncio.Lock()


def _to_discord_timestamp(unix_timestamp: int, style: str = "R") -> str:
    return f"<t:{int(unix_timestamp)}:{style}>"


def _format_duration_es(total_seconds: int) -> str:
    seconds = int(max(0, total_seconds))
    if seconds < 60:
        return f"{seconds} segundo{'s' if seconds != 1 else ''}"

    minutes, rem_seconds = divmod(seconds, 60)
    if minutes < 60:
        if rem_seconds == 0:
            return f"{minutes} minuto{'s' if minutes != 1 else ''}"
        return (
            f"{minutes} minuto{'s' if minutes != 1 else ''} "
            f"{rem_seconds} segundo{'s' if rem_seconds != 1 else ''}"
        )

    hours, rem_minutes = divmod(minutes, 60)
    if hours < 24:
        if rem_minutes == 0:
            return f"{hours} hora{'s' if hours != 1 else ''}"
        return f"{hours} hora{'s' if hours != 1 else ''} {rem_minutes} minuto{'s' if rem_minutes != 1 else ''}"

    days, rem_hours = divmod(hours, 24)
    if rem_hours == 0:
        return f"{days} dia{'s' if days != 1 else ''}"
    return f"{days} dia{'s' if days != 1 else ''} {rem_hours} hora{'s' if rem_hours != 1 else ''}"


def _parse_duration_to_seconds(raw: str) -> int | None:
    token = str(raw).strip().lower()
    match = re.fullmatch(r"(\d+)([smhd])?", token)
    if not match:
        return None

    value = int(match.group(1))
    suffix = match.group(2)

    if value <= 0:
        return None

    if suffix is None or suffix == "s":
        return value
    if suffix == "m":
        return value * 60
    if suffix == "h":
        return value * 3600
    if suffix == "d":
        return value * 86400

    return None


async def _load_temp_castigos() -> list[dict[str, Any]]:
    async with _TEMP_CASTIGO_LOCK:
        if not _TEMP_CASTIGO_FILE.exists():
            return []
        try:
            with open(_TEMP_CASTIGO_FILE, "r", encoding="utf-8") as file:
                payload = json.load(file)
            if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
                return payload["entries"]
        except Exception:
            pass
        return []


async def _save_temp_castigos(entries: list[dict[str, Any]]) -> None:
    async with _TEMP_CASTIGO_LOCK:
        _TEMP_CASTIGO_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_TEMP_CASTIGO_FILE, "w", encoding="utf-8") as file:
            json.dump({"entries": entries}, file, indent=2, ensure_ascii=False)


async def _upsert_temp_castigo(entry: dict[str, Any]) -> None:
    entries = await _load_temp_castigos()
    filtered = [
        e for e in entries
        if not (
            int(e.get("guild_id", 0)) == int(entry.get("guild_id", 0))
            and int(e.get("user_id", 0)) == int(entry.get("user_id", 0))
            and int(e.get("role_id", 0)) == int(entry.get("role_id", 0))
        )
    ]
    filtered.append(entry)
    await _save_temp_castigos(filtered)


async def _ensure_temp_castigo_cleanup_task(bot: commands.Bot) -> None:
    task = getattr(bot, "_temp_castigo_cleanup_task", None)
    if task is None or task.done():
        bot._temp_castigo_cleanup_task = asyncio.create_task(_temp_castigo_cleanup_loop(bot))


async def _temp_castigo_cleanup_loop(bot: commands.Bot) -> None:
    while not bot.is_closed():
        try:
            await _process_expired_temp_castigos(bot)
        except Exception as exc:
            print(f"⚠️ Error en cleanup de castigos temporales: {exc}")
        await asyncio.sleep(5)


async def _process_expired_temp_castigos(bot: commands.Bot) -> None:
    entries = await _load_temp_castigos()
    if not entries:
        return

    now_ts = int(time.time())
    remaining: list[dict[str, Any]] = []

    for entry in entries:
        guild_id = int(entry.get("guild_id", 0) or 0)
        user_id = int(entry.get("user_id", 0) or 0)
        role_id = int(entry.get("role_id", 0) or 0)
        expires_at = int(entry.get("expires_at", 0) or 0)
        role_key = str(entry.get("role_key") or "castigo")
        reason_text = str(entry.get("reason") or "Incumplimiento de reglas del servidor")
        applied_by = int(entry.get("applied_by", 0) or 0)

        if expires_at > now_ts:
            remaining.append(entry)
            continue

        if guild_id <= 0 or user_id <= 0 or role_id <= 0:
            continue

        guild = bot.get_guild(guild_id)
        if guild is None:
            continue

        role = guild.get_role(role_id)
        if role is None:
            continue

        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                member = None

        if member is None:
            continue

        if role not in member.roles:
            continue

        try:
            await member.remove_roles(role, reason="Castigo temporal completado")
            moderator_user = guild.get_member(applied_by) if applied_by > 0 else None
            await log_moderation(
                bot,
                guild.id,
                "Castigo temporal finalizado",
                f"Se retiró automáticamente el rol temporal de {member.mention} al completarse el tiempo.",
                fields={
                    "Usuario": f"{member.mention} ({member.id})",
                    "Nivel": role_key,
                    "Rol": f"{role.name} ({role.id})",
                    "Motivo": reason_text,
                    "Expiró": _to_discord_timestamp(expires_at, "R"),
                },
                user=member,
                moderator=moderator_user,
            )
        except Exception:
            # Si falla, lo mantenemos para reintentar en el próximo ciclo
            remaining.append(entry)

    await _save_temp_castigos(remaining)


def setup_admin_commands(bot: commands.Bot):
    """Registra comandos de administración"""

    try:
        asyncio.create_task(_ensure_temp_castigo_cleanup_task(bot))
    except RuntimeError:
        pass

    admin_group = app_commands.Group(name="admin", description="Comandos administrativos")

    @admin_group.command(name="say", description="Publica un mensaje de texto plano en este canal")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.describe(mensaje="Texto que publicará el bot")
    async def admin_say(interaction: discord.Interaction, mensaje: str):
        """Comando de servidor: envía texto suelto en el canal sin firma del usuario."""
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Este comando solo se puede usar en servidor.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Solo los administradores pueden usar este comando.",
                ephemeral=True,
            )
            return

        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "Este canal no admite mensajes de texto del bot.",
                ephemeral=True,
            )
            return

        try:
            await channel.send(str(mensaje))
            await interaction.response.send_message("Mensaje enviado.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "No tengo permisos para enviar mensajes en este canal.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Error al enviar mensaje: {e}",
                ephemeral=True,
            )
    
    @bot.tree.command(name="setprefix", description="Cambia el prefix del bot (solo admin)")
    @app_commands.describe(prefix="El nuevo prefix (ej: !, ?, >)")
    async def setprefix(interaction: discord.Interaction, prefix: str):
        """Cambia el prefix del bot en este servidor - Solo administradores"""
        
        # Verificar permisos de administración
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Acceso denegado",
                description="Solo los administradores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Si tiene permisos, ejecutar comando
        if len(prefix) > 3:
            embed = discord.Embed(
                title="❌ Error",
                description="El prefix debe tener máximo 3 caracteres.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="✅ Prefix actualizado",
            description=f"Nuevo prefix: `{prefix}`",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # Grupo de comandos /set
    set_group = app_commands.Group(name="set", description="Configuración del servidor")
    
    @set_group.command(name="channel", description="Configura canales del servidor")
    @app_commands.describe(
        tipo="Tipo de canal a configurar",
        channel="Canal a asignar"
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Confesiones", value="confession"),
        app_commands.Choice(name="Logs", value="logs"),
        app_commands.Choice(name="Economía", value="economy"),
        app_commands.Choice(name="Mina", value="mine"),
        app_commands.Choice(name="Livestreams", value="livestreams"),
    ])
    async def set_channel(interaction: discord.Interaction, tipo: app_commands.Choice[str], channel: discord.TextChannel):
        """Configura canales del servidor - Solo administradores"""
        
        # Verificar permisos
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Acceso denegado",
                description="Solo los administradores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            # Mapear tipos a nombres de configuración
            channel_map = {
                "confession": "confession_channel",
                "logs": "logs_channel",
                "economy": "economy_channel",
                "livestreams": "livestream_channel",
            }
            
            # Guardar el canal
            if tipo.value == "mine":
                mine_config = get_mine_config(interaction.guild.id)
                mine_config.set_mine_channel_id(channel.id)
            else:
                channels_config = get_channels_config(interaction.guild.id)
                config_name = channel_map.get(tipo.value)
                if not config_name:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="Tipo de canal no reconocido.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                channels_config.set_channel(config_name, channel.id)
            
            # Mapear tipos a nombres amigables
            tipo_nombre = {
                "confession": "Confesiones",
                "logs": "Logs",
                "economy": "Economía",
                "mine": "Mina",
                "livestreams": "Livestreams",
            }
            
            embed = discord.Embed(
                title="✅ Canal configurado",
                description=f"Canal de {tipo_nombre.get(tipo.value)} establecido",
                color=discord.Color.green()
            )
            embed.add_field(name="Tipo", value=f"`{tipo_nombre.get(tipo.value)}`", inline=True)
            embed.add_field(name="Canal", value=f"{channel.mention}", inline=True)
            embed.add_field(name="ID", value=f"`{channel.id}`", inline=True)
            embed.set_footer(text="Guardado en data/discord_bot/")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Log de la configuración (solo si no es el canal de logs mismo)
            if tipo.value != "logs":
                await log_success(
                    bot,
                    interaction.guild.id,
                    "Canal configurado",
                    f"Canal de {tipo_nombre.get(tipo.value)} establecido por {interaction.user.mention}",
                    fields={
                        "Tipo": tipo_nombre.get(tipo.value),
                        "Canal": channel.mention,
                        "Configurado por": interaction.user.display_name
                    }
                )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error al configurar el canal: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @set_group.command(name="afk_voice_channel", description="Configura el canal de voz AFK (sin ganancias)")
    @app_commands.describe(channel="Canal de voz AFK a bloquear para earning")
    async def set_afk_voice_channel(interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Configura el canal de voz AFK para bloquear earning - Solo administradores"""

        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Acceso denegado",
                description="Solo los administradores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            channels_config = get_channels_config(interaction.guild.id)
            channels_config.set_channel("afk_voice_channel", channel.id)

            embed = discord.Embed(
                title="✅ Canal AFK de voz configurado",
                description="Este canal quedará bloqueado para ganancias por llamada.",
                color=discord.Color.green()
            )
            embed.add_field(name="Canal AFK", value=channel.mention, inline=True)
            embed.add_field(name="ID", value=f"`{channel.id}`", inline=True)
            embed.set_footer(text="Guardado en data/discord_bot/")

            await interaction.response.send_message(embed=embed, ephemeral=True)

            await log_success(
                bot,
                interaction.guild.id,
                "Canal AFK de voz configurado",
                f"Canal AFK de voz establecido por {interaction.user.mention}",
                fields={
                    "Canal": channel.mention,
                    "ID": str(channel.id),
                    "Configurado por": interaction.user.display_name,
                }
            )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error al configurar canal AFK de voz: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @set_group.command(name="currency", description="Configura la moneda del servidor")
    @app_commands.describe(
        nombre="Nombre de la moneda (máx 20 caracteres)",
        simbolo="Símbolo de la moneda (máx 5 caracteres)"
    )
    async def set_currency(interaction: discord.Interaction, nombre: str, simbolo: str):
        """Configura la moneda del servidor - Solo administradores"""
        
        # Verificar permisos
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Acceso denegado",
                description="Solo los administradores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Validar longitud del nombre
        if len(nombre) > 20:
            embed = discord.Embed(
                title="❌ Error",
                description="El nombre de la moneda no puede exceder 20 caracteres.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Validar símbolo
        if len(simbolo) > 5:
            embed = discord.Embed(
                title="❌ Error",
                description="El símbolo no puede exceder 5 caracteres.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            # Obtener configuración de economía y guardar
            economy_config = get_economy_config(interaction.guild.id)
            economy_config.set_currency(nombre, simbolo)
            
            embed = discord.Embed(
                title="✅ Moneda actualizada",
                description=f"Nueva moneda configurada",
                color=discord.Color.green()
            )
            embed.add_field(name="Nombre", value=f"`{nombre}`", inline=True)
            embed.add_field(name="Símbolo", value=f"`{simbolo}`", inline=True)
            embed.set_footer(text="Guardado en data/discord_bot/")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Logging de cambio de moneda
            await log_success(
                bot,
                interaction.guild.id,
                "Moneda actualizada",
                f"La moneda del servidor ha sido actualizada por {interaction.user.mention}",
                fields={
                    "Moneda": nombre,
                    "Símbolo": simbolo,
                    "Configurado por": interaction.user.display_name
                }
            )
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error al actualizar la moneda: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @set_group.command(name="points", description="Configura cantidad e intervalo de puntos")
    @app_commands.describe(
        amount="Cantidad de puntos que da el bot",
        interval="Intervalo en segundos (ej: 300 = 5 minutos)"
    )
    async def set_points(interaction: discord.Interaction, amount: int, interval: int):
        """Configura puntos y su intervalo - Solo administradores"""
        
        # Verificar permisos
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Acceso denegado",
                description="Solo los administradores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Validar values
        if amount <= 0:
            embed = discord.Embed(
                title="❌ Error",
                description="La cantidad de puntos debe ser mayor a 0.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if interval <= 0:
            embed = discord.Embed(
                title="❌ Error",
                description="El intervalo debe ser mayor a 0 segundos.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            # Obtener configuración de economía y guardar
            economy_config = get_economy_config(interaction.guild.id)
            economy_config.set_points(amount, interval)

            youtube_economy_config = get_youtube_economy_config()
            youtube_economy_config.set_sync_source_guild_id(interaction.guild.id)
            youtube_economy_config.set_points(amount, interval)
            youtube_economy_config.set_earning_enabled(economy_config.is_earning_enabled())
            
            # Convertir segundos a minutos para mostrar
            minutes = interval / 60
            
            embed = discord.Embed(
                title="✅ Configuración de puntos actualizada",
                description=f"Puntos configurados correctamente",
                color=discord.Color.green()
            )
            embed.add_field(name="Cantidad de puntos", value=f"`{amount}` puntos", inline=True)
            embed.add_field(name="Intervalo", value=f"`{interval}` segundos (`{minutes:.1f}` min)", inline=True)
            embed.set_footer(text="Guardado en data/discord_bot/")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Logging de cambio de puntos
            await log_success(
                bot,
                interaction.guild.id,
                "Configuración de puntos actualizada",
                f"La configuración de puntos ha sido actualizada por {interaction.user.mention}",
                fields={
                    "Cantidad": f"{amount} puntos",
                    "Intervalo": f"{minutes:.1f} minutos",
                    "Configurado por": interaction.user.display_name
                }
            )
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error al configurar puntos: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @set_group.command(name="earning", description="Activa o desactiva el earning global en Discord y YouTube")
    @app_commands.describe(enabled="True para activar, false para desactivar")
    async def set_earning(interaction: discord.Interaction, enabled: bool):
        """Configura el earning global para mensajes y voz en Discord, y chat en YouTube."""

        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Acceso denegado",
                description="Solo los administradores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            economy_config = get_economy_config(interaction.guild.id)
            economy_config.set_earning_enabled(enabled)

            youtube_economy_config = get_youtube_economy_config()
            youtube_economy_config.set_sync_source_guild_id(interaction.guild.id)
            youtube_economy_config.set_points(
                economy_config.get_points_amount(),
                economy_config.get_points_interval(),
            )
            youtube_economy_config.set_earning_enabled(enabled)

            state_text = "activado" if enabled else "desactivado"
            color = discord.Color.green() if enabled else discord.Color.orange()

            embed = discord.Embed(
                title="✅ Earning actualizado",
                description=f"El earning global quedó {state_text} en Discord y YouTube.",
                color=color,
            )
            embed.add_field(name="Discord mensajes", value=state_text, inline=True)
            embed.add_field(name="Discord voz", value=state_text, inline=True)
            embed.add_field(name="YouTube chat", value=state_text, inline=True)
            embed.add_field(
                name="Sincronización",
                value=f"Guild fuente: `{interaction.guild.id}`",
                inline=False,
            )
            embed.set_footer(text="YouTube usa el mismo amount e interval que Discord")

            await interaction.response.send_message(embed=embed, ephemeral=True)

            await log_success(
                bot,
                interaction.guild.id,
                "Earning global actualizado",
                f"{interaction.user.mention} cambió el earning global a {state_text}",
                fields={
                    "Estado": state_text,
                    "Guild fuente YouTube": str(interaction.guild.id),
                    "Configurado por": interaction.user.display_name,
                }
            )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error al configurar earning: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @set_group.command(name="earning_channel", description="Agrega/elimina canales donde se ganan puntos hablando")
    @app_commands.describe(
        accion="Agregar o eliminar canal",
        channel="Canal a configurar"
    )
    @app_commands.choices(accion=[
        app_commands.Choice(name="➕ Agregar", value="add"),
        app_commands.Choice(name="➖ Eliminar", value="remove"),
        app_commands.Choice(name="📋 Ver lista", value="list"),
    ])
    async def set_earning_channel(interaction: discord.Interaction, accion: app_commands.Choice[str], channel: discord.TextChannel = None):
        """Configura canales donde se ganan puntos hablando - Solo administradores"""
        
        # Verificar permisos
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Acceso denegado",
                description="Solo los administradores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            economy_config = get_economy_config(interaction.guild.id)
            valid_text_channel_ids = [text_channel.id for text_channel in interaction.guild.text_channels]
            removed_stale = economy_config.prune_deleted_earning_channels(valid_text_channel_ids)
            
            if accion.value == "add":
                # Agregar canal
                if not channel:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="Debes especificar un canal para agregar.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                success = economy_config.add_earning_channel(channel.id)
                
                if success:
                    embed = discord.Embed(
                        title="✅ Canal de ganancias agregado",
                        description=f"Los usuarios ahora ganarán puntos al escribir en {channel.mention}",
                        color=discord.Color.green()
                    )
                    
                    # Logging de canal agregado
                    await log_info(
                        bot,
                        interaction.guild.id,
                        "Canal de ganancias agregado",
                        f"Canal {channel.mention} agregado a la lista por {interaction.user.mention}",
                        fields={
                            "Canal": channel.name,
                            "Agregado por": interaction.user.display_name
                        }
                    )
                else:
                    embed = discord.Embed(
                        title="ℹ️ Canal ya configurado",
                        description=f"{channel.mention} ya está en la lista de canales de ganancias",
                        color=discord.Color.blue()
                    )
            
            elif accion.value == "remove":
                # Eliminar canal
                if not channel:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="Debes especificar un canal para eliminar.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                success = economy_config.remove_earning_channel(channel.id)
                
                if success:
                    embed = discord.Embed(
                        title="✅ Canal de ganancias eliminado",
                        description=f"{channel.mention} ya no dará puntos",
                        color=discord.Color.green()
                    )
                    
                    # Logging de canal eliminado
                    await log_info(
                        bot,
                        interaction.guild.id,
                        "Canal de ganancias eliminado",
                        f"Canal {channel.mention} eliminado de la lista por {interaction.user.mention}",
                        fields={
                            "Canal": channel.name,
                            "Eliminado por": interaction.user.display_name
                        }
                    )
                else:
                    embed = discord.Embed(
                        title="ℹ️ Canal no configurado",
                        description=f"{channel.mention} no estaba en la lista de canales de ganancias",
                        color=discord.Color.blue()
                    )
            
            else:  # list
                embed = discord.Embed(
                    title="📋 Canales de ganancias",
                    description="Canales donde se ganan puntos hablando",
                    color=discord.Color.blue()
                )

                if removed_stale > 0:
                    embed.add_field(
                        name="🧹 Limpieza automática",
                        value=f"Se eliminaron `{removed_stale}` canal(es) borrados de la configuración.",
                        inline=False,
                    )
                
                earning_channels = economy_config.get_earning_channels()
                if earning_channels:
                    channels_list = "\n".join([f"• <#{ch_id}>" for ch_id in earning_channels])
                    embed.add_field(name="Canales configurados", value=channels_list, inline=False)
                else:
                    embed.add_field(name="Canales configurados", value="*Ninguno configurado*", inline=False)
                
                embed.set_footer(text=f"Total: {len(earning_channels)} canal(es)")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Mostrar lista actual de canales
            earning_channels = economy_config.get_earning_channels()
            if earning_channels:
                channels_list = "\n".join([f"• <#{ch_id}>" for ch_id in earning_channels])
                embed.add_field(name="Canales actuales", value=channels_list, inline=False)
            else:
                embed.add_field(name="Canales actuales", value="*Ninguno configurado*", inline=False)
            
            embed.set_footer(text="Guardado en data/discord_bot/")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error al configurar canal de ganancias: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @set_group.command(name="role", description="Configura roles del servidor")
    @app_commands.describe(
        tipo="Tipo de rol a configurar",
        rol="Rol a asignar"
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="DJ", value="dj"),
        app_commands.Choice(name="MOD", value="mod"),
        app_commands.Choice(name="Streamer", value="streamer"),
        app_commands.Choice(name="Notificaciones", value="notifications"),
        app_commands.Choice(name="CastigadoLv1", value="castigado_lv1"),
        app_commands.Choice(name="CastigadoLv2", value="castigado_lv2"),
        app_commands.Choice(name="CastigadoLv3", value="castigado_lv3"),
    ])
    async def set_role(interaction: discord.Interaction, tipo: app_commands.Choice[str], rol: discord.Role):
        """Configura roles del servidor - Solo administradores"""
        
        # Verificar permisos
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Acceso denegado",
                description="Solo los administradores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            # Obtener configuración de roles
            roles_config = get_roles_config(interaction.guild.id)
            
            # Mapear tipos a nombres amigables
            tipo_nombre = {
                "dj": "DJ",
                "mod": "MOD",
                "streamer": "Streamer",
                "notifications": "Notificaciones",
                "castigado_lv1": "CastigadoLv1",
                "castigado_lv2": "CastigadoLv2",
                "castigado_lv3": "CastigadoLv3",
            }
            
            # Manejo diferenciado: DJ (único), MOD (múltiple), streamer/notifications (único)
            if tipo.value == "dj":
                # DJ solo puede tener un rol
                roles_config.set_role("dj", rol.id)
                
                embed = discord.Embed(
                    title="✅ Rol DJ configurado",
                    description=f"Rol DJ establecido",
                    color=discord.Color.green()
                )
                embed.add_field(name="Tipo", value=f"`DJ`", inline=True)
                embed.add_field(name="Rol", value=f"{rol.mention}", inline=True)
                embed.add_field(name="ID", value=f"`{rol.id}`", inline=True)
                embed.set_footer(text="Guardado en data/discord_bot/")
                
            elif tipo.value == "mod":  # MOD
                # MOD puede tener múltiples roles
                is_new = roles_config.add_mod_role(rol.id)
                
                if is_new:
                    embed = discord.Embed(
                        title="✅ Rol MOD agregado",
                        description=f"Rol MOD agregado a la lista",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Tipo", value=f"`MOD`", inline=True)
                    embed.add_field(name="Rol agregado", value=f"{rol.mention}", inline=True)
                    embed.add_field(name="ID", value=f"`{rol.id}`", inline=True)
                else:
                    embed = discord.Embed(
                        title="ℹ️ Rol MOD ya existe",
                        description=f"Este rol ya está configurado como MOD",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Rol", value=f"{rol.mention}", inline=True)
                    embed.add_field(name="ID", value=f"`{rol.id}`", inline=True)
                
                # Mostrar todos los roles MOD
                mod_roles = roles_config.get_mod_roles()
                if mod_roles:
                    roles_list = "\n".join([f"• <@&{role_id}>" for role_id in mod_roles])
                    embed.add_field(name="Roles MOD totales", value=roles_list, inline=False)
                
                embed.set_footer(text="Guardado en data/discord_bot/")

            elif tipo.value == "streamer":
                roles_config.set_role("streamer", rol.id)

                embed = discord.Embed(
                    title="✅ Rol streamer configurado",
                    description="Rol principal del streamer configurado correctamente",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Tipo", value="`Streamer`", inline=True)
                embed.add_field(name="Rol", value=rol.mention, inline=True)
                embed.add_field(name="ID", value=f"`{rol.id}`", inline=True)
                embed.set_footer(text="Guardado en data/discord_bot/")

            elif tipo.value == "notifications":
                roles_config.set_role("notifications", rol.id)

                embed = discord.Embed(
                    title="✅ Rol de notificaciones configurado",
                    description="Rol usado para notificar eventos globales (ej: streams en vivo)",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Tipo", value="`Notificaciones`", inline=True)
                embed.add_field(name="Rol", value=rol.mention, inline=True)
                embed.add_field(name="ID", value=f"`{rol.id}`", inline=True)
                embed.set_footer(text="Guardado en data/discord_bot/")

            elif tipo.value in {"castigado_lv1", "castigado_lv2", "castigado_lv3"}:
                roles_config.set_role(tipo.value, rol.id)

                embed = discord.Embed(
                    title="✅ Rol de castigo configurado",
                    description="Rol de castigo temporal configurado correctamente",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Tipo", value=f"`{tipo_nombre.get(tipo.value)}`", inline=True)
                embed.add_field(name="Rol", value=rol.mention, inline=True)
                embed.add_field(name="ID", value=f"`{rol.id}`", inline=True)
                embed.set_footer(text="Guardado en data/discord_bot/")

            else:
                embed = discord.Embed(
                    title="❌ Error",
                    description="Tipo de rol no reconocido.",
                    color=discord.Color.red(),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error al configurar el rol: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="castigar", description="Añade un rol de castigo temporal (Lv1/Lv2/Lv3)")
    @app_commands.describe(
        target="Usuario a castigar",
        nivel="Nivel del castigo a aplicar",
        tiempo="Duración (ej: 200, 13s, 1m, 5m, 7h, 2d)",
        motivo="Motivo opcional del castigo",
    )
    @app_commands.choices(nivel=[
        app_commands.Choice(name="Lv1", value="castigado_lv1"),
        app_commands.Choice(name="Lv2", value="castigado_lv2"),
        app_commands.Choice(name="Lv3", value="castigado_lv3"),
    ])
    async def castigar(
        interaction: discord.Interaction,
        target: discord.Member,
        nivel: app_commands.Choice[str],
        tiempo: str,
        motivo: str | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Este comando solo se puede usar en servidor.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Acceso denegado",
                description="Solo los administradores pueden usar este comando.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        duration_seconds = _parse_duration_to_seconds(tiempo)
        if duration_seconds is None:
            await interaction.response.send_message(
                "Tiempo inválido. Usa segundos puros o sufijo s/m/h/d (ej: 200, 13s, 1m, 7h, 2d).",
                ephemeral=True,
            )
            return

        await _ensure_temp_castigo_cleanup_task(bot)

        roles_config = get_roles_config(interaction.guild.id)
        role_id = roles_config.get_role(nivel.value)
        if not role_id:
            await interaction.response.send_message(
                f"No hay rol configurado para {nivel.name}. Configúralo con /set role.",
                ephemeral=True,
            )
            return

        role = interaction.guild.get_role(int(role_id))
        if role is None:
            await interaction.response.send_message(
                f"El rol configurado para {nivel.name} ya no existe. Vuelve a configurarlo con /set role.",
                ephemeral=True,
            )
            return

        if target.bot:
            await interaction.response.send_message("No puedes castigar bots.", ephemeral=True)
            return

        now_ts = int(time.time())
        expires_at = now_ts + int(duration_seconds)
        safe_reason = (motivo or "Incumplimiento de reglas del servidor").strip()

        try:
            await target.add_roles(role, reason=f"Castigo temporal ({nivel.name}) por {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "No tengo permisos para asignar ese rol. Revisa la jerarquía de roles.",
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.response.send_message(f"Error al asignar el rol: {e}", ephemeral=True)
            return

        await _upsert_temp_castigo(
            {
                "guild_id": int(interaction.guild.id),
                "user_id": int(target.id),
                "role_id": int(role.id),
                "role_key": str(nivel.value),
                "expires_at": int(expires_at),
                "reason": safe_reason,
                "applied_by": int(interaction.user.id),
                "created_at": int(now_ts),
            }
        )

        dm_embed = discord.Embed(
            title="⚠️ Has sido castigado por la moderación",
            description=(
                f"Has recibido una sanción temporal ({nivel.name}) en **{interaction.guild.name}**.\n"
                f"Motivo: **{safe_reason}**"
            ),
            color=discord.Color.orange(),
        )
        dm_embed.add_field(name="Duración", value=f"{_format_duration_es(duration_seconds)}", inline=True)
        dm_embed.add_field(name="Finaliza", value=f"{_to_discord_timestamp(expires_at, 'R')}", inline=True)
        dm_embed.add_field(name="Fecha exacta", value=f"{_to_discord_timestamp(expires_at, 'F')}", inline=False)
        dm_embed.set_footer(
            text="Recuerda seguir las reglas del servidor o tu sanción podría ser mayor"
        )

        dm_sent = True
        try:
            await target.send(embed=dm_embed)
        except Exception:
            dm_sent = False

        response_embed = discord.Embed(
            title="✅ Castigo aplicado",
            description=f"Se aplicó **{nivel.name}** a {target.mention}",
            color=discord.Color.green(),
        )
        response_embed.add_field(name="Duración", value=f"{_format_duration_es(duration_seconds)}", inline=True)
        response_embed.add_field(name="Termina", value=f"{_to_discord_timestamp(expires_at, 'R')}", inline=True)
        response_embed.add_field(name="Razón", value=safe_reason, inline=False)
        response_embed.add_field(name="DM enviado", value="Sí" if dm_sent else "No", inline=True)

        await interaction.response.send_message(embed=response_embed, ephemeral=True)

        await log_moderation(
            bot,
            interaction.guild.id,
            "Castigo temporal aplicado",
            f"{interaction.user.mention} aplicó {nivel.name} a {target.mention}.",
            fields={
                "Usuario": f"{target.mention} ({target.id})",
                "Nivel": nivel.name,
                "Rol": f"{role.name} ({role.id})",
                "Duración": _format_duration_es(duration_seconds),
                "Finaliza": _to_discord_timestamp(expires_at, "R"),
                "Motivo": safe_reason,
                "DM enviado": "Sí" if dm_sent else "No",
            },
            user=target,
            moderator=interaction.user,
        )
    
    bot.tree.add_command(set_group)
    bot.tree.add_command(admin_group)
    
    @bot.tree.command(name="clean", description="Limpia configuración guardada")
    @app_commands.describe(tipo="Qué configuración deseas limpiar")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Roles", value="roles"),
        app_commands.Choice(name="Canales", value="channels"),
        app_commands.Choice(name="Economía", value="economy"),
        app_commands.Choice(name="earning_channel", value="earning_channel"),
    ])
    async def clean(interaction: discord.Interaction, tipo: app_commands.Choice[str]):
        """Limpia configuración guardada - Solo administradores"""
        
        # Verificar permisos
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Acceso denegado",
                description="Solo los administradores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            tipo_valor = tipo.value
            
            if tipo_valor == "roles":
                # Limpiar roles
                roles_config = get_roles_config(interaction.guild.id)
                roles_config._config = roles_config._defaults.copy()
                roles_config._save()
                
                embed = discord.Embed(
                    title="✅ Roles limpiados",
                    description="Configuración de roles reiniciada a valores por defecto",
                    color=discord.Color.green()
                )
                
            elif tipo_valor == "channels":
                # Limpiar canales
                channels_config = get_channels_config(interaction.guild.id)
                channels_config._config = channels_config._defaults.copy()
                channels_config._save()
                
                embed = discord.Embed(
                    title="✅ Canales limpiados",
                    description="Configuración de canales reiniciada a valores por defecto",
                    color=discord.Color.green()
                )
                
            elif tipo_valor == "economy":
                # Limpiar economía
                economy_config = get_economy_config(interaction.guild.id)
                economy_config._config = economy_config._defaults.copy()
                economy_config._save()
                
                embed = discord.Embed(
                    title="✅ Economía limpiada",
                    description="Configuración de economía reiniciada a valores por defecto",
                    color=discord.Color.green()
                )
            
            elif tipo_valor == "earning_channel":
                # Limpiar canales de ganancias
                economy_config = get_economy_config(interaction.guild.id)
                economy_config.clear_earning_channels()
                
                embed = discord.Embed(
                    title="✅ earning_channel limpiado",
                    description="Todos los canales de ganancias han sido eliminados",
                    color=discord.Color.green()
                )
            
            tipo_nombre = {
                "roles": "Roles",
                "channels": "Canales",
                "economy": "Economía",
                "earning_channel": "earning_channel",
            }
            
            embed.add_field(name="Tipo", value=f"`{tipo_nombre.get(tipo_valor)}`", inline=True)
            embed.set_footer(text="Puedes volver a configurar este apartado")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error al limpiar configuración: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    print("   ✓ Comandos de administración registrados")
