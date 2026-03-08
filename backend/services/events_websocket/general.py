from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import socket
from typing import Any


logger = logging.getLogger(__name__)


def _ws_url() -> str:
	host = os.getenv("WSOCKET_HOST", "127.0.0.1")
	# 0.0.0.0 es valido para bind del servidor, pero no para conectar como cliente.
	if host in {"0.0.0.0", "::", "*"}:
		host = "127.0.0.1"
	port = int(os.getenv("WSOCKET_PORT", "8765"))
	return f"ws://{host}:{port}/ws"


def is_ws_endpoint_available(timeout: float = 0.6) -> bool:
	"""Retorna True si el endpoint websocket local está escuchando."""
	host = os.getenv("WSOCKET_HOST", "127.0.0.1")
	if host in {"0.0.0.0", "::", "*"}:
		host = "127.0.0.1"
	port = int(os.getenv("WSOCKET_PORT", "8765"))
	try:
		with socket.create_connection((host, port), timeout=max(0.2, float(timeout))):
			return True
	except OSError:
		return False


async def send_update(content: dict[str, Any], timeout: float = 3) -> bool:
	"""Envía un mensaje JSON al WebSocket local para su broadcast."""
	url = _ws_url()
	try:
		if not is_ws_endpoint_available(timeout=0.45):
			return False

		websockets = importlib.import_module("websockets")

		payload = json.dumps(content, ensure_ascii=False)
		connect_timeout = max(1.0, min(float(timeout) + 0.6, 4.2))
		send_timeout = max(1.0, min(float(timeout), 3.2))

		async def _send_once() -> bool:
			ws = None
			try:
				ws = await asyncio.wait_for(
					websockets.connect(
						url,
						open_timeout=connect_timeout,
						close_timeout=1,
						ping_interval=None,
					),
					timeout=connect_timeout + 0.8,
				)
				await asyncio.wait_for(ws.send(payload), timeout=send_timeout)
				return True
			finally:
				if ws is not None:
					try:
						await asyncio.wait_for(ws.close(), timeout=0.8)
					except Exception:
						pass

		for attempt, pause in ((1, 0.12), (2, 0.35), (3, 0.75), (4, 0.0)):
			try:
				return await _send_once()
			except Exception as exc:
				if attempt >= 4:
					logger.warning(
						"No se pudo enviar actualización websocket tras %s intentos (%s): %s",
						attempt,
						type(exc).__name__,
						content,
					)
					return False
				if pause > 0:
					await asyncio.sleep(pause)
	except ModuleNotFoundError:
		logger.warning("No se pudo enviar por websocket: falta dependencia 'websockets'")
	except Exception as exc:
		logger.debug("No se pudo enviar actualización websocket a %s: %s", url, exc)
	return False


async def change_page(url: str, timeout: float = 3) -> bool:
	"""Envía un mensaje para que los clientes cambien de página."""
	data = {"type": "redirect", "url": url}
	return await send_update(data, timeout=timeout)


async def ruleta_call(timeout: float = 3) -> bool:
	"""Redirige a la página de la ruleta."""
	return await change_page("ruleta.html", timeout=timeout)


async def addtexthub(text: str, timeout: float = 3) -> bool:
	"""Agrega texto al texthub."""
	data = {"type": "texthubadd", "text": text}
	return await send_update(data, timeout=timeout)

