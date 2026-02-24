"""
Comandos de consola para controlar el servicio backup.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from backend.services.backup.config.autorun import create_backup_autorun_manager
from backend.services.backup.config.toggle_on_off import create_backup_toggle_manager


_backup_process: Optional[subprocess.Popen] = None
_backup_toggle_manager = None
_backup_autorun_manager = None
_backup_log_threads: list[threading.Thread] = []


def _can_run_backup_module(python_executable: str) -> bool:
	"""Valida si el intérprete puede arrancar el módulo backup."""
	try:
		result = subprocess.run(
			[python_executable, "-c", "import dotenv"],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
			check=False,
			timeout=6,
		)
		return result.returncode == 0
	except Exception:
		return False


def _pick_python_for_backup(project_root: Path) -> str:
	"""Selecciona intérprete funcional para arrancar backup."""
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
		if _can_run_backup_module(candidate):
			return candidate

	return sys.executable


def _get_toggle_manager():
	global _backup_toggle_manager
	if _backup_toggle_manager is None:
		_backup_toggle_manager = create_backup_toggle_manager()
	return _backup_toggle_manager


def _get_autorun_manager():
	global _backup_autorun_manager
	if _backup_autorun_manager is None:
		_backup_autorun_manager = create_backup_autorun_manager()
	return _backup_autorun_manager


def _is_backup_running() -> bool:
	global _backup_process
	return _backup_process is not None and _backup_process.poll() is None


def _stream_backup_logs(pipe, stream_name: str) -> None:
	"""Consume logs del proceso backup para evitar bloqueo por buffers."""
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
			clean_text = text
			for prefix in ("💾 BACKUP:", "✅ BACKUP:", "⚠ BACKUP:", "🛑 BACKUP:"):
				if clean_text.startswith(prefix):
					clean_text = clean_text[len(prefix):].strip()
					break

			lower_text = clean_text.lower()
			if stream_name == "stderr":
				if "traceback" in lower_text or "error" in lower_text or "exception" in lower_text:
					console.print(f"[error]✗ BACKUP STDERR: {clean_text}[/error]")
				else:
					console.print(f"[warning]⚠ BACKUP STDERR: {clean_text}[/warning]")
			else:
				if "error" in lower_text or "exception" in lower_text:
					console.print(f"[warning]⚠ BACKUP: {clean_text}[/warning]")
				else:
					console.print(f"[muted]💾 BACKUP: {clean_text}[/muted]")
	except Exception:
		return


async def _start_backup_process() -> tuple[bool, str]:
	"""Inicia el servicio backup en un subproceso."""
	global _backup_process

	if _is_backup_running():
		return True, "El servicio backup ya está encendido"

	project_root = Path(__file__).resolve().parents[4]
	env = os.environ.copy()
	env.setdefault("PYTHONUTF8", "1")
	env.setdefault("PYTHONIOENCODING", "utf-8")
	env.setdefault("PYTHONUNBUFFERED", "1")
	pythonpath = env.get("PYTHONPATH", "")
	root_str = str(project_root)
	if root_str not in pythonpath:
		env["PYTHONPATH"] = f"{root_str}{os.pathsep}{pythonpath}" if pythonpath else root_str

	python_executable = _pick_python_for_backup(project_root)

	try:
		_backup_process = subprocess.Popen(
			[python_executable, "-u", "-m", "backend.services.backup.backup_core"],
			cwd=str(project_root),
			env=env,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			encoding="utf-8",
			errors="replace",
		)
		await asyncio.sleep(1.0)
		if _backup_process.poll() is not None:
			code = _backup_process.returncode
			error_output = ""
			if _backup_process.stderr is not None:
				try:
					error_output = (_backup_process.stderr.read() or "").strip()
				except Exception:
					error_output = ""
			_backup_process = None
			if error_output:
				error_line = error_output.splitlines()[-1]
				return False, f"No se pudo iniciar backup (exit code: {code}): {error_line}"
			return False, f"No se pudo iniciar backup (exit code: {code})"

		_backup_log_threads.clear()
		stdout_thread = threading.Thread(
			target=_stream_backup_logs,
			args=(_backup_process.stdout, "stdout"),
			daemon=True,
		)
		stderr_thread = threading.Thread(
			target=_stream_backup_logs,
			args=(_backup_process.stderr, "stderr"),
			daemon=True,
		)
		stdout_thread.start()
		stderr_thread.start()
		_backup_log_threads.extend([stdout_thread, stderr_thread])

		return True, "Servicio backup encendido"
	except Exception as exc:
		_backup_process = None
		return False, f"Error iniciando backup: {exc}"


def _stop_backup_process() -> tuple[bool, str]:
	"""Detiene el servicio backup si está activo."""
	global _backup_process

	if not _is_backup_running():
		_backup_process = None
		return True, "El servicio backup ya está apagado"

	try:
		_backup_process.terminate()
		_backup_process.wait(timeout=8)
	except Exception:
		try:
			_backup_process.kill()
		except Exception:
			pass
	finally:
		try:
			if _backup_process and _backup_process.stdout:
				_backup_process.stdout.close()
		except Exception:
			pass
		try:
			if _backup_process and _backup_process.stderr:
				_backup_process.stderr.close()
		except Exception:
			pass
		_backup_process = None

	return True, "Servicio backup apagado"


async def start_if_autorun() -> tuple[bool, str]:
	"""Inicia backup automáticamente si autorun está activo."""
	autorun_manager = _get_autorun_manager()
	toggle_manager = _get_toggle_manager()

	if not autorun_manager.is_enabled():
		toggle_manager.set_enabled(False)
		return False, "Autorun backup desactivado"

	ok, message = await _start_backup_process()
	if ok:
		toggle_manager.set_enabled(True)
		return True, message

	toggle_manager.set_enabled(False)
	return False, message


async def cmd_backup(ctx: Any) -> None:
	"""
	Comando principal para encender/apagar el servicio backup.

	Uso:
	  backup          -> alterna on/off
	  backup on       -> enciende
	  backup off      -> apaga
	  backup status   -> muestra estado
	  backup autorun  -> alterna arranque automático
	"""
	toggle_manager = _get_toggle_manager()
	action = ctx.args[0].lower() if ctx.args else "toggle"

	if action in {"help", "-h", "--help"}:
		ctx.print("Comandos backup disponibles:")
		ctx.print("  backup          - Alterna ON/OFF")
		ctx.print("  backup on       - Enciende el servicio backup")
		ctx.print("  backup off      - Apaga el servicio backup")
		ctx.print("  backup status   - Estado actual del servicio backup")
		ctx.print("  backup autorun  - Alterna arranque automático")
		ctx.print("  backup autosave - Gestión de autosave")
		return

	if action == "autosave":
		from .autosave import cmd_backup_autosave
		from types import SimpleNamespace

		autosave_ctx = SimpleNamespace(
			args=ctx.args[1:],
			print=ctx.print,
			error=ctx.error,
			warning=ctx.warning,
			success=ctx.success,
		)
		await cmd_backup_autosave(autosave_ctx)
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
				ctx.error("Uso: backup autorun [true|false]")
				return
		else:
			new_state = autorun_manager.toggle()

		status = "activado" if new_state else "desactivado"
		ctx.success(f"Backup autorun {status}")
		ctx.print("Se aplicará al abrir el programa")
		return

	if action == "status":
		is_running = _is_backup_running()
		cfg = toggle_manager.get_status()
		autorun_cfg = _get_autorun_manager().get_status()
		pid = _backup_process.pid if is_running and _backup_process else None

		ctx.print("Estado del servicio backup:")
		ctx.print(f"  • Proceso: {'ON' if is_running else 'OFF'}")
		if pid is not None:
			ctx.print(f"  • PID: {pid}")
		ctx.print(f"  • Config persistida: {'ON' if cfg.get('backup_enabled') else 'OFF'}")
		ctx.print(f"  • Autorun: {'ON' if autorun_cfg.get('autorun') else 'OFF'}")
		ctx.print(f"  • Archivo config: {cfg.get('config_file')}")
		ctx.print(f"  • Archivo autorun: {autorun_cfg.get('config_file')}")
		return

	if action in {"toggle", "switch"}:
		if _is_backup_running() or toggle_manager.is_enabled():
			action = "off"
		else:
			action = "on"

	if action in {"on", "start", "1", "true"}:
		ok, message = await _start_backup_process()
		if ok:
			toggle_manager.set_enabled(True)
			ctx.success(message)
			ctx.print("Usa 'backup status' para verificar el estado")
		else:
			toggle_manager.set_enabled(False)
			ctx.error(message)
		return

	if action in {"off", "stop", "0", "false"}:
		ok, message = _stop_backup_process()
		toggle_manager.set_enabled(False)
		if ok:
			ctx.success(message)
		else:
			ctx.error(message)
		return

	ctx.error(f"Subcomando desconocido: 'backup {action}'")
	ctx.print("Usa 'backup help' para ver comandos disponibles")


BACKUP_COMMANDS = {
	"backup": cmd_backup,
	"on": cmd_backup,
	"off": cmd_backup,
	"status": cmd_backup,
	"autorun": cmd_backup,
	"help": cmd_backup,
}

