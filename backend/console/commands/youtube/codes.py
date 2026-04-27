"""Comandos de consola para sistema de códigos de YouTube."""

from __future__ import annotations

from backend.services.activities.codes_master import spawn_random_code_now
from .general import _get_chat_id_manager, _get_console, _get_listener


async def cmd_youtube_random_code(ctx) -> None:
	"""Fuerza publicación manual de un código aleatorio en notifications.

	Uso:
	  yt random_code
	"""
	console = _get_console()
	listener = _get_listener()
	chat_manager = _get_chat_id_manager()

	live_chat_id = None
	if listener and getattr(listener, "is_running", False):
		live_chat_id = getattr(listener, "live_chat_id", None)

	if not live_chat_id and chat_manager:
		status = chat_manager.get_status()
		live_chat_id = status.get("current_chat_id")

	if not live_chat_id:
		ctx.error("No hay live_chat_id activo. Inicia YAPI/listener primero.")
		ctx.print("Sugerencia: ejecuta 'yapi' y vuelve a probar 'yt random_code'.")
		return

	result = await spawn_random_code_now(str(live_chat_id))
	status = str(result.get("status") or "unknown")

	if status == "spawned":
		code = result.get("code")
		points = result.get("points")
		expires_at = result.get("expires_at")
		ctx.success("Código aleatorio invocado")
		ctx.print(f"Código: {code}")
		ctx.print(f"Puntos: {points}")
		ctx.print(f"Expira: {expires_at}")
		console.print("[success]🎁 Código enviado a notifications.html[/success]")
		return

	if status == "skipped":
		reason = str(result.get("reason") or "unknown")
		if reason == "pending_exists":
			pending_code = result.get("pending_code")
			ctx.warning("Ya existe un código pendiente activo")
			if pending_code:
				ctx.print(f"Pendiente actual: {pending_code}")
		elif reason == "common_fund_empty":
			ctx.warning("No se generó código: fondo común vacío")
			ctx.print("Recarga fondo_comun para reactivar la generación de códigos")
		elif reason == "empty_catalog":
			ctx.error("El catálogo de códigos está vacío")
			ctx.print("Revisa backend/data/activities/codes_catalog.json")
		else:
			ctx.warning(f"No se publicó código: {reason}")
		return

	ctx.error("No se pudo invocar un código aleatorio")


YOUTUBE_CODES_COMMANDS = {
	"random_code": cmd_youtube_random_code,
}

