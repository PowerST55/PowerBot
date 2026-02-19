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
		
		# 3. Verificar autorun de YouTube (con protección)
		try:
			from backend.console.commands.commands_youtube import _load_config
			config = _load_config()
			if config.get("youtube", {}).get("autorun", False):
				console.print("[info]🎬 YouTube autorun activado - Conectando...[/info]")
				try:
					from backend.services.youtube_api import YouTubeAPI
					from backend.console.commands.commands_youtube import _set_youtube
					
					yt = YouTubeAPI()
					if yt.connect():
						_set_youtube(yt)
						console.print("[success]✓ YouTube conectado automáticamente[/success]")
					else:
						console.print("[warning]⚠ No se pudo conectar a YouTube automáticamente[/warning]")
				except Exception as e:
					console.print(f"[warning]⚠ Error al conectar YouTube: {e}[/warning]")
					logger.exception("YouTube autorun failed")
		except Exception as e:
			console.print(f"[warning]⚠ Error cargando config de YouTube: {e}[/warning]")
			logger.exception("Error loading YouTube config")
		
		# 4. Importar e iniciar la consola interactiva
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

