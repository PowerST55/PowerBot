from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
from typing import Any


logger = logging.getLogger(__name__)


def _ws_url() -> str:
	host = os.getenv("WSOCKET_HOST", "127.0.0.1")
	port = int(os.getenv("WSOCKET_PORT", "8765"))
	return f"ws://{host}:{port}/ws"


async def send_update(content: dict[str, Any], timeout: float = 3) -> bool:
	"""Envía un mensaje JSON al WebSocket local para su broadcast."""
	url = _ws_url()
	try:
		websockets = importlib.import_module("websockets")

		payload = json.dumps(content, ensure_ascii=False)
		async with asyncio.timeout(timeout):
			async with websockets.connect(url) as ws:
				await ws.send(payload)
		return True
	except ModuleNotFoundError:
		logger.warning("No se pudo enviar por websocket: falta dependencia 'websockets'")
	except TimeoutError:
		logger.warning("Timeout enviando actualización websocket: %s", content)
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

