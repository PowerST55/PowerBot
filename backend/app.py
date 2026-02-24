"""
PowerBot - Sistema de consola interactivo asincrónico.

Frontend principal que enseña mejor el flujo de la aplicación:
1. Bootstrap: Instala dependencias y verifica el entorno
2. Consola: Inicia la interfaz interactiva
"""

import asyncio
import sys
import logging
from pathlib import Path

# Configurar logging (usando la consola centralizada de colores)
logging.basicConfig(
	level=logging.INFO,
	format="%(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> int:
	"""
	Función principal de PowerBot con protección máxima contra crashes.
	
	Retorna:
		int: Código de salida (0 = éxito, 1 = error)
	"""
	from backend.bootstrap import bootstrap, _reexec_in_venv
	
	# Obtener la consola configurada
	try:
		from backend.core import get_console
		console = get_console()
	except Exception:
		# Fallback si la consola no está disponible
		class SimpleConsole:
			def print(self, msg):
				print(msg)
		console = SimpleConsole()  # type: ignore
	
	try:
		# 1. Reejecutar en venv si es necesario (solo al inicio)
		bootstrap_verbose = "--verbose" in sys.argv
		_reexec_in_venv(None, ".venv")  # type: ignore
		
		# 2. Ejecutar bootstrap
		if not bootstrap(verbose=bootstrap_verbose):
			console.print("[error]✗ Bootstrap falló[/error]")
			return 1
		
		# 3. Verificar autorun de YouTube (flujo completo tipo yapi)
		try:
			from backend.console.commands.youtube.general import _load_config, cmd_youtube_yapi, CommandContext
			config = _load_config()
			if config.get("youtube", {}).get("autorun", False):
				console.print("[info]🎬 YouTube autorun activado - iniciando flujo yapi...[/info]")
				try:
					autorun_ctx = CommandContext([])
					await cmd_youtube_yapi(autorun_ctx)
					console.print("[success]✓ YouTube autorun ejecutado[/success]")
				except Exception as e:
					console.print(f"[warning]⚠ Error en yapi autorun: {e}[/warning]")
					logger.exception("YouTube autorun failed")
		except Exception as e:
			console.print(f"[warning]⚠ Error cargando config de YouTube: {e}[/warning]")
			logger.exception("Error loading YouTube config")

		# 4. Verificar autorun de Web (y estado inicial consistente)
		try:
			from backend.console.commands.web.general import start_if_autorun as start_web_if_autorun
			web_ok, web_message = await start_web_if_autorun()
			if web_ok:
				console.print("[success]✓ Servidor web iniciado automáticamente[/success]")
			else:
				if "desactivado" not in str(web_message).lower():
					console.print(f"[warning]⚠ Web autorun: {web_message}[/warning]")
		except Exception as e:
			console.print(f"[warning]⚠ Error en autorun Web: {e}[/warning]")
			logger.exception("Web autorun failed")
		
		# 5. Verificar autorun de WebSocket
		try:
			from backend.console.commands.websocket.general import start_if_autorun
			ok, message = await start_if_autorun()
			if ok:
				console.print("[success]✓ WebSocket local iniciado automáticamente[/success]")
			else:
				if "desactivado" not in str(message).lower():
					console.print(f"[warning]⚠ WebSocket autorun: {message}[/warning]")
		except Exception as e:
			console.print(f"[warning]⚠ Error en autorun WebSocket: {e}[/warning]")
			logger.exception("WebSocket autorun failed")

		# 6. Verificar autorun de Discord
		try:
			from backend.console.commands.discord_bot.general import start_if_autorun as start_discord_if_autorun
			discord_ok, discord_message = await start_discord_if_autorun()
			if discord_ok:
				console.print("[success]✓ Bot de Discord iniciado automáticamente[/success]")
			else:
				if "desactivado" not in str(discord_message).lower():
					console.print(f"[warning]⚠ Discord autorun: {discord_message}[/warning]")
		except Exception as e:
			console.print(f"[warning]⚠ Error en autorun Discord: {e}[/warning]")
			logger.exception("Discord autorun failed")

		# 7. Importar e iniciar la consola interactiva
		# 7. Verificar autorun de Backup
		try:
			from backend.console.commands.backup.general import start_if_autorun as start_backup_if_autorun
			backup_ok, backup_message = await start_backup_if_autorun()
			if backup_ok:
				console.print("[success]✓ Servicio backup iniciado automáticamente[/success]")
			else:
				if "desactivado" not in str(backup_message).lower():
					console.print(f"[warning]⚠ Backup autorun: {backup_message}[/warning]")
		except Exception as e:
			console.print(f"[warning]⚠ Error en autorun Backup: {e}[/warning]")
			logger.exception("Backup autorun failed")

		# 8. Importar e iniciar la consola interactiva
		from backend.console.console import start_console
		
		console.print("[header]PowerBot iniciado[/header]")
		
		try:
			await start_console()
		except asyncio.CancelledError:
			console.print("\n[warning]⚠ Console fue cancelado[/warning]")
		except Exception as e:
			console.print(f"[error]✗ Error en consola: {type(e).__name__}: {e}[/error]")
			logger.exception("Console error")
		
		return 0
		
	except KeyboardInterrupt:
		console.print("\n[warning]⚠ Aplicación detenida por el usuario[/warning]")
		return 130  # Código estándar para interrupción por Ctrl+C
	except Exception as e:
		console.print(f"[error]✗ Error fatal: {type(e).__name__}: {e}[/error]")
		if "--verbose" in sys.argv:
			import traceback
			traceback.print_exc()
		logger.exception("Main function error")
		return 1


if __name__ == "__main__":
	# Asegurar que estamos en el directorio correcto
	backend_dir = Path(__file__).parent
	sys.path.insert(0, str(backend_dir.parent))
	
	# Ejecutar el programa con máxima protección
	exit_code = 1
	try:
		exit_code = asyncio.run(main())
	except KeyboardInterrupt:
		print("\n✗ Aplicación interrumpida por el usuario")
		exit_code = 130
	except SystemExit as e:
		# Permitir que sys.exit() funcione normalmente
		exit_code = e.code if e.code is not None else 1
	except Exception as e:
		# Catch-all final que NUNCA debería alcanzarse
		print(f"✗ Error CRÍTICO no manejado: {type(e).__name__}: {e}")
		import traceback
		traceback.print_exc()
		exit_code = 1
	finally:
		# Asegúrate de que salimos con el código correcto
		sys.exit(exit_code if isinstance(exit_code, int) else 1)

