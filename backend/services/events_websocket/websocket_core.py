from __future__ import annotations

import asyncio
import logging
import os
from typing import Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


app = FastAPI(title="PowerBot Events WebSocket", version="1.0.0")
logger = logging.getLogger(__name__)


def _client_label(ws: WebSocket) -> str:
	client = ws.client
	if client is None:
		return "unknown"
	return f"{client.host}:{client.port}"


class ConnectionHub:
	"""Hub simple para conexiones WebSocket locales."""

	def __init__(self) -> None:
		self._connections: Set[WebSocket] = set()
		self._pending_broadcasts: Set[asyncio.Task] = set()

	async def connect(self, ws: WebSocket) -> None:
		await ws.accept()
		self._connections.add(ws)

	def disconnect(self, ws: WebSocket) -> None:
		self._connections.discard(ws)

	async def send_to(self, ws: WebSocket, payload: str) -> None:
		await ws.send_text(payload)

	async def _safe_send(self, ws: WebSocket, payload: str, timeout: float = 1.6) -> bool:
		"""Envía con timeout para evitar que un cliente zombie bloquee el broadcast."""
		try:
			await asyncio.wait_for(ws.send_text(payload), timeout=timeout)
			return True
		except Exception as exc:
			logger.debug("[WS] Fallo enviando a %s (%s)", _client_label(ws), type(exc).__name__)
			return False

	async def broadcast(self, payload: str, exclude: WebSocket | None = None) -> None:
		if not self._connections:
			return

		connections = [ws for ws in self._connections if ws is not exclude]
		if not connections:
			return
		results = await asyncio.gather(
			*(self._safe_send(ws, payload) for ws in connections),
			return_exceptions=False,
		)

		for ws, ok in zip(connections, results):
			if not ok:
				self.disconnect(ws)

	def broadcast_nowait(self, payload: str, exclude: WebSocket | None = None) -> None:
		"""Programa broadcast sin bloquear el handler del cliente emisor."""
		task = asyncio.create_task(self.broadcast(payload, exclude=exclude))
		self._pending_broadcasts.add(task)

		def _cleanup(done: asyncio.Task) -> None:
			self._pending_broadcasts.discard(done)
			try:
				done.result()
			except Exception:
				pass

		task.add_done_callback(_cleanup)

	@property
	def size(self) -> int:
		return len(self._connections)


hub = ConnectionHub()


@app.get("/health")
async def health() -> dict:
	return {
		"ok": True,
		"service": "events_websocket",
		"connections": hub.size,
	}


async def _ws_handler(ws: WebSocket) -> None:
	await hub.connect(ws)
	print(f"[WS] Cliente conectado: {_client_label(ws)} (total={hub.size})")
	try:
		await asyncio.wait_for(hub.send_to(ws, '{"type":"connected","ok":true}'), timeout=1.0)
	except Exception:
		# El mensaje de bienvenida es opcional; no debe romper la sesión.
		pass

	try:
		while True:
			message = await ws.receive_text()
			if message.strip().lower() == "ping":
				await hub.send_to(ws, '{"type":"pong"}')
				continue
			hub.broadcast_nowait(message, exclude=ws)
	except WebSocketDisconnect:
		hub.disconnect(ws)
		print(f"[WS] Cliente desconectado: {_client_label(ws)} (total={hub.size})")
		return
	except Exception as exc:
		logger.warning("[WS] Error en cliente %s: %s", _client_label(ws), type(exc).__name__)
		hub.disconnect(ws)
		print(f"[WS] Cliente desconectado por error: {_client_label(ws)} (total={hub.size})")
		return


@app.websocket("/ws")
async def ws_events(ws: WebSocket) -> None:
	await _ws_handler(ws)


@app.websocket("/")
async def ws_events_root(ws: WebSocket) -> None:
	await _ws_handler(ws)


def run() -> None:
	"""Arranca el servidor WebSocket local para la VM actual."""
	host = os.getenv("WSOCKET_HOST", "0.0.0.0")
	port = int(os.getenv("WSOCKET_PORT", "8765"))
	uvicorn.run(
		"backend.services.events_websocket.websocket_core:app",
		host=host,
		port=port,
		reload=False,
		access_log=False,
		log_level="warning",
	)


if __name__ == "__main__":
	run()

