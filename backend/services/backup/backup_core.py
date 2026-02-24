"""
Servicio backup - núcleo de conexión MySQL.

Responsabilidades:
- Cargar credenciales desde backend/keys/.env
- Probar conexión MySQL
- Mantener un loop de servicio con healthcheck periódico
"""

from __future__ import annotations

import os
import time
from typing import Tuple

from backend.services.backup.autosave_packager import run_due_autosave_if_needed
from backend.services.backup.mysql_client import connect_mysql, load_mysql_config


def test_mysql_connection() -> Tuple[bool, str]:
	"""Prueba la conexión y ejecuta SELECT 1."""
	cfg = load_mysql_config()
	conn = None
	try:
		conn, driver = connect_mysql(cfg)
		cursor = conn.cursor()
		cursor.execute("SELECT 1")
		row = cursor.fetchone()
		try:
			cursor.close()
		except Exception:
			pass
		return True, f"Conectado a MySQL ({driver}) en {cfg.host}:{cfg.port} | ping={row}"
	except Exception as exc:
		return False, f"Error conectando MySQL {cfg.host}:{cfg.port}: {exc}"
	finally:
		if conn is not None:
			try:
				conn.close()
			except Exception:
				pass


def run_backup_service(poll_seconds: int = 60) -> None:
	"""Ejecuta el servicio backup con healthcheck periódico de MySQL."""
	print("💾 BACKUP: Servicio iniciado")
	print(f"💾 BACKUP: Healthcheck MySQL cada {poll_seconds}s")

	while True:
		ok, message = test_mysql_connection()
		if ok:
			print(f"✅ BACKUP: {message}")
		else:
			print(f"⚠ BACKUP: {message}")

		autosave_ok, autosave_message = run_due_autosave_if_needed()
		if autosave_ok:
			print(f"✅ BACKUP: Autosave ejecutado: {autosave_message}")
		else:
			if "desactivado" not in autosave_message.lower() and "aún no vence" not in autosave_message.lower():
				print(f"⚠ BACKUP: Autosave: {autosave_message}")
		time.sleep(poll_seconds)


if __name__ == "__main__":
	try:
		poll = int(os.getenv("BACKUP_POLL_SECONDS", "60"))
	except Exception:
		poll = 60

	try:
		run_backup_service(poll_seconds=max(10, poll))
	except KeyboardInterrupt:
		print("🛑 BACKUP: Servicio detenido por usuario")

