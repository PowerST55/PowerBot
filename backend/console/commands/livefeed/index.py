"""Comando de consola para volver al index (main.html) del livefeed."""

from __future__ import annotations

from typing import Any

from backend.services.events_websocket import general as ws_general


async def cmd_index(ctx: Any) -> None:
	"""Redirige el livefeed a main.html."""
	ok = await ws_general.change_page("main.html")
	if ok:
		ctx.success("Redirección enviada: main.html")
	else:
		ctx.warning("No se pudo enviar la redirección por websocket")
