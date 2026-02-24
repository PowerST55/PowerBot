"""
Comandos de consola para controlar el bot de Discord.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from backend.services.discord_bot.config.autorun import create_discord_autorun_manager
from backend.services.discord_bot.config.toggle_on_off import create_discord_toggle_manager


_discord_process: Optional[subprocess.Popen] = None
_discord_toggle_manager = None
_discord_autorun_manager = None
_discord_log_threads: list[threading.Thread] = []


def _can_run_discord_module(python_executable: str) -> bool:
	"""Valida si el intérprete tiene dependencias mínimas para Discord."""
	try:
		result = subprocess.run(
			[python_executable, "-c", "import discord, dotenv"],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
			check=False,
			timeout=6,
		)
		return result.returncode == 0
	except Exception:
		return False


def _pick_python_for_discord(project_root: Path) -> str:
	"""Selecciona un intérprete funcional para arrancar el bot de Discord."""
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
		if _can_run_discord_module(candidate):
			return candidate

	return sys.executable


def _get_toggle_manager():
	"""Obtiene el manager de configuración del toggle Discord."""
	global _discord_toggle_manager
	if _discord_toggle_manager is None:
		_discord_toggle_manager = create_discord_toggle_manager()
	return _discord_toggle_manager


def _get_autorun_manager():
	"""Obtiene el manager de configuración de autorun Discord."""
	global _discord_autorun_manager
	if _discord_autorun_manager is None:
		_discord_autorun_manager = create_discord_autorun_manager()
	return _discord_autorun_manager


def _is_discord_running() -> bool:
	"""Verifica si el proceso de Discord lanzado por consola sigue activo."""
	global _discord_process
	return _discord_process is not None and _discord_process.poll() is None


def _stream_discord_logs(pipe, stream_name: str) -> None:
	"""Consume logs del proceso Discord para evitar bloqueo por buffers."""
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
			if "RuntimeWarning" in text and "backend.services.discord_bot.bot_core" in text:
				continue

			lower_text = text.lower()
			if stream_name == "stderr":
				if "traceback" in lower_text or "error" in lower_text or "exception" in lower_text:
					console.print(f"[error]✗ DISCORD STDERR: {text}[/error]")
				else:
					console.print(f"[warning]⚠ DISCORD STDERR: {text}[/warning]")
			else:
				if "error" in lower_text or "exception" in lower_text:
					console.print(f"[warning]⚠ DISCORD: {text}[/warning]")
				else:
					console.print(f"[muted]🤖 DISCORD: {text}[/muted]")
	except Exception:
		return


async def _start_discord_process() -> tuple[bool, str]:
	"""Inicia el bot de Discord en un subproceso."""
	global _discord_process

	if _is_discord_running():
		return True, "El bot de Discord ya está encendido"

	project_root = Path(__file__).resolve().parents[4]
	env = os.environ.copy()
	env.setdefault("PYTHONUTF8", "1")
	env.setdefault("PYTHONIOENCODING", "utf-8")
	env.setdefault("PYTHONUNBUFFERED", "1")
	pythonpath = env.get("PYTHONPATH", "")
	root_str = str(project_root)
	if root_str not in pythonpath:
		env["PYTHONPATH"] = f"{root_str}{os.pathsep}{pythonpath}" if pythonpath else root_str
	python_executable = _pick_python_for_discord(project_root)

	try:
		_discord_process = subprocess.Popen(
			[python_executable, "-u", "-m", "backend.services.discord_bot.bot_core"],
			cwd=str(project_root),
			env=env,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			encoding="utf-8",
			errors="replace",
		)
		await asyncio.sleep(1.2)
		if _discord_process.poll() is not None:
			code = _discord_process.returncode
			error_output = ""
			if _discord_process.stderr is not None:
				try:
					error_output = (_discord_process.stderr.read() or "").strip()
				except Exception:
					error_output = ""
			_discord_process = None
			if error_output:
				error_line = error_output.splitlines()[-1]
				return False, f"No se pudo iniciar Discord (exit code: {code}): {error_line}"
			return False, f"No se pudo iniciar Discord (exit code: {code})"

		_discord_log_threads.clear()
		stdout_thread = threading.Thread(
			target=_stream_discord_logs,
			args=(_discord_process.stdout, "stdout"),
			daemon=True,
		)
		stderr_thread = threading.Thread(
			target=_stream_discord_logs,
			args=(_discord_process.stderr, "stderr"),
			daemon=True,
		)
		stdout_thread.start()
		stderr_thread.start()
		_discord_log_threads.extend([stdout_thread, stderr_thread])

		return True, "Bot de Discord encendido"
	except Exception as exc:
		_discord_process = None
		return False, f"Error iniciando Discord: {exc}"


def _stop_discord_process() -> tuple[bool, str]:
	"""Detiene el bot de Discord si está activo."""
	global _discord_process

	if not _is_discord_running():
		_discord_process = None
		return True, "El bot de Discord ya está apagado"

	try:
		_discord_process.terminate()
		_discord_process.wait(timeout=8)
	except Exception:
		try:
			_discord_process.kill()
		except Exception:
			pass
	finally:
		try:
			if _discord_process and _discord_process.stdout:
				_discord_process.stdout.close()
		except Exception:
			pass
		try:
			if _discord_process and _discord_process.stderr:
				_discord_process.stderr.close()
		except Exception:
			pass
		_discord_process = None

	return True, "Bot de Discord apagado"


async def start_if_autorun() -> tuple[bool, str]:
	"""Inicia Discord automáticamente si autorun está activo."""
	autorun_manager = _get_autorun_manager()
	toggle_manager = _get_toggle_manager()

	if not autorun_manager.is_enabled():
		toggle_manager.set_enabled(False)
		return False, "Autorun discord desactivado"

	ok, message = await _start_discord_process()
	if ok:
		toggle_manager.set_enabled(True)
		return True, message

	toggle_manager.set_enabled(False)
	return False, message


async def cmd_discord(ctx: Any) -> None:
	"""
	Comando principal para encender/apagar el bot de Discord.

	Uso:
	  discord          -> alterna on/off
	  discord on       -> enciende
	  discord off      -> apaga
	  discord status   -> muestra estado
	  discord autorun  -> alterna arranque automático
	"""
	toggle_manager = _get_toggle_manager()
	action = ctx.args[0].lower() if ctx.args else "toggle"

	if action in {"help", "-h", "--help"}:
		ctx.print("Comandos discord disponibles:")
		ctx.print("  discord          - Alterna ON/OFF")
		ctx.print("  discord on       - Enciende el bot de Discord")
		ctx.print("  discord off      - Apaga el bot de Discord")
		ctx.print("  discord status   - Estado actual del bot de Discord")
		ctx.print("  discord autorun  - Alterna arranque automático")
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
				ctx.error("Uso: discord autorun [true|false]")
				return
		else:
			new_state = autorun_manager.toggle()

		status = "activado" if new_state else "desactivado"
		ctx.success(f"Discord autorun {status}")
		ctx.print("Se aplicará al abrir el programa")
		return

	if action == "status":
		is_running = _is_discord_running()
		cfg = toggle_manager.get_status()
		autorun_cfg = _get_autorun_manager().get_status()
		pid = _discord_process.pid if is_running and _discord_process else None

		ctx.print("Estado del bot de Discord:")
		ctx.print(f"  • Proceso: {'ON' if is_running else 'OFF'}")
		if pid is not None:
			ctx.print(f"  • PID: {pid}")
		ctx.print(f"  • Config persistida: {'ON' if cfg.get('discord_enabled') else 'OFF'}")
		ctx.print(f"  • Autorun: {'ON' if autorun_cfg.get('autorun') else 'OFF'}")
		ctx.print(f"  • Archivo config: {cfg.get('config_file')}")
		ctx.print(f"  • Archivo autorun: {autorun_cfg.get('config_file')}")
		return

	if action in {"toggle", "switch"}:
		if _is_discord_running() or toggle_manager.is_enabled():
			action = "off"
		else:
			action = "on"

	if action in {"on", "start", "1", "true"}:
		ok, message = await _start_discord_process()
		if ok:
			toggle_manager.set_enabled(True)
			ctx.success(message)
			ctx.print("Usa 'discord status' para verificar el estado")
		else:
			toggle_manager.set_enabled(False)
			ctx.error(message)
		return

	if action in {"off", "stop", "0", "false"}:
		ok, message = _stop_discord_process()
		toggle_manager.set_enabled(False)
		if ok:
			ctx.success(message)
		else:
			ctx.error(message)
		return

	ctx.error(f"Subcomando desconocido: 'discord {action}'")
	ctx.print("Usa 'discord help' para ver comandos disponibles")


DISCORD_COMMANDS = {
	"discord": cmd_discord,
	"on": cmd_discord,
	"off": cmd_discord,
	"status": cmd_discord,
	"autorun": cmd_discord,
	"help": cmd_discord,
}
