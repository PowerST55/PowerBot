"""
Comandos de consola para controlar el servidor WebSocket local.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from backend.services.events_websocket.config.autorun import create_websocket_autorun_manager
from backend.services.events_websocket.config.toggle_on_off import create_websocket_toggle_manager


_ws_process: Optional[subprocess.Popen] = None
_ws_toggle_manager = None
_ws_autorun_manager = None


def _can_run_ws_module(python_executable: str) -> bool:
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


def _pick_python_for_ws(project_root: Path) -> str:
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
		if _can_run_ws_module(candidate):
			return candidate

	return sys.executable


def _get_toggle_manager():
	global _ws_toggle_manager
	if _ws_toggle_manager is None:
		_ws_toggle_manager = create_websocket_toggle_manager()
	return _ws_toggle_manager


def _get_autorun_manager():
	global _ws_autorun_manager
	if _ws_autorun_manager is None:
		_ws_autorun_manager = create_websocket_autorun_manager()
	return _ws_autorun_manager


def _get_access_urls() -> tuple[str, int, str]:
	host = os.getenv("WSOCKET_HOST", "127.0.0.1")
	port = int(os.getenv("WSOCKET_PORT", "8765"))
	browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
	ws_url = f"ws://{browser_host}:{port}/ws"
	return host, port, ws_url


def is_websocket_running() -> bool:
	global _ws_process
	return _ws_process is not None and _ws_process.poll() is None


async def start_websocket_server() -> tuple[bool, str]:
	global _ws_process

	if is_websocket_running():
		return True, "El servidor websocket ya está encendido"

	project_root = Path(__file__).resolve().parents[4]
	env = os.environ.copy()
	env.setdefault("PYTHONUTF8", "1")
	env.setdefault("PYTHONIOENCODING", "utf-8")
	env.setdefault("WSOCKET_HOST", "127.0.0.1")
	env.setdefault("WSOCKET_PORT", "8765")

	pythonpath = env.get("PYTHONPATH", "")
	root_str = str(project_root)
	if root_str not in pythonpath:
		env["PYTHONPATH"] = f"{root_str}{os.pathsep}{pythonpath}" if pythonpath else root_str

	python_executable = _pick_python_for_ws(project_root)

	try:
		_ws_process = subprocess.Popen(
			[python_executable, "-m", "backend.services.events_websocket.websocket_core"],
			cwd=str(project_root),
			env=env,
			stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE,
			text=True,
		)
		await asyncio.sleep(0.8)
		if _ws_process.poll() is not None:
			code = _ws_process.returncode
			error_output = ""
			if _ws_process.stderr is not None:
				try:
					error_output = (_ws_process.stderr.read() or "").strip()
				except Exception:
					error_output = ""
			_ws_process = None
			if error_output:
				return False, f"No se pudo iniciar websocket (exit code: {code}): {error_output.splitlines()[-1]}"
			return False, f"No se pudo iniciar websocket (exit code: {code})"

		return True, "Servidor websocket encendido"
	except Exception as exc:
		_ws_process = None
		return False, f"Error iniciando websocket: {exc}"


def stop_websocket_server() -> tuple[bool, str]:
	global _ws_process

	if not is_websocket_running():
		_ws_process = None
		return True, "El servidor websocket ya está apagado"

	try:
		_ws_process.terminate()
		_ws_process.wait(timeout=5)
	except Exception:
		try:
			_ws_process.kill()
		except Exception:
			pass
	finally:
		_ws_process = None

	return True, "Servidor websocket apagado"


async def start_if_autorun(ctx: Any | None = None) -> tuple[bool, str]:
	autorun_manager = _get_autorun_manager()
	if not autorun_manager.is_enabled():
		return False, "Autorun websocket desactivado"

	ok, message = await start_websocket_server()
	if ok:
		_get_toggle_manager().set_enabled(True)
		if ctx is not None:
			_, _, ws_url = _get_access_urls()
			ctx.success("WebSocket autorun activado - servidor iniciado")
			ctx.print(f"Endpoint local: {ws_url}")
		return True, message

	if ctx is not None:
		ctx.warning(f"Autorun websocket activo, pero falló el arranque: {message}")
	return False, message


async def cmd_wsocket(ctx: Any) -> None:
	"""
	Comando principal de websocket.

	Uso:
	  wsocket           -> alterna ON/OFF
	  wsocket autorun   -> alterna autorun
	  wsocket status    -> muestra estado
	  wsocket on/off    -> fuerza estado
	"""
	toggle_manager = _get_toggle_manager()
	autorun_manager = _get_autorun_manager()
	action = ctx.args[0].lower() if ctx.args else "toggle"

	if action in {"help", "-h", "--help"}:
		ctx.print("Comandos websocket disponibles:")
		ctx.print("  wsocket           - Alterna ON/OFF del servidor websocket")
		ctx.print("  wsocket on        - Enciende el servidor websocket")
		ctx.print("  wsocket off       - Apaga el servidor websocket")
		ctx.print("  wsocket status    - Muestra estado")
		ctx.print("  wsocket autorun   - Alterna arranque automático")
		return

	if action == "autorun":
		config = autorun_manager.toggle()
		state = "activado" if config.get("autorun") else "desactivado"
		ctx.success(f"WebSocket autorun {state}")
		ctx.print("Se aplicará en el próximo arranque del programa")
		return

	if action == "status":
		status = toggle_manager.get_status()
		process_state = "ON" if is_websocket_running() else "OFF"
		persisted_state = "ON" if status.get("enabled") else "OFF"
		autorun_state = "ON" if autorun_manager.is_enabled() else "OFF"
		host, port, ws_url = _get_access_urls()
		ctx.print("Estado WebSocket:")
		ctx.print(f"  • Proceso: {process_state}")
		ctx.print(f"  • Persistido: {persisted_state}")
		ctx.print(f"  • Autorun: {autorun_state}")
		ctx.print(f"  • Bind: {host}:{port}")
		ctx.print(f"  • Endpoint: {ws_url}")
		ctx.print(f"  • Config: {status.get('config_file')}")
		return

	if action in {"toggle", "switch"}:
		action = "off" if (is_websocket_running() or toggle_manager.is_enabled()) else "on"

	if action in {"on", "start", "1", "true"}:
		ok, message = await start_websocket_server()
		if ok:
			toggle_manager.set_enabled(True)
			ctx.success(message)
			_, _, ws_url = _get_access_urls()
			ctx.print(f"Endpoint local: {ws_url}")
		else:
			toggle_manager.set_enabled(False)
			ctx.error(message)
		return

	if action in {"off", "stop", "0", "false"}:
		ok, message = stop_websocket_server()
		toggle_manager.set_enabled(False)
		if ok:
			ctx.success(message)
		else:
			ctx.error(message)
		return

	ctx.error(f"Subcomando desconocido: 'wsocket {action}'")
	ctx.print("Usa 'wsocket help' para ver comandos disponibles")


WEBSOCKET_COMMANDS = {
	"wsocket": cmd_wsocket,
	"status": cmd_wsocket,
	"autorun": cmd_wsocket,
	"on": cmd_wsocket,
	"off": cmd_wsocket,
}

