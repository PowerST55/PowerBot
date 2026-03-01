from __future__ import annotations

import os
from typing import Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


app = FastAPI(title="PowerBot Events WebSocket", version="1.0.0")


class ConnectionHub:
	"""Hub simple para conexiones WebSocket locales."""

	def __init__(self) -> None:
		self._connections: Set[WebSocket] = set()

	async def connect(self, ws: WebSocket) -> None:
		await ws.accept()
		self._connections.add(ws)

	def disconnect(self, ws: WebSocket) -> None:
		self._connections.discard(ws)

	async def send_to(self, ws: WebSocket, payload: str) -> None:
		await ws.send_text(payload)

	async def broadcast(self, payload: str) -> None:
		dead: list[WebSocket] = []
		for ws in self._connections:
			try:
				await ws.send_text(payload)
			except Exception:
				dead.append(ws)

		for ws in dead:
			self.disconnect(ws)

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
	await hub.send_to(ws, '{"type":"connected","ok":true}')

	try:
		while True:
			message = await ws.receive_text()
			if message.strip().lower() == "ping":
				await hub.send_to(ws, '{"type":"pong"}')
				continue
			await hub.broadcast(message)
	except WebSocketDisconnect:
		hub.disconnect(ws)
		return
	except Exception:
		hub.disconnect(ws)
		return


@app.websocket("/ws")
async def ws_events(ws: WebSocket) -> None:
	await _ws_handler(ws)


@app.websocket("/")
async def ws_events_root(ws: WebSocket) -> None:
	await _ws_handler(ws)


def run() -> None:
	"""Arranca el servidor WebSocket local para la VM actual."""
	host = os.getenv("WSOCKET_HOST", "127.0.0.1")
	port = int(os.getenv("WSOCKET_PORT", "8765"))
	uvicorn.run("backend.services.events_websocket.websocket_core:app", host=host, port=port, reload=False)


if __name__ == "__main__":
	run()

