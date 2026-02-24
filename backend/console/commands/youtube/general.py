"""
Comandos de YouTube API para la consola interactiva.
"""

import json
import asyncio
from pathlib import Path

# Lazy loading
_console = None
_youtube_instance = None
_youtube_listener = None
_chat_id_manager = None

CONFIG_PATH = Path(__file__).resolve().parents[3] / "data" / "bot_config.json"


def _get_console():
    """Obtiene la consola."""
    global _console
    if _console is None:
        from backend.core import get_console
        _console = get_console()
    return _console


def _get_youtube():
    """Obtiene la instancia de YouTube API."""
    global _youtube_instance
    return _youtube_instance


def _set_youtube(instance):
    """Establece la instancia de YouTube API."""
    global _youtube_instance
    _youtube_instance = instance


def _get_listener():
    """Obtiene la instancia del listener."""
    global _youtube_listener
    return _youtube_listener


def _set_listener(instance):
    """Establece la instancia del listener."""
    global _youtube_listener
    _youtube_listener = instance


def _get_chat_id_manager():
    """Obtiene la instancia del ChatIdManager."""
    global _chat_id_manager
    return _chat_id_manager


def _set_chat_id_manager(instance):
    """Establece la instancia del ChatIdManager."""
    global _chat_id_manager
    _chat_id_manager = instance


def _load_config() -> dict:
    """Carga la configuración del bot."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"youtube": {"autorun": False}}


def _save_config(config: dict) -> None:
    """Guarda la configuración del bot."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


class CommandContext:
    """Contexto de comando."""
    def __init__(self, args: list):
        self.args = args
        self.output = []

    def print(self, message: str) -> None:
        self.output.append(("info", message))

    def error(self, message: str) -> None:
        self.output.append(("error", message))

    def warning(self, message: str) -> None:
        self.output.append(("warning", message))

    def success(self, message: str) -> None:
        self.output.append(("success", message))
    
    def render(self) -> None:
        """Renderiza todos los mensajes."""
        console = _get_console()
        for msg_type, message in self.output:
            console.print(f"[{msg_type}]{message}[/{msg_type}]")


# ============================================================================
# COMANDOS DE YOUTUBE
# ============================================================================

async def _shutdown_yapi_runtime(console) -> list[str]:
    """Apaga todo el runtime de YouTube sin borrar token."""
    yt = _get_youtube()
    listener = _get_listener()
    chat_manager = _get_chat_id_manager()
    actions: list[str] = []

    if listener and listener.is_running:
        await listener.stop()
        actions.append("Listener detenido")
    if listener:
        _set_listener(None)

    if chat_manager and chat_manager.is_monitoring:
        await chat_manager.stop_monitoring()
        actions.append("Monitoreo detenido")
    if chat_manager:
        _set_chat_id_manager(None)

    if yt and yt.is_connected():
        yt.disconnect()
        actions.append("API desconectada")
    if yt:
        _set_youtube(None)

    return actions

async def cmd_youtube_yapi(ctx: CommandContext) -> None:
    """
    Comando alternable ON/OFF del sistema YouTube.
    Si está apagado, conecta API e inicia listener.
    Si está encendido, apaga listener/monitoreo/API.
    Uso: yapi
    """
    console = _get_console()
    yt = _get_youtube()
    listener = _get_listener()
    chat_manager = _get_chat_id_manager()

    is_active = bool(
        (listener and listener.is_running)
        or (chat_manager and chat_manager.is_monitoring)
        or (yt and yt.is_connected())
    )

    if is_active:
        try:
            console.print("[info]🛑 YAPI activo detectado, apagando sistema...[/info]")
            actions = await _shutdown_yapi_runtime(console)

            console.print("\n" + "=" * 60)
            console.print("[bold yellow]🛑 YOUTUBE API DESACTIVADO[/bold yellow]")
            console.print("=" * 60)
            console.print("")
            ctx.success("✅ YAPI apagado correctamente")
            if actions:
                for action in actions:
                    ctx.print(f"• {action}")
            else:
                ctx.print("• No había procesos activos para detener")
            ctx.print("")
            ctx.print("💡 Ejecuta 'yapi' nuevamente para encenderlo")
            console.print("")
        except Exception as e:
            ctx.error(f"❌ Error al apagar YAPI: {str(e)}")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return
    
    try:
        # Paso 1: Conectar YouTube API si no está conectado
        if not yt or not yt.is_connected():
            console.print("[info]🔌 Conectando YouTube API...[/info]")
            
            from backend.services.youtube_api import YouTubeAPI
            yt = YouTubeAPI()
            
            if not yt.connect():
                ctx.error("No se pudo conectar a YouTube API")
                ctx.print("Verifica tus credenciales en backend/keys/")
                return
            
            _set_youtube(yt)
            console.print("[success]✅ YouTube API conectado[/success]")
        else:
            console.print("[info]✅ YouTube API ya está conectado[/info]")
        
        # Paso 2: Crear ChatIdManager
        chat_manager = _get_chat_id_manager()
        if not chat_manager:
            from backend.services.youtube_api import ChatIdManager
            chat_manager = ChatIdManager(yt.client, check_interval=60)
            _set_chat_id_manager(chat_manager)
            console.print("[info]📋 ChatIdManager creado[/info]")
        
        # Paso 3: Buscar transmisión en vivo (siempre forzar actualización)
        console.print("[info]🔍 Buscando transmisión en vivo...[/info]")
        live_chat_id = chat_manager.update_chat_id(force_fetch=True)
        
        if not live_chat_id:
            console.print("\n" + "="*60)
            ctx.warning("⚠️  No hay transmisión en vivo activa")
            console.print("="*60)
            console.print("")
            ctx.print("💡 Acciones disponibles:")
            ctx.print("   • Inicia una transmisión en YouTube")
            ctx.print("   • Ejecuta 'yapi' nuevamente cuando haya transmisión")
            ctx.print("   • Usa 'yt status' para verificar el estado")
            console.print("")
            return
        
        console.print(f"[success]✅ Transmisión encontrada: {live_chat_id[:20]}...[/success]")
        
        # Paso 4: Crear y configurar listener
        from backend.services.youtube_api import (
            YouTubeListener,
            console_message_handler,
            command_processor_handler
        )
        
        listener = YouTubeListener(yt.client, live_chat_id)
        
        # Agregar handlers
        listener.add_message_handler(console_message_handler)

        async def _earning_handler(message):
            try:
                from backend.services.youtube_api.economy.earning import process_message_earning
                process_message_earning(
                    youtube_channel_id=message.author_channel_id,
                    live_chat_id=live_chat_id,
                    source_id=message.id or None,
                )
            except Exception as exc:
                console.print(f"[warning]⚠ Error en earning YouTube: {exc}[/warning]")

        listener.add_message_handler(_earning_handler)

        async def _command_handler(message):
            try:
                await command_processor_handler(message, yt.client, live_chat_id)
            except Exception as exc:
                console.print(f"[warning]⚠ Error en comandos de chat: {exc}[/warning]")

        listener.add_message_handler(_command_handler)
        
        console.print("[info]🎧 Configurando listener de mensajes...[/info]")
        console.print("[info]👁️  Chat ID fijo mientras el listener esté activo[/info]")
        
        # Paso 6: Iniciar listener
        await listener.start()
        _set_listener(listener)
        
        # Mensaje de éxito
        console.print("\n" + "="*60)
        console.print("[bold green]🎬 YOUTUBE API ACTIVO - ESCUCHANDO CHAT[/bold green]")
        console.print("="*60)
        console.print("")
        ctx.success("✅ Sistema configurado correctamente")
        ctx.print("📡 Listener de mensajes activo")
        ctx.print("🔄 Chat ID queda fijo hasta reiniciar yapi")
        ctx.print("")
        ctx.print("💡 Comandos disponibles:")
        ctx.print("   • 'yt status' - Ver estado del sistema")
        ctx.print("   • 'yt stop_listener' - Detener el listener")
        console.print("")
        
    except Exception as e:
        ctx.error(f"❌ Error al iniciar YAPI: {str(e)}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


async def cmd_youtube_logout(ctx: CommandContext) -> None:
    """
    Cierra sesión de YouTube y borra el token de autenticación.
    Uso: yt logout
    """
    console = _get_console()
    yt = _get_youtube()
    listener = _get_listener()
    chat_manager = _get_chat_id_manager()
    
    try:
        # Paso 1: Detener listener si está activo
        if listener and listener.is_running:
            console.print("[info]🛑 Deteniendo listener activo...[/info]")
            await listener.stop()
            _set_listener(None)
        
        # Paso 2: Detener monitoreo si está activo
        if chat_manager and chat_manager.is_monitoring:
            console.print("[info]🛑 Deteniendo monitoreo de chat ID...[/info]")
            await chat_manager.stop_monitoring()
            _set_chat_id_manager(None)
        
        # Paso 3: Desconectar YouTube API
        if yt and yt.is_connected():
            console.print("[info]🔌 Desconectando YouTube API...[/info]")
            yt.disconnect()
            _set_youtube(None)
        
        # Paso 4: Borrar el archivo de token
        from pathlib import Path
        backend_dir = Path(__file__).resolve().parents[3]
        token_path = backend_dir / "keys" / "ytkey.json"
        
        if token_path.exists():
            console.print(f"[info]🗑️  Borrando token: {token_path.name}...[/info]")
            token_path.unlink()
            console.print("[success]✅ Token borrado exitosamente[/success]")
        else:
            console.print("[info]ℹ️  No se encontró token para borrar[/info]")
        
        # Mensaje final
        console.print("\n" + "="*60)
        console.print("[bold green]🚪 SESIÓN DE YOUTUBE CERRADA[/bold green]")
        console.print("="*60)
        console.print("")
        ctx.success("✅ Desconexión completa")
        ctx.print("📋 Estado:")
        ctx.print("   • Listener detenido")
        ctx.print("   • Monitoreo detenido")
        ctx.print("   • Token borrado")
        ctx.print("   • API desconectada")
        ctx.print("")
        ctx.print("💡 Para volver a conectar:")
        ctx.print("   • Ejecuta 'yapi' para reconectar")
        ctx.print("   • Se te pedirá autenticación nuevamente")
        console.print("")
        
    except Exception as e:
        ctx.error(f"❌ Error al cerrar sesión: {str(e)}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


async def cmd_youtube_autorun(ctx: CommandContext) -> None:
    """
    Configura/alterna el autorun de YouTube al iniciar el bot.
    Uso:
      yt autorun
      yt autorun true
      yt autorun false
      yt autorun = true
    """
    config = _load_config()
    
    # Asegurar que existe la sección youtube
    if "youtube" not in config:
        config["youtube"] = {}

    # Modo explícito: true/false con o sin '='
    explicit_value = None
    if ctx.args:
        normalized_args = [str(a).strip().lower() for a in ctx.args if str(a).strip()]
        if normalized_args and normalized_args[0] == "=":
            normalized_args = normalized_args[1:]

        if normalized_args:
            token = normalized_args[0]
            if token in {"=true", "true", "on", "1", "si", "sí"}:
                explicit_value = True
            elif token in {"=false", "false", "off", "0", "no"}:
                explicit_value = False
            else:
                ctx.error("Uso: yt autorun [true|false]")
                return

    if explicit_value is None:
        current = bool(config["youtube"].get("autorun", False))
        config["youtube"]["autorun"] = not current
    else:
        config["youtube"]["autorun"] = explicit_value
    
    # Guardar
    _save_config(config)
    
    new_value = config["youtube"]["autorun"]
    status = "activado" if new_value else "desactivado"
    
    ctx.success(f"YouTube autorun {status}")
    if new_value:
        ctx.print("YouTube se conectará automáticamente al iniciar el bot")
    else:
        ctx.print("YouTube NO se conectará automáticamente")


async def cmd_youtube_help(ctx: CommandContext) -> None:
    """
    Muestra ayuda de comandos de YouTube.
    Uso: yt help
    """
    from rich.panel import Panel
    console = _get_console()
    
    help_text = """
🎬 [bold cyan]Comandos de YouTube API:[/bold cyan]

    [yellow]yapi[/yellow]             - 🔁 Alterna ON/OFF del sistema YouTube (todo en uno)
    [yellow]yt autorun[/yellow]       - Alterna/define inicio automático (true|false)
  [yellow]yt listener[/yellow]      - Inicia el listener de mensajes del chat
  [yellow]yt stop_listener[/yellow] - Detiene el listener de mensajes
  [yellow]yt logout[/yellow]        - 🚪 Cierra sesión y borra el token
  [yellow]yt status[/yellow]        - Muestra el estado de YouTube y listener
  [yellow]yt help[/yellow]          - Muestra esta ayuda
    [yellow]yt set currency[/yellow]  - Configura nombre/símbolo de moneda YouTube
        [yellow]yt set gamble[/yellow]    - Configura límite/cooldown de !g y !gamble
        [yellow]yt set slots[/yellow]     - Configura límite/cooldown de !tm y aliases

[bold cyan]Características:[/bold cyan]
  • Gestión automática de Chat ID con persistencia
  • Monitoreo de nuevas transmisiones cada 60 segundos
  • Notificación cuando cambia la transmisión activa
  • Chat ID se guarda en [dim]data/youtube_bot/active_chat.json[/dim]

[bold cyan]Ejemplos:[/bold cyan]
    [dim]yapi[/dim]                  - Enciende si está OFF / apaga si está ON ⭐
    [dim]yt autorun true[/dim]       - Activa autorun (modo yapi completo)
    [dim]yt autorun false[/dim]      - Desactiva autorun
  [dim]yt listener[/dim]           - Comienza a escuchar mensajes del chat
  [dim]yt stop_listener[/dim]      - Detiene de escuchar mensajes
  [dim]yt logout[/dim]             - Cierra sesión y requiere nueva autenticación
  [dim]yt status[/dim]             - Ver estado de la conexión y monitoreo
    [dim]yt set currency pews 💎[/dim]- Configura la moneda de YouTube
        [dim]yt set gamble 150 0[/dim]    - Limita gamble a 150 y sin cooldown
        [dim]yt set slots 300 30[/dim]    - Limita slots a 300 con 30s cooldown
        [dim]!g 100 | !gamble 100[/dim]   - Comandos de gamble en YouTube chat
        [dim]!tm 50 | !tragamonedas 50[/dim]- Comandos de slots en YouTube chat
"""
    
    console.print(Panel(
        help_text,
        title="[bold cyan]YouTube API - Ayuda[/bold cyan]",
        border_style="cyan"
    ))


async def cmd_youtube_listener(ctx: CommandContext) -> None:
    """
    Inicia el listener de mensajes del chat.
    Uso: yt listener
    """
    console = _get_console()
    yt = _get_youtube()
    listener = _get_listener()
    chat_manager = _get_chat_id_manager()
    
    # Verificar si ya hay un listener corriendo
    if listener and listener.is_running:
        ctx.warning("El listener ya está en ejecución")
        return
    
    # Verificar conexión de YouTube
    if not yt or not yt.is_connected():
        ctx.error("YouTube API no está conectada")
        ctx.print("Primero activa el autorun o conecta manualmente")
        return
    
    try:
        # Crear ChatIdManager si no existe
        if not chat_manager:
            from backend.services.youtube_api import ChatIdManager
            chat_manager = ChatIdManager(yt.client, check_interval=60)
            _set_chat_id_manager(chat_manager)
            console.print("[info]📋 ChatIdManager creado[/info]")
        
        # Obtener chat ID (intenta cargar guardado primero)
        console.print("[info]🔍 Buscando transmisión en vivo...[/info]")
        
        # Intentar cargar chat ID guardado
        live_chat_id = chat_manager.load_saved_chat_id()
        if live_chat_id:
            console.print(f"[info]📂 Chat ID cargado desde archivo[/info]")
        
        # Actualizar/verificar chat ID
        live_chat_id = chat_manager.update_chat_id(force_fetch=True)
        
        if not live_chat_id:
            ctx.error("No hay transmisión en vivo activa")
            return
        
        console.print(f"[success]✓ Chat encontrado: {live_chat_id[:20]}...[/success]")
        
        # Crear listener
        from backend.services.youtube_api import (
            YouTubeListener,
            console_message_handler,
            command_processor_handler
        )
        
        listener = YouTubeListener(yt.client, live_chat_id)
        
        # Agregar handlers
        listener.add_message_handler(console_message_handler)

        async def _earning_handler(message):
            try:
                from backend.services.youtube_api.economy.earning import process_message_earning
                process_message_earning(
                    youtube_channel_id=message.author_channel_id,
                    live_chat_id=live_chat_id,
                    source_id=message.id or None,
                )
            except Exception as exc:
                console.print(f"[warning]⚠ Error en earning YouTube: {exc}[/warning]")

        listener.add_message_handler(_earning_handler)

        async def _command_handler(message):
            await command_processor_handler(message, yt.client, live_chat_id)

        listener.add_message_handler(_command_handler)
        
        # No iniciar monitoreo: el chat ID queda fijo mientras el listener esté activo
        
        # Iniciar listener
        await listener.start()
        _set_listener(listener)
        
        console.print("\n" + "="*60)
        ctx.success("Listener iniciado - Escuchando mensajes del chat")
        console.print("="*60 + "\n")
        
    except Exception as e:
        ctx.error(f"Error al iniciar listener: {str(e)}")


async def cmd_youtube_stop_listener(ctx: CommandContext) -> None:
    """
    Detiene el listener de mensajes.
    Uso: yt stop_listener
    """
    listener = _get_listener()
    chat_manager = _get_chat_id_manager()
    
    if not listener:
        ctx.warning("No hay ningún listener en ejecución")
        return
    
    if not listener.is_running:
        ctx.warning("El listener ya está detenido")
        return
    
    try:
        # Detener listener
        await listener.stop()
        _set_listener(None)
        
        # Detener monitoreo de chat ID
        if chat_manager and chat_manager.is_monitoring:
            await chat_manager.stop_monitoring()
        
        ctx.success("Listener y monitoreo detenidos")
        
    except Exception as e:
        ctx.error(f"Error al detener listener: {str(e)}")


async def cmd_youtube_status(ctx: CommandContext) -> None:
    """
    Muestra el estado de YouTube API y listener.
    Uso: yt status
    """
    from rich.table import Table
    console = _get_console()
    
    yt = _get_youtube()
    listener = _get_listener()
    chat_manager = _get_chat_id_manager()
    config = _load_config()
    
    # Crear tabla
    table = Table(title="YouTube API Status", show_header=True, header_style="bold magenta")
    table.add_column("Propiedad", style="cyan", width=25)
    table.add_column("Valor", style="green")
    
    # Estado de conexión
    if yt and yt.is_connected():
        table.add_row("Estado API", "✅ Conectado")
        table.add_row("Credenciales", str(yt.config.credentials_path.name))
        table.add_row("Token", str(yt.config.token_path.name))
    else:
        table.add_row("Estado API", "❌ Desconectado")
    
    # Estado del ChatIdManager
    if chat_manager:
        status = chat_manager.get_status()
        table.add_row("ChatIdManager", "✅ Activo")
        table.add_row("Monitoreo", "✅ Activo" if status['is_monitoring'] else "❌ Inactivo")
        if status['current_chat_id']:
            table.add_row("Chat ID actual", status['current_chat_id'][:20] + "...")
        else:
            table.add_row("Chat ID actual", "Sin transmisión")
        table.add_row("Intervalo verificación", f"{status['check_interval']}s")
    else:
        table.add_row("ChatIdManager", "❌ No creado")
    
    # Estado del listener
    if listener and listener.is_running:
        stats = listener.get_stats()
        table.add_row("Listener", "✅ Activo")
        table.add_row("Mensajes procesados", str(stats['processed_messages_count']))
        table.add_row("Poll interval", f"{stats['poll_interval_ms']}ms")
    else:
        table.add_row("Listener", "❌ Inactivo")
    
    # Configuración
    autorun = config.get("youtube", {}).get("autorun", False)
    table.add_row("Autorun", "✅ Activado" if autorun else "❌ Desactivado")
    
    console.print(table)


# ============================================================================
# DICCIONARIO DE COMANDOS YOUTUBE
# ============================================================================

YOUTUBE_COMMANDS = {
    "yapi": cmd_youtube_yapi,
    "autorun": cmd_youtube_autorun,
    "listener": cmd_youtube_listener,
    "stop_listener": cmd_youtube_stop_listener,
    "logout": cmd_youtube_logout,
    "status": cmd_youtube_status,
    "help": cmd_youtube_help,
}
