"""
Comandos de administración para PowerBot Discord.
Solo ejecutables por administradores.
"""
import discord
from discord import app_commands
from discord.ext import commands
from backend.services.discord_bot.config import get_channels_config, get_economy_config
from backend.services.discord_bot.config.mine_config import get_mine_config
from backend.services.discord_bot.config.roles import get_roles_config
from backend.services.discord_bot.bot_logging import log_info, log_success


def setup_admin_commands(bot: commands.Bot):
    """Registra comandos de administración"""
    
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
        app_commands.Choice(name="Notificaciones", value="notifications"),
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
                "notifications": "Notificaciones",
            }
            
            # Manejo diferenciado: DJ (único), MOD (múltiple), notifications (único)
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

            else:  # notifications
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

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error al configurar el rol: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    bot.tree.add_command(set_group)
    
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
    
    @bot.tree.command(
        name="say",
        description="Envía un mensaje como el bot (solo mods)"
    )
    @app_commands.describe(mensaje="El mensaje que enviará el bot")
    async def say(interaction: discord.Interaction, mensaje: str):
        """Envía un mensaje como el bot en el canal actual - Solo moderadores"""
        
        # Verificar permisos de moderación (admin o permisos de moderar miembros)
        if not (interaction.user.guild_permissions.administrator or 
                interaction.user.guild_permissions.moderate_members):
            embed = discord.Embed(
                title="❌ Acceso denegado",
                description="Solo los moderadores pueden usar este comando.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            # Responder al usuario de forma ephemeral
            confirm_embed = discord.Embed(
                title="✅ Mensaje enviado",
                description=f"Tu mensaje ha sido publicado en {interaction.channel.mention}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=confirm_embed, ephemeral=True)
            
            # Enviar el mensaje en el canal
            await interaction.channel.send(mensaje)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Error de permisos",
                description="El bot no tiene permisos para enviar mensajes en este canal.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Ocurrió un error: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    print("   ✓ Comandos de administración registrados")
