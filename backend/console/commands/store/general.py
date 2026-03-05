"""
Comandos de consola para controlar el servicio store.
"""

from __future__ import annotations

from typing import Any

from backend.services.store.config.autorun import create_store_autorun_manager
from backend.services.store.store_core import (
	create_store_toggle_manager,
	get_store_service,
	start_store_service,
	stop_store_service,
)


_store_toggle_manager = None
_store_autorun_manager = None


def _get_toggle_manager():
	"""Obtiene el manager de configuración del store toggle."""
	global _store_toggle_manager
	if _store_toggle_manager is None:
		_store_toggle_manager = create_store_toggle_manager()
	return _store_toggle_manager


def _get_autorun_manager():
	"""Obtiene el manager de autorun del servicio store."""
	global _store_autorun_manager
	if _store_autorun_manager is None:
		_store_autorun_manager = create_store_autorun_manager()
	return _store_autorun_manager


def _is_store_running() -> bool:
	"""Estado operativo del store."""
	return bool(get_store_service().is_running())


async def start_if_autorun() -> tuple[bool, str]:
	"""Activa store al iniciar si autorun está habilitado."""
	autorun_manager = _get_autorun_manager()
	toggle_manager = _get_toggle_manager()

	if not autorun_manager.is_enabled():
		toggle_manager.set_enabled(False)
		stop_store_service()
		return False, "Autorun store desactivado"

	ok, message = start_store_service()
	if ok:
		toggle_manager.set_enabled(True)
		return True, message

	toggle_manager.set_enabled(False)
	return False, message


async def cmd_store(ctx: Any) -> None:
	"""
	Comando principal para encender/apagar el servicio store.

	Uso:
	  store          -> alterna on/off
	  store on       -> enciende
	  store off      -> apaga
	  store status   -> muestra estado
	  store autorun  -> alterna arranque automático
	"""
	toggle_manager = _get_toggle_manager()
	action = ctx.args[0].lower() if ctx.args else "toggle"

	if action in {"help", "-h", "--help"}:
		ctx.print("Comandos store disponibles:")
		ctx.print("  store          - Alterna ON/OFF")
		ctx.print("  store on       - Enciende el servicio store")
		ctx.print("  store off      - Apaga el servicio store")
		ctx.print("  store status   - Estado actual del servicio store")
		ctx.print("  store autorun  - Alterna arranque automático")
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
				ctx.error("Uso: store autorun [true|false]")
				return
		else:
			new_state = autorun_manager.toggle()

		status = "activado" if new_state else "desactivado"
		ctx.success(f"Store autorun {status}")
		ctx.print("Se aplicará al abrir el programa")
		return

	if action == "status":
		cfg = toggle_manager.get_status()
		autorun_cfg = _get_autorun_manager().get_status()
		service_status = get_store_service().get_status()
		last_sync_result = service_status.get("last_sync_result", {}) or {}

		ctx.print("Estado del servicio store:")
		ctx.print(f"  • Servicio: {'ON' if _is_store_running() else 'OFF'}")
		ctx.print(f"  • Config persistida: {'ON' if cfg.get('store_enabled') else 'OFF'}")
		ctx.print(f"  • Autorun: {'ON' if autorun_cfg.get('autorun') else 'OFF'}")
		ctx.print(f"  • Última sync: {service_status.get('last_sync_at')}")
		ctx.print(
			f"  • Catálogo: {last_sync_result.get('loaded', 0)}/{last_sync_result.get('total', 0)} cargados"
		)
		ctx.print(f"  • Assets inválidos: {last_sync_result.get('invalid', 0)}")
		ctx.print(f"  • Archivo config: {cfg.get('config_file')}")
		ctx.print(f"  • Archivo autorun: {autorun_cfg.get('config_file')}")
		return

	if action in {"toggle", "switch"}:
		action = "off" if _is_store_running() else "on"

	if action in {"on", "start", "1", "true"}:
		ok, message = start_store_service()
		if ok:
			toggle_manager.set_enabled(True)
			ctx.success(message)
		else:
			toggle_manager.set_enabled(False)
			ctx.error(message)
		return

	if action in {"off", "stop", "0", "false"}:
		stop_store_service()
		toggle_manager.set_enabled(False)
		ctx.success("Servicio store apagado")
		return

	ctx.error(f"Subcomando desconocido: 'store {action}'")
	ctx.print("Usa 'store help' para ver comandos disponibles")


STORE_COMMANDS = {
	"store": cmd_store,
	"on": cmd_store,
	"off": cmd_store,
	"status": cmd_store,
	"autorun": cmd_store,
	"help": cmd_store,
}

