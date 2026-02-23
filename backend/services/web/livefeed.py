"""
Lógica de protección de livefeed por IP whitelist.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from .config.ip_livefeed import create_livefeed_ip_manager


def _extract_client_ip(request: Request) -> str:
	forwarded_for = request.headers.get("x-forwarded-for", "").strip()
	if forwarded_for:
		first = forwarded_for.split(",")[0].strip()
		if first:
			return first

	if request.client and request.client.host:
		return str(request.client.host)

	return "unknown"


def is_livefeed_path(path: str) -> bool:
	normalized = str(path or "").lower()
	return (
		normalized.startswith("/livefeed")
		or normalized.startswith("/fronted/livefeed")
		or normalized.startswith("/frontend/livefeed")
	)


def is_livefeed_authorized(request: Request) -> tuple[bool, str]:
	manager = create_livefeed_ip_manager()
	client_ip = _extract_client_ip(request)
	return manager.is_allowed(client_ip), client_ip


def register_pending_request(ip: str, path: str) -> None:
	manager = create_livefeed_ip_manager()
	manager.register_pending(ip=ip, path=path)


def waiting_authorization_response() -> HTMLResponse:
	html = """
	<!doctype html>
	<html lang="es">
	<head>
	  <meta charset="utf-8" />
	  <meta name="viewport" content="width=device-width,initial-scale=1" />
	  <title>Livefeed protegido</title>
	  <style>
		body{margin:0;display:grid;place-items:center;height:100vh;background:#0f1115;color:#e8eaed;font-family:Arial,sans-serif}
		.box{padding:24px 28px;border:1px solid #2c313a;border-radius:12px;background:#151922;max-width:560px;text-align:center}
		h1{margin:0 0 10px;font-size:24px}
		p{margin:0;color:#aeb6c2}
	  </style>
	</head>
	<body>
	  <div class="box">
		<h1>Esperando autorización...</h1>
		<p>Tu IP aún no está permitida para acceder a livefeed.</p>
		<p>El administrador debe responder la solicitud desde consola.</p>
	  </div>
	</body>
	</html>
	"""
	return HTMLResponse(content=html, status_code=403)

