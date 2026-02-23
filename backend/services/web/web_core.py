from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import uvicorn
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.services.web.livefeed import (
	is_livefeed_authorized,
	is_livefeed_path,
	register_pending_request,
	waiting_authorization_response,
)
from backend.services.web.economy.top_packager import get_top10_payload

app = FastAPI(title="PowerBot Web", version="1.0.0")
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _resolve_index_path() -> Path | None:
	"""Resuelve el index principal a servir en /."""
	candidates = [
		os.getenv("WEB_INDEX_FILE", "").strip(),
		"fronted/index.html",
		"frontend/index.html",
	]

	for candidate in candidates:
		if not candidate:
			continue
		path = Path(candidate)
		if not path.is_absolute():
			path = PROJECT_ROOT / candidate
		if path.exists() and path.is_file():
			return path
	return None


def _resolve_pages_dir() -> Path | None:
	"""Resuelve carpeta de páginas estáticas (fronted/pages o frontend/pages)."""
	candidates = [
		PROJECT_ROOT / "fronted" / "pages",
		PROJECT_ROOT / "frontend" / "pages",
	]

	for path in candidates:
		if path.exists() and path.is_dir():
			return path
	return None


def _resolve_livefeed_dir() -> Path | None:
	"""Resuelve carpeta del livefeed estático."""
	candidates = [
		PROJECT_ROOT / "fronted" / "livefeed",
		PROJECT_ROOT / "frontend" / "livefeed",
	]

	for path in candidates:
		if path.exists() and path.is_dir():
			return path
	return None


def _default_mounts() -> Iterable[tuple[str, Path]]:
	"""Montajes base útiles del proyecto."""
	return (
		("/fronted", PROJECT_ROOT / "fronted"),
		("/frontend", PROJECT_ROOT / "frontend"),
		("/media", PROJECT_ROOT / "media"),
	)


def _parse_custom_mounts() -> Iterable[tuple[str, Path]]:
	"""
	Parsea WEB_STATIC_MOUNTS con formato:
		"/ui=fronted;/assets=media;/docs=C:/ruta/absoluta"
	"""
	raw = os.getenv("WEB_STATIC_MOUNTS", "").strip()
	if not raw:
		return ()

	parsed: list[tuple[str, Path]] = []
	for chunk in raw.split(";"):
		chunk = chunk.strip()
		if not chunk or "=" not in chunk:
			continue
		url_prefix, path_value = chunk.split("=", 1)
		url_prefix = url_prefix.strip()
		path_value = path_value.strip()
		if not url_prefix.startswith("/"):
			url_prefix = f"/{url_prefix}"
		path = Path(path_value)
		if not path.is_absolute():
			path = PROJECT_ROOT / path_value
		parsed.append((url_prefix, path))

	return parsed


def _mount_static_dirs() -> None:
	mounted_prefixes: set[str] = set()

	for url_prefix, directory in [*_default_mounts(), *_parse_custom_mounts()]:
		if url_prefix in mounted_prefixes:
			continue
		if directory.exists() and directory.is_dir():
			app.mount(url_prefix, StaticFiles(directory=str(directory)), name=url_prefix.strip("/"))
			mounted_prefixes.add(url_prefix)


_mount_static_dirs()


@app.middleware("http")
async def livefeed_whitelist_middleware(request, call_next):
	path = str(request.url.path or "")
	if not is_livefeed_path(path):
		return await call_next(request)

	authorized, client_ip = is_livefeed_authorized(request)
	if authorized:
		return await call_next(request)

	register_pending_request(client_ip, path)
	print(
		f"[LIVEFEED_PENDING] Esperando autorización IP={client_ip} path={path}. "
		f"Usa: livefeed allow | livefeed deny"
	)
	return waiting_authorization_response()


@app.get("/", response_model=None)
async def root() -> Response:
	index_file = _resolve_index_path()
	if index_file:
		return FileResponse(index_file)
	return JSONResponse(
		{
			"service": "PowerBot Web",
			"status": "ok",
			"message": "No se encontró index.html. Define WEB_INDEX_FILE o usa /health.",
		}
	)


@app.get("/pages/{page_name}", response_model=None)
async def page_file(page_name: str) -> Response:
	if "/" in page_name or "\\" in page_name or ".." in page_name:
		return JSONResponse({"ok": False, "error": "page_name invalido"}, status_code=400)

	pages_dir = _resolve_pages_dir()
	if not pages_dir:
		return JSONResponse({"ok": False, "error": "Carpeta de paginas no encontrada"}, status_code=404)

	page_path = pages_dir / page_name
	if not page_path.exists() or not page_path.is_file():
		return JSONResponse({"ok": False, "error": "Pagina no encontrada"}, status_code=404)

	return FileResponse(page_path)


@app.get("/pages.top.html", response_model=None)
async def top_page_compat() -> Response:
	return await page_file("top.html")


@app.get("/livefeed", response_model=None)
@app.get("/livefeed/", response_model=None)
async def livefeed_root() -> Response:
	return await livefeed_file("main.html")


@app.get("/livefeed/{file_path:path}", response_model=None)
async def livefeed_file(file_path: str) -> Response:
	if ".." in file_path or file_path.startswith("/") or "\\" in file_path:
		return JSONResponse({"ok": False, "error": "file_path invalido"}, status_code=400)

	livefeed_dir = _resolve_livefeed_dir()
	if not livefeed_dir:
		return JSONResponse({"ok": False, "error": "Carpeta livefeed no encontrada"}, status_code=404)

	target = livefeed_dir / file_path
	if not target.exists() or not target.is_file():
		return JSONResponse({"ok": False, "error": "Archivo livefeed no encontrado"}, status_code=404)

	return FileResponse(target)


@app.get("/api/economy/top10")
async def economy_top10() -> dict:
	return get_top10_payload(limit=10)


@app.get("/health")
async def health() -> dict:
	return {"ok": True}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
	await ws.accept()
	try:
		while True:
			message = await ws.receive_text()
			await ws.send_text(f"echo: {message}")
	except WebSocketDisconnect:
		return


def run() -> None:
	host = os.getenv("WEB_HOST", "0.0.0.0")
	port = int(os.getenv("WEB_PORT", "19131"))
	uvicorn.run("backend.services.web.web_core:app", host=host, port=port, reload=False)


if __name__ == "__main__":
	run()
