"""
PowerBot Discord - Bot básico de Discord

Ejecutar directamente para pruebas:
    python backend/services/discord_bot/bot_core.py
"""
import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv
import discord
from discord.ext import commands

# Configurar path ANTES de importar backend (necesario para ejecución directa)
root_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(root_dir))

# Inicializar base de datos
from backend.database import init_database
from backend.managers import get_or_create_discord_user
from backend.managers.economy_manager import get_user_balance_by_discord_id
from backend.services.discord_bot.economy.earning import process_message_earning, process_voice_earning_in_channel
from backend.services.discord_bot.economy.economy_channel import (
    notify_economy_progress_if_needed,
    pop_external_platform_progress_events,
    notify_external_platform_progress_all_guilds,
)
from backend.services.discord_bot.config.economy import get_economy_config
from backend.services.discord_bot.discord_avatar_packager import DiscordAvatarPackager


class PowerBotDiscord(commands.Bot):
    """Bot de Discord para PowerBot"""
    
    def __init__(self, prefix: str = "!"):
        # Configurar intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        
        super().__init__(
            command_prefix=prefix,
            intents=intents,
            help_command=None
        )
        
        self.start_time = None
        self.voice_earning_poll_seconds = 10
        self._voice_earning_task: asyncio.Task | None = None
        self._external_economy_events_task: asyncio.Task | None = None
    
    async def setup_hook(self):
        """Se ejecuta al inicializar el bot (antes de on_ready)"""
        print(f"🔧 Configurando {self.user.name}...")
        
        # Inicializar base de datos
        try:
            init_database()
            print("✅ Base de datos inicializada")
        except Exception as e:
            print(f"⚠️ Error inicializando DB: {e}")
        
        # Registrar comandos de admin
        from backend.services.discord_bot.commands.admin import setup_admin_commands
        setup_admin_commands(self)
        
        # Registrar comandos sociales
        from backend.services.discord_bot.commands.social import setup_social_commands
        setup_social_commands(self)

        # Registrar comandos generales
        from backend.services.discord_bot.commands.general import setup_general_commands
        setup_general_commands(self)

        # Registrar comandos de vinculación de cuentas
        from backend.services.discord_bot.commands.link_accounts.link_acc import setup_link_commands
        setup_link_commands(self)

        # Registrar comandos admin de vinculación forzada
        from backend.services.discord_bot.commands.link_accounts.link_admin import setup_link_admin_commands
        setup_link_admin_commands(self)
        
        # Registrar comandos de economía
        from backend.services.discord_bot.commands.economy.user_economy import setup_economy_commands
        setup_economy_commands(self)

        # Registrar comandos admin de economía
        from backend.services.discord_bot.commands.economy.admin_economy import setup_admin_economy_commands
        setup_admin_economy_commands(self)

        # Registrar comandos de top economia
        from backend.services.discord_bot.commands.economy.top import setup_top_commands
        setup_top_commands(self)

        # Registrar comandos de mina
        from backend.services.discord_bot.commands.economy.mine_admin import setup_mine_commands
        setup_mine_commands(self)
        
        # Registrar comandos de items
        from backend.services.discord_bot.commands.items.item_finder import setup_item_commands
        setup_item_commands(self)
        
        # Registrar comandos de inventario
        from backend.services.discord_bot.commands.items.item_inventory import setup_inventory_commands
        setup_inventory_commands(self)
        
        # Registrar comandos de admin de items
        from backend.services.discord_bot.commands.items.admin_item import setup_admin_item_commands
        setup_admin_item_commands(self)

        # Registrar comandos de juegos
        from backend.services.discord_bot.commands.games.gamble import setup_gamble_commands
        setup_gamble_commands(self)

        from backend.services.discord_bot.commands.games.slots import setup_slots_commands
        setup_slots_commands(self)

        from backend.services.discord_bot.commands.games.rock_paper_scissors import setup_ppt_commands
        setup_ppt_commands(self)

        from backend.services.discord_bot.commands.games.games_admin import setup_games_admin_commands
        setup_games_admin_commands(self)
        
        # Sincronizar comandos slash
        try:
            synced = await self.tree.sync()
            print(f"✅ {len(synced)} comandos sincronizados")
        except Exception as e:
            print(f"⚠️ Error sincronizando: {e}")
    
    async def on_ready(self):
        """Se ejecuta cuando el bot está completamente listo"""
        from datetime import datetime
        self.start_time = datetime.now()
        
        print(f"✅ {self.user.name} está conectado")
        print(f"   Servidores: {len(self.guilds)}")
        # Reanclar vistas persistentes (mina)
        try:
            from backend.services.discord_bot.economy.mine import MineView
            await MineView.register_persistent(self)
        except Exception as exc:
            print(f"⚠️ No se pudo registrar la vista persistente de mina: {exc}")
        await self._cleanup_deleted_earning_channels_all_guilds()
        await self._backfill_existing_discord_progress()
        if self._external_economy_events_task is None or self._external_economy_events_task.done():
            self._external_economy_events_task = asyncio.create_task(self._external_economy_events_loop())
            print("📣 Notificador de economía externa activado")
        if self._voice_earning_task is None or self._voice_earning_task.done():
            self._voice_earning_task = asyncio.create_task(self._voice_earning_loop())
            print("🎙️ Earning por llamada activado")
        print()

    async def _external_economy_events_loop(self):
        """Loop que consume eventos de economía externa (YouTube y otras plataformas)."""
        while not self.is_closed():
            try:
                events = await asyncio.to_thread(pop_external_platform_progress_events, 100)
                for event in events:
                    platform = str(event.get("platform") or "unknown")
                    platform_user_id = str(event.get("platform_user_id") or "unknown")
                    previous_balance = float(event.get("previous_balance") or 0)
                    new_balance = float(event.get("new_balance") or 0)

                    await notify_external_platform_progress_all_guilds(
                        bot=self,
                        platform=platform,
                        platform_user_id=platform_user_id,
                        previous_balance=previous_balance,
                        new_balance=new_balance,
                    )
            except Exception as e:
                print(f"⚠️ Error en external economy events loop: {e}")

            await asyncio.sleep(3)

    async def _cleanup_deleted_earning_channels_all_guilds(self) -> None:
        """Limpia earning_channels huérfanos (canales borrados) en todos los servidores."""
        total_removed = 0
        for guild in self.guilds:
            try:
                valid_channel_ids = [channel.id for channel in guild.text_channels]
                economy_config = get_economy_config(guild.id)
                removed = economy_config.prune_deleted_earning_channels(valid_channel_ids)
                total_removed += removed
                if removed > 0:
                    print(
                        f"🧹 Earning channels limpiados en {guild.name}: {removed} canal(es) borrado(s) removido(s)"
                    )
            except Exception as exc:
                print(f"⚠️ Error limpiando earning channels en guild {guild.id}: {exc}")

        if total_removed > 0:
            print(f"🧹 Limpieza total de earning channels completada: {total_removed} eliminado(s)")

    async def _backfill_existing_discord_progress(self) -> None:
        """
        Detecta usuarios existentes con saldo y dispara catch-up de hitos pendientes.
        Esto permite marcar/notificar automáticamente usuarios que ya tienen 100, 400, 590, etc.
        """
        processed = 0
        for guild in self.guilds:
            try:
                for member in guild.members:
                    if member.bot:
                        continue

                    balance_info = await asyncio.to_thread(get_user_balance_by_discord_id, str(member.id))
                    if not balance_info or not balance_info.get("user_exists"):
                        continue

                    current_balance = float(balance_info.get("global_points") or 0)
                    if current_balance <= 0:
                        continue

                    await notify_economy_progress_if_needed(
                        bot=self,
                        guild_id=guild.id,
                        discord_user_id=member.id,
                        previous_balance=0,
                        new_balance=current_balance,
                    )
                    processed += 1
            except Exception as exc:
                print(f"⚠️ Error en backfill de logros para guild {guild.id}: {exc}")

        if processed > 0:
            print(f"📈 Backfill de logros ejecutado para {processed} usuario(s)")
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Hook que se ejecuta ANTES de cualquier comando"""
        try:
            # Auto-registrar usuario en DB
            await self._auto_register_user(interaction.user)
        except Exception as e:
            print(f"⚠️ Error registrando usuario en comando: {e}")
        
        return True
    
    async def on_message(self, message: discord.Message):
        """Listener - Se ejecuta en cada mensaje"""
        # Ignorar mensajes del bot
        if message.author.bot:
            return
        
        # Ignorar si no es en un servidor
        if not message.guild:
            return
        
        try:
            # Auto-registrar usuario
            await self._auto_register_user(message.author)
            
            # Verificar si es en earning_channel
            if await self._is_earning_channel(message.guild.id, message.channel.id):
                result = await asyncio.to_thread(
                    process_message_earning,
                    str(message.author.id),
                    message.guild.id,
                    message.channel.id,
                )
                if result.get("awarded"):
                    points_added = float(result.get("points_added") or 0)
                    new_points = float(result.get("global_points") or 0)
                    previous_points = new_points - points_added

                    print(
                        "💬 {user} en #{channel}: +{added} puntos (global: {global_points})".format(
                            user=message.author,
                            channel=message.channel.name,
                            added=result.get("points_added"),
                            global_points=result.get("global_points"),
                        )
                    )
                    await notify_economy_progress_if_needed(
                        bot=self,
                        guild_id=message.guild.id,
                        discord_user_id=message.author.id,
                        previous_balance=previous_points,
                        new_balance=new_points,
                    )
        
        except Exception as e:
            print(f"⚠️ Error en on_message: {e}")
        
        # IMPORTANTE: Procesar comandos normales
        await self.process_commands(message)

    async def _voice_earning_loop(self):
        """Loop que detecta usuarios en llamada y aplica earning por intervalo."""
        while not self.is_closed():
            try:
                await self._process_voice_earning_tick()
            except Exception as e:
                print(f"⚠️ Error en voice earning loop: {e}")

            await asyncio.sleep(self.voice_earning_poll_seconds)

    async def _process_voice_earning_tick(self):
        """Procesa un ciclo de earning para usuarios conectados en canales de voz."""
        for guild in self.guilds:
            for voice_channel in guild.voice_channels:
                for member in voice_channel.members:
                    if member.bot:
                        continue

                    voice_state = member.voice
                    if voice_state is None:
                        continue
                    if voice_state.afk:
                        continue

                    result = await asyncio.to_thread(
                        process_voice_earning_in_channel,
                        str(member.id),
                        guild.id,
                        voice_channel.id,
                    )

                    if result.get("awarded"):
                        points_added = float(result.get("points_added") or 0)
                        new_points = float(result.get("global_points") or 0)
                        previous_points = new_points - points_added

                        print(
                            "🎙️ {user} en llamada #{channel}: +{added} puntos (global: {global_points})".format(
                                user=member,
                                channel=voice_channel.name,
                                added=result.get("points_added"),
                                global_points=result.get("global_points"),
                            )
                        )
                        await notify_economy_progress_if_needed(
                            bot=self,
                            guild_id=guild.id,
                            discord_user_id=member.id,
                            previous_balance=previous_points,
                            new_balance=new_points,
                        )
    
    async def _auto_register_user(self, user: discord.User):
        """
        Auto-registra un usuario en la DB si no existe.
        Descarga avatar automáticamente.
        
        Args:
            user: discord.User a registrar
        """
        try:
            avatar_url = str(user.avatar.url) if user.avatar else None
            
            user_obj, discord_profile, is_new = await asyncio.to_thread(
                get_or_create_discord_user,
                str(user.id),
                user.name,
                avatar_url
            )
            
            if is_new:
                print(f"✨ Nuevo usuario registrado: {user.name} (ID: {user.id})")
            
            # Descargar avatar si existe
            if avatar_url and user_obj and user_obj.user_id:
                try:
                    await asyncio.to_thread(
                        DiscordAvatarPackager.download_and_update_avatar,
                        user_obj.user_id,
                        str(user.id),
                        avatar_url
                    )
                except Exception as e:
                    print(f"⚠️  Error descargando avatar para {user.name}: {e}")
        
        except Exception as e:
            print(f"⚠️ Error registrando usuario en comando: {e}")
            print(f"❌ Error registrando usuario {user.name}: {e}")
    
    async def _is_earning_channel(self, guild_id: int, channel_id: int) -> bool:
        """
        Verifica si un canal es earning_channel.
        
        Args:
            guild_id: ID del servidor
            channel_id: ID del canal
            
        Returns:
            bool: True si es earning_channel
        """
        try:
            guild = self.get_guild(int(guild_id))
            valid_channel_ids = [channel.id for channel in guild.text_channels] if guild else []

            economy = get_economy_config(guild_id)
            if valid_channel_ids:
                economy.prune_deleted_earning_channels(valid_channel_ids)

            earning_channels = economy.get_earning_channels()
            return channel_id in earning_channels
        except Exception as e:
            print(f"⚠️ Error verificando earning_channel: {e}")
            return False

    async def close(self):
        """Cierre limpio del bot y tareas en background."""
        if self._external_economy_events_task and not self._external_economy_events_task.done():
            self._external_economy_events_task.cancel()
            try:
                await self._external_economy_events_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"⚠️ Error cerrando external economy events task: {e}")
            finally:
                self._external_economy_events_task = None

        if self._voice_earning_task and not self._voice_earning_task.done():
            self._voice_earning_task.cancel()
            try:
                await self._voice_earning_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"⚠️ Error cerrando voice earning task: {e}")
            finally:
                self._voice_earning_task = None

        await super().close()


def create_bot(token: str = None, prefix: str = "!") -> PowerBotDiscord:
    """
    Crea una instancia del bot con configuración básica.
    
    Args:
        token: Token de Discord (opcional, se carga de .env si no se proporciona)
        prefix: Prefix de comandos
    
    Returns:
        PowerBotDiscord: Instancia del bot
    """
    # Cargar variables de entorno
    env_path = Path(__file__).parent.parent.parent / "keys" / ".env"
    load_dotenv(env_path)
    
    if token is None:
        token = os.getenv("DISCORD_TOKEN")
    
    if not token or token == "TU_TOKEN_AQUI":
        raise ValueError("❌ Token de Discord no configurado en keys/.env")
    
    # Obtener prefix de .env si existe
    env_prefix = os.getenv("DISCORD_PREFIX", prefix)
    
    bot = PowerBotDiscord(prefix=env_prefix)
    
    return bot


async def start_bot(token: str = None, prefix: str = "!"):
    """
    Inicia el bot de Discord.
    
    Args:
        token: Token de Discord (opcional)
        prefix: Prefix de comandos
    """
    bot = create_bot(token, prefix)
    
    try:
        await bot.start(token or os.getenv("DISCORD_TOKEN"))
    except KeyboardInterrupt:
        print("\n⚠️ Deteniendo bot...")
        await bot.close()
    except Exception as e:
        print(f"❌ Error al iniciar bot: {e}")
        raise


# Ejecución directa para pruebas
if __name__ == "__main__":
    print("🤖 PowerBot Discord - Modo de prueba")
    print("=" * 50)
    
    try:
        asyncio.run(start_bot())
    except ValueError as e:
        print(f"\n{e}")
        print("\n📝 Configura tu token en: backend/keys/.env")
        print("   DISCORD_TOKEN=tu_token_aqui")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Bot detenido")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        sys.exit(1)
