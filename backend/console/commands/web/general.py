"""
Comandos de consola para controlar el servidor web.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from backend.services.web.config.autorun import create_web_autorun_manager
from backend.services.web.config.economy import create_web_economy_manager
from backend.services.web.config.toggle_on_off import create_web_toggle_manager

_console = None
_web_process: Optional[subprocess.Popen] = None
_web_config_manager = None
_web_economy_manager = None
_web_autorun_manager = None
_web_log_threads: list[threading.Thread] = []


def _can_run_web_module(python_executable: str) -> bool:
	"""Valida si el intérprete tiene dependencias mínimas para el servidor web."""
	try:
		result = subprocess.run(
			[python_executable, "-c", "import fastapi, uvicorn"],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
			check=False,
			timeout=6,
		)
		return result.returncode == 0
	except Exception:
		return False


def _pick_python_for_web(project_root: Path) -> str:
	"""Selecciona un intérprete funcional para arrancar el módulo web."""
	candidates = [
		sys.executable,
		str(project_root / ".venv" / "Scripts" / "python.exe"),
		str(project_root / "venv" / "Scripts" / "python.exe"),
	]

	seen: set[str] = set()
	for candidate in candidates:
		candidate = str(candidate)
		if not candidate or candidate in seen:
			continue
		seen.add(candidate)
		if not Path(candidate).exists():
			continue
		if _can_run_web_module(candidate):
			return candidate

	# Fallback al actual para mantener comportamiento previo
	return sys.executable


def _get_console():
	"""Obtiene la consola global."""
	global _console
	if _console is None:
		from backend.core import get_console
		_console = get_console()
	return _console


def _get_config_manager():
	"""Obtiene el manager de configuración del web toggle."""
	global _web_config_manager
	if _web_config_manager is None:
		_web_config_manager = create_web_toggle_manager()
	return _web_config_manager


def _get_economy_manager():
	"""Obtiene el manager de configuración de economía web."""
	global _web_economy_manager
	if _web_economy_manager is None:
		_web_economy_manager = create_web_economy_manager()
	return _web_economy_manager


def _get_autorun_manager():
	"""Obtiene el manager de autorun del servidor web."""
	global _web_autorun_manager
	if _web_autorun_manager is None:
		_web_autorun_manager = create_web_autorun_manager()
	return _web_autorun_manager


def _is_web_running() -> bool:
	"""Verifica si el proceso web lanzado por la consola sigue activo."""
	global _web_process
	return _web_process is not None and _web_process.poll() is None


def _get_access_urls() -> tuple[str, str, str]:
	"""Devuelve bind host/puerto y URL recomendada para navegador."""
	host = os.getenv("WEB_HOST", "0.0.0.0")
	port = os.getenv("WEB_PORT", "19131")
	browser_host = "127.0.0.1" if host == "0.0.0.0" else host
	browser_url = f"http://{browser_host}:{port}"
	return host, port, browser_url if browser_url else f"http://127.0.0.1:{port}"


def _stream_web_logs(pipe, stream_name: str) -> None:
	"""Lee logs del subproceso web y emite alertas relevantes a consola."""
	if pipe is None:
		return

	try:
		from backend.core import get_console
		console = get_console()
		for line in iter(pipe.readline, ""):
			if not line:
				break
			text = line.strip()
			if not text:
				continue
			if "[LIVEFEED_PENDING]" in text:
				console.print(f"[warning]⚠ {text}[/warning]")
			elif stream_name == "stderr" and "error" in text.lower():
				console.print(f"[warning]⚠ WEB: {text}[/warning]")
	except Exception:
		return


async def _start_web_process() -> tuple[bool, str]:
	"""Inicia el servidor web en un subproceso."""
	global _web_process

	if _is_web_running():
		return True, "El servidor web ya está encendido"

	project_root = Path(__file__).resolve().parents[4]
	env = os.environ.copy()
	env.setdefault("PYTHONUTF8", "1")
	env.setdefault("PYTHONIOENCODING", "utf-8")
	pythonpath = env.get("PYTHONPATH", "")
	root_str = str(project_root)
	if root_str not in pythonpath:
		env["PYTHONPATH"] = f"{root_str}{os.pathsep}{pythonpath}" if pythonpath else root_str
	python_executable = _pick_python_for_web(project_root)

	try:
		_web_process = subprocess.Popen(
			[python_executable, "-m", "backend.services.web.web_core"],
			cwd=str(project_root),
			env=env,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
		)
		await asyncio.sleep(0.8)
		if _web_process.poll() is not None:
			code = _web_process.returncode
			error_output = ""
			if _web_process.stderr is not None:
				try:
					error_output = (_web_process.stderr.read() or "").strip()
				except Exception:
					error_output = ""
			_web_process = None
			if error_output:
				error_line = error_output.splitlines()[-1]
				return False, f"No se pudo iniciar el servidor web (exit code: {code}): {error_line}"
			return False, f"No se pudo iniciar el servidor web (exit code: {code})"

		# Stream de logs para avisos livefeed pendientes
		_web_log_threads.clear()
		stdout_thread = threading.Thread(
			target=_stream_web_logs,
			args=(_web_process.stdout, "stdout"),
			daemon=True,
		)
		stderr_thread = threading.Thread(
			target=_stream_web_logs,
			args=(_web_process.stderr, "stderr"),
			daemon=True,
		)
		stdout_thread.start()
		stderr_thread.start()
		_web_log_threads.extend([stdout_thread, stderr_thread])
		return True, "Servidor web encendido"
	except Exception as exc:
		_web_process = None
		return False, f"Error iniciando servidor web: {exc}"


async def start_if_autorun() -> tuple[bool, str]:
	"""Inicia web automáticamente si autorun está activo.

	Si autorun está desactivado, fuerza persistencia OFF para que el primer
	comando `web` en la sesión encienda el servidor.
	"""
	autorun_manager = _get_autorun_manager()
	config_manager = _get_config_manager()

	if not autorun_manager.is_enabled():
		config_manager.set_enabled(False)
		return False, "Autorun web desactivado"

	ok, message = await _start_web_process()
	if ok:
		config_manager.set_enabled(True)
		return True, message

	config_manager.set_enabled(False)
	return False, message


def _stop_web_process() -> tuple[bool, str]:
	"""Detiene el servidor web si está activo."""
	global _web_process

	if not _is_web_running():
		_web_process = None
		return True, "El servidor web ya está apagado"

	try:
		_web_process.terminate()
		_web_process.wait(timeout=5)
	except Exception:
		try:
			_web_process.kill()
		except Exception:
			pass
	finally:
		try:
			if _web_process and _web_process.stdout:
				_web_process.stdout.close()
		except Exception:
			pass
		try:
			if _web_process and _web_process.stderr:
				_web_process.stderr.close()
		except Exception:
			pass
		_web_process = None

	return True, "Servidor web apagado"


async def cmd_web(ctx: Any) -> None:
	"""
	Comando principal para encender/apagar el servidor web.

	Uso:
	  web            -> alterna on/off
	  web on         -> enciende
	  web off        -> apaga
	  web status     -> muestra estado
	  web help       -> ayuda
	"""
	manager = _get_config_manager()
	action = ctx.args[0].lower() if ctx.args else "toggle"

	if action in {"help", "-h", "--help"}:
		ctx.print("Comandos web disponibles:")
		ctx.print("  web             - Alterna ON/OFF")
		ctx.print("  web on          - Enciende el servidor web")
		ctx.print("  web off         - Apaga el servidor web")
		ctx.print("  web status      - Estado actual del servidor web")
		ctx.print("  web autorun     - Alterna arranque automático")
		ctx.print("  web currency <nombre> <simbolo> - Configura moneda web")
		return

	if action == "autorun":
		autorun_manager = _get_autorun_manager()
		if len(ctx.args) > 1:
			token = str(ctx.args[1]).strip().lower()
			if token in {"true", "on", "1", "si", "sí"}:
				autorun_manager.set_enabled(True)
				new_state = True
			elif token in {"false", "off", "0", "no"}:
				autorun_manager.set_enabled(False)
				new_state = False
			else:
				ctx.error("Uso: web autorun [true|false]")
				return
		else:
			new_state = autorun_manager.toggle()
		status = "activado" if new_state else "desactivado"
		ctx.success(f"Web autorun {status}")
		ctx.print("Se aplicará al abrir el programa")
		return

	if action == "status":
		is_running = _is_web_running()
		cfg = manager.get_status()
		autorun_cfg = _get_autorun_manager().get_status()
		economy_cfg = _get_economy_manager().get_currency()
		host, port, browser_url = _get_access_urls()
		ctx.print("Estado del servidor web:")
		ctx.print(f"  • Proceso: {'ON' if is_running else 'OFF'}")
		ctx.print(f"  • Config persistida: {'ON' if cfg.get('web_enabled') else 'OFF'}")
		ctx.print(f"  • Autorun: {'ON' if autorun_cfg.get('autorun') else 'OFF'}")
		ctx.print(f"  • Moneda web: {economy_cfg.get('name')} ({economy_cfg.get('symbol')})")
		ctx.print(f"  • Bind: http://{host}:{port}")
		ctx.print(f"  • Abrir en navegador: {browser_url}")
		ctx.print("  • Nota: 0.0.0.0 no se usa directamente en navegador")
		ctx.print(f"  • Archivo config: {cfg.get('config_file')}")
		ctx.print(f"  • Archivo autorun: {autorun_cfg.get('config_file')}")
		ctx.print(f"  • Archivo economy: {economy_cfg.get('config_file')}")
		return

	if action == "currency":
		if len(ctx.args) < 3:
			ctx.error("Uso: web currency <nombre> <simbolo>")
			return

		currency_name = " ".join(ctx.args[1:-1]).strip()
		currency_symbol = ctx.args[-1].strip()

		if not currency_name or not currency_symbol:
			ctx.error("Uso: web currency <nombre> <simbolo>")
			return

		economy_manager = _get_economy_manager()
		economy_manager.set_currency(currency_name, currency_symbol)
		ctx.success(f"Moneda web actualizada: {currency_name} ({currency_symbol})")
		ctx.print(f"Archivo config: {economy_manager.get_currency().get('config_file')}")
		return

	if action in {"toggle", "switch"}:
		if _is_web_running() or manager.is_enabled():
			action = "off"
		else:
			action = "on"

	if action in {"on", "start", "1", "true"}:
		ok, message = await _start_web_process()
		if ok:
			manager.set_enabled(True)
			ctx.success(message)
			_, _, browser_url = _get_access_urls()
			ctx.print(f"Abre: {browser_url}")
			ctx.print("(No uses http://0.0.0.0 en el navegador)")
		else:
			manager.set_enabled(False)
			ctx.error(message)
		return

	if action in {"off", "stop", "0", "false"}:
		ok, message = _stop_web_process()
		manager.set_enabled(False)
		if ok:
			ctx.success(message)
		else:
			ctx.error(message)
		return

	ctx.error(f"Subcomando desconocido: 'web {action}'")
	ctx.print("Usa 'web help' para ver comandos disponibles")


WEB_COMMANDS = {
	"web": cmd_web,
	"on": cmd_web,
	"off": cmd_web,
	"status": cmd_web,
	"help": cmd_web,
}

