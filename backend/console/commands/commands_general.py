"""
Comandos generales del sistema de consola.
"""
from typing import Dict, Callable, Any, Optional
import sys
import os
import subprocess
import asyncio

# Lazy loading de consola para evitar problemas de inicialización
_console = None
_command_loop: Optional[asyncio.AbstractEventLoop] = None

def _get_console():
	"""Obtiene la consola, inicializándola si es necesario."""
	global _console
	if _console is None:
		from backend.core import get_console
		_console = get_console()
	return _console


def set_command_event_loop(loop: asyncio.AbstractEventLoop) -> None:
	"""Establece el event loop principal para ejecutar comandos async."""
	global _command_loop
	_command_loop = loop


class CommandContext:
	"""Contexto de ejecución de un comando."""
	def __init__(self, args: list[str]):
		self.args = args
		self.output = []

	def print(self, message: str) -> None:
		"""Agregar mensaje al output."""
		self.output.append(("info", message))

	def error(self, message: str) -> None:
		"""Agregar error al output (rojo)."""
		self.output.append(("error", message))

	def warning(self, message: str) -> None:
		"""Agregar advertencia al output (amarillo)."""
		self.output.append(("warning", message))

	def success(self, message: str) -> None:
		"""Agregar éxito al output (verde)."""
		self.output.append(("success", message))
	
	def render(self) -> None:
		"""Renderiza todos los mensajes con colores usando la consola global."""
		console_instance = _get_console()
		for msg_type, message in self.output:
			if msg_type == "error":
				console_instance.print(f"[error][ERROR][/error] {message}")
			elif msg_type == "warning":
				console_instance.print(f"[warning][WARNING][/warning] {message}")
			elif msg_type == "success":
				console_instance.print(f"[success][SUCCESS][/success] {message}")
			else:
				console_instance.print(f"[info]{message}[/info]")





async def cmd_test(ctx: CommandContext) -> None:
	"""Comando test - imprime 'Hola mundo'"""
	ctx.print("Hola mundo")


async def cmd_colortest(ctx: CommandContext) -> None:
	"""Comando colortest - prueba todos los colores disponibles"""
	console_instance = _get_console()
	
	# Mostrar encabezado
	console_instance.print("\n" + "="*60)
	console_instance.print("[header]═══════════════════════════════════════════════════════[/header]")
	console_instance.print("[header]           PRUEBA DE COLORES - POWERBOT               [/header]")
	console_instance.print("[header]═══════════════════════════════════════════════════════[/header]")
	
	# Colores del tema personalizado
	console_instance.print("\n[header]Colores del Tema:[/header]")
	console_instance.print("[info]   ✓ INFO    [/info]  - Información general")
	console_instance.print("[success] ✓ SUCCESS  [/success] - Operación exitosa")
	console_instance.print("[warning] ⚠ WARNING  [/warning] - Advertencia")
	console_instance.print("[error]   ✗ ERROR    [/error]  - Error crítico")
	console_instance.print("[header]  HEADER   [/header] - Encabezado")
	console_instance.print("[debug]   DEBUG    [/debug]  - Información de depuración")
	console_instance.print("[muted]   MUTED    [/muted]  - Texto atenuado")
	
	# Colores estándar de Rich
	console_instance.print("\n[header]Colores Estándar de Rich:[/header]")
	colores_standard = [
		("red", "Rojo"),
		("green", "Verde"),
		("yellow", "Amarillo"),
		("blue", "Azul"),
		("magenta", "Magenta"),
		("cyan", "Cian"),
		("white", "Blanco"),
	]
	
	for color, nombre in colores_standard:
		console_instance.print(f"[bold {color}]■ {nombre:<15}[/bold {color}]", end="  ")
		console_instance.print(f"[{color}]■ {nombre} (bold)[/{color}]")
	
	# Combinaciones especiales
	console_instance.print("\n[header]Combinaciones Especiales:[/header]")
	console_instance.print("[bold green]✓ Éxito con énfasis[/bold green]")
	console_instance.print("[bold yellow]⚠ Advertencia con énfasis[/bold yellow]")
	console_instance.print("[bold red]✗ Error con énfasis[/bold red]")
	console_instance.print("[dim]Texto atenuado (dim)[/dim]")
	console_instance.print("[bold]Texto en negrita[/bold]")
	console_instance.print("[italic]Texto en itálica[/italic]")
	console_instance.print("[underline]Texto subrayado[/underline]")
	
	console_instance.print("\n[header]═══════════════════════════════════════════════════════[/header]")
	console_instance.print("[info]Fin de la prueba de colores[/info]\n")


async def cmd_help(ctx: CommandContext) -> None:
	"""Comando help - muestra los comandos disponibles"""
	ctx.print("Comandos disponibles:")
	ctx.print("  test           - Comando de prueba que imprime 'Hola mundo'")
	ctx.print("  colortest      - Prueba todos los colores disponibles")
	ctx.print("  clean          - Limpia la consola")
	ctx.print("  restart (rst)  - Reinicia el programa completamente")
	ctx.print("  web <subcmd>   - Control del servidor web")
	ctx.print("                   • web            - Alterna ON/OFF")
	ctx.print("                   • web on         - Enciende servidor web")
	ctx.print("                   • web off        - Apaga servidor web")
	ctx.print("                   • web status     - Estado del servidor web")
	ctx.print("                   • web autorun    - Alterna arranque automático")
	ctx.print("  store <subcmd> - Control del servicio store")
	ctx.print("                   • store          - Alterna ON/OFF")
	ctx.print("                   • store on       - Enciende servicio store")
	ctx.print("                   • store off      - Apaga servicio store")
	ctx.print("                   • store status   - Estado del servicio store")
	ctx.print("                   • store autorun  - Alterna arranque automático")
	ctx.print("  livefeed <subcmd>- Autoriza/rechaza acceso por IP")
	ctx.print("                   • livefeed status - Ver solicitud pendiente")
	ctx.print("                   • livefeed allow  - Autorizar última solicitud")
	ctx.print("                   • livefeed deny   - Rechazar última solicitud")
	ctx.print("  wsocket <subcmd>- Control del servidor websocket local")
	ctx.print("                   • wsocket        - Alterna ON/OFF")
	ctx.print("                   • wsocket autorun- Alterna arranque automático")
	ctx.print("                   • wsocket status - Estado actual")
	ctx.print("  discord <subcmd>- Control del bot de Discord")
	ctx.print("                   • discord        - Alterna ON/OFF")
	ctx.print("                   • discord on     - Enciende bot de Discord")
	ctx.print("                   • discord off    - Apaga bot de Discord")
	ctx.print("                   • discord status - Estado del bot de Discord")
	ctx.print("                   • discord autorun- Alterna arranque automático")
	ctx.print("  backup <subcmd> - Control del servicio backup")
	ctx.print("                   • backup         - Alterna ON/OFF")
	ctx.print("                   • backup on      - Enciende servicio backup")
	ctx.print("                   • backup off     - Apaga servicio backup")
	ctx.print("                   • backup status  - Estado del servicio backup")
	ctx.print("                   • backup autorun - Alterna arranque automático")
	ctx.print("                   • backup autosave interval <s>")
	ctx.print("                   • backup autosave list")
	ctx.print("                   • backup autosave run")
	ctx.print("                   • backup autosave recovery <index>")
	ctx.print("                   • backup autosave delete <index>")
	ctx.print("  say <msg>      - Envia un mensaje a YouTube Live")
	ctx.print("  yapi           - 🚀 Conecta YouTube e inicia listener (TODO EN UNO)")
	ctx.print("  yt <subcmd>    - Comandos de YouTube API")
	ctx.print("                   • yt autorun      - Alterna inicio automático")
	ctx.print("                   • yt listener     - Inicia listener de chat")
	ctx.print("                   • yt stop_listener- Detiene listener")
	ctx.print("                   • yt logout       - Cierra sesión y borra token")
	ctx.print("                   • yt status       - Estado de YouTube")
	ctx.print("                   • yt set currency - Configura moneda de YouTube")
	ctx.print("                   • yt set gamble   - Configura límite/cooldown de gamble")
	ctx.print("                   • yt set slots    - Configura límite/cooldown de slots")
	ctx.print("                   • yt help         - Ayuda de YouTube")
	ctx.print("  help           - Muestra esta ayuda")
	ctx.print("  exit           - Salir del programa")


async def cmd_clean(ctx: CommandContext) -> None:
	"""Comando clean - limpia la consola."""
	# Limpiar la consola usando el método nativo del SO
	os.system('cls' if os.name == 'nt' else 'clear')
	ctx.print("Consola limpiada")


async def cmd_restart(ctx: CommandContext) -> None:
	"""Comando restart - cierra y reinicia el programa completamente."""
	ctx.print("Reiniciando PowerBot...")
	
	# Obtener el path del script principal
	script_dir = os.path.dirname(os.path.abspath(__file__))
	project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
	app_path = os.path.join(project_root, "backend", "app.py")
	
	try:
		# Iniciar nueva instancia
		subprocess.Popen([sys.executable, app_path])
		ctx.print("Nueva instancia iniciada")
		# Señal para salir
		await cmd_exit(ctx)
	except Exception as e:
		ctx.error(f"Error al reiniciar: {e}")


async def cmd_exit(ctx: CommandContext) -> None:
	"""Comando exit - señal para salir"""
	ctx.print("Saliendo...")


async def cmd_yt(ctx: CommandContext) -> None:
	"""Comando yt - ejecuta subcomandos de YouTube API"""
	from .youtube import YOUTUBE_COMMANDS
	
	if not ctx.args:
		# Sin argumentos, mostrar ayuda
		if "help" in YOUTUBE_COMMANDS:
			await YOUTUBE_COMMANDS["help"](ctx)
		return
	
	subcommand = ctx.args[0].lstrip("/").lower()
	yt_ctx = CommandContext(ctx.args[1:])
	
	if subcommand not in YOUTUBE_COMMANDS:
		yt_ctx.error(f"Subcomando desconocido: 'yt {subcommand}'")
		yt_ctx.print("Usa 'yt help' para ver comandos disponibles")
		yt_ctx.render()
		return
	
	# Ejecutar el subcomando de YouTube
	await YOUTUBE_COMMANDS[subcommand](yt_ctx)
	yt_ctx.render()


async def cmd_yapi(ctx: CommandContext) -> None:
	"""Comando yapi - Conecta YouTube API e inicia el listener automáticamente"""
	from .youtube import YOUTUBE_COMMANDS
	
	# Ejecutar el comando yapi de YouTube
	if "yapi" in YOUTUBE_COMMANDS:
		await YOUTUBE_COMMANDS["yapi"](ctx)
	else:
		ctx.error("Comando yapi no disponible")


async def cmd_web(ctx: CommandContext) -> None:
	"""Comando web - ejecuta subcomandos para controlar el servidor web."""
	from .web.general import cmd_web as cmd_web_impl
	await cmd_web_impl(ctx)


async def cmd_store(ctx: CommandContext) -> None:
	"""Comando store - ejecuta subcomandos para controlar el servicio store."""
	from .store.general import cmd_store as cmd_store_impl
	await cmd_store_impl(ctx)


async def cmd_wsocket(ctx: CommandContext) -> None:
	"""Comando wsocket - ejecuta subcomandos para websocket local."""
	from .websocket.general import cmd_wsocket as cmd_wsocket_impl
	await cmd_wsocket_impl(ctx)


async def cmd_discord(ctx: CommandContext) -> None:
	"""Comando discord - ejecuta subcomandos para controlar el bot de Discord."""
	from .discord_bot.general import cmd_discord as cmd_discord_impl
	await cmd_discord_impl(ctx)


async def cmd_backup(ctx: CommandContext) -> None:
	"""Comando backup - ejecuta subcomandos para controlar el servicio backup."""
	from .backup.general import cmd_backup as cmd_backup_impl
	await cmd_backup_impl(ctx)


async def cmd_livefeed(ctx: CommandContext) -> None:
	"""Comando livefeed - gestiona whitelist de IP para livefeed."""
	from .web.livefeed.ip_whitelist import cmd_livefeed as cmd_livefeed_impl
	await cmd_livefeed_impl(ctx)


async def cmd_say(ctx: CommandContext) -> None:
	"""Comando say - envia un mensaje a YouTube Live."""
	from .youtube.general import _get_listener, _get_youtube
	from backend.services.youtube_api.send_message import send_chat_message

	if not ctx.args:
		ctx.error("Uso: say <mensaje>")
		return

	message_text = " ".join(ctx.args).strip()
	if not message_text:
		ctx.error("El mensaje no puede estar vacio")
		return

	yt = _get_youtube()
	listener = _get_listener()

	if not yt or not yt.is_connected():
		ctx.error("YouTube API no esta conectada")
		ctx.print("Primero ejecuta yapi o activa autorun")
		return

	if not listener or not listener.is_running:
		ctx.error("El listener no esta activo")
		ctx.print("Primero ejecuta yapi para iniciar el listener")
		return

	ok = await send_chat_message(yt.client, listener.live_chat_id, message_text)
	if ok:
		ctx.success("Mensaje enviado a YouTube Live")
	else:
		ctx.error("No se pudo enviar el mensaje")


# Registro de comandos con alias
_COMMAND_FUNCTIONS: Dict[str, Callable[[CommandContext], Any]] = {
	"test": cmd_test,
	"colortest": cmd_colortest,
	"clean": cmd_clean,
	"restart": cmd_restart,
	"say": cmd_say,
	"yt": cmd_yt,
	"youtube": cmd_yt,
	"yapi": cmd_yapi,
	"web": cmd_web,
	"store": cmd_store,
	"discord": cmd_discord,
	"backup": cmd_backup,
	"livefeed": cmd_livefeed,
	"wsocket": cmd_wsocket,
	"help": cmd_help,
	"exit": cmd_exit,
}

# Definir alias para comandos
_COMMAND_ALIASES = {
	"rst": "restart",
	"cls": "clean",
	"clear": "clean",
	"limpiar": "clean",
	"e": "exit",
	"salir": "exit",
}

# Construir el dict COMMANDS con comandos y alias
COMMANDS: Dict[str, Callable[[CommandContext], Any]] = {}
for cmd_name, cmd_func in _COMMAND_FUNCTIONS.items():
	COMMANDS[cmd_name] = cmd_func

for alias, cmd_name in _COMMAND_ALIASES.items():
	if cmd_name in _COMMAND_FUNCTIONS:
		COMMANDS[alias] = _COMMAND_FUNCTIONS[cmd_name]


async def execute_command(command_line: str) -> tuple[Any, bool]:
	"""
	Ejecuta un comando y retorna (ctx, should_exit).
	
	Args:
		command_line: Línea completa del comando
	
	Returns:
		(CommandContext, should_exit: bool)
	"""
	parts = command_line.strip().split()
	if not parts:
		return None, False

	cmd_name = parts[0].lower()
	args = parts[1:]

	if cmd_name not in COMMANDS:
		ctx = CommandContext(args)
		ctx.error(f"Comando desconocido: '{cmd_name}'. Usa 'help' para ver los comandos disponibles.")
		return ctx, False

	try:
		ctx = CommandContext(args)
		await COMMANDS[cmd_name](ctx)
		should_exit = cmd_name == "exit"
		return ctx, should_exit
	except Exception as e:
		ctx = CommandContext(args)
		ctx.error(f"Error ejecutando comando '{cmd_name}': {str(e)}")
		return ctx, False


def execute_command_sync(command_line: str) -> tuple[Any, bool]:
	"""
	Versión sincrónica de execute_command.
	Ejecuta comandos async usando asyncio.run().
	
	Args:
		command_line: Línea completa del comando
	
	Returns:
		(CommandContext, should_exit: bool)
	"""
	parts = command_line.strip().split()
	if not parts:
		return None, False

	cmd_name = parts[0].lower()
	args = parts[1:]

	if cmd_name not in COMMANDS:
		ctx = CommandContext(args)
		ctx.error(f"Comando desconocido: '{cmd_name}'. Usa 'help' para ver los comandos disponibles.")
		return ctx, False

	try:
		ctx = CommandContext(args)
		# Ejecutar en el loop principal si está disponible
		if _command_loop and _command_loop.is_running():
			future = asyncio.run_coroutine_threadsafe(COMMANDS[cmd_name](ctx), _command_loop)
			future.result()
		else:
			# Fallback: crear un loop temporal
			asyncio.run(COMMANDS[cmd_name](ctx))
		should_exit = cmd_name == "exit"
		return ctx, should_exit
	except Exception as e:
		ctx = CommandContext(args)
		ctx.error(f"Error ejecutando comando '{cmd_name}': {str(e)}")
		return ctx, False

