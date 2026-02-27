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
	if not cfg.database:
		return False, "Falta nombre de base de datos MySQL (BACKUP_DB_NAME/MYSQL_DATABASE/DB_NAME)."
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
		return True, f"Conectado a MySQL ({driver}) en {cfg.host}:{cfg.port}/{cfg.database} | ping={row}"
	except Exception as exc:
		return False, f"Error conectando MySQL {cfg.host}:{cfg.port}: {exc}"
	finally:
		if conn is not None:
			try:
				conn.close()
			except Exception:
				pass



def run_backup_service(poll_seconds: int = 60, healthcheck_seconds: int | None = None, verbose_ok: bool = False) -> None:
	"""Ejecuta el servicio backup.

	- Llama a ``run_due_autosave_if_needed`` en cada iteración (él decide si toca guardar).
	- Hace healthcheck MySQL solo cada ``healthcheck_seconds`` para no spamear.
	- Solo loguea OK continuos si ``verbose_ok`` es True o cambia el estado.
	"""
	if healthcheck_seconds is None:
		try:
			healthcheck_seconds = int(os.getenv("BACKUP_HEALTHCHECK_SECONDS", "300"))
		except Exception:
			healthcheck_seconds = 300

	healthcheck_seconds = max(30, healthcheck_seconds)

	print("💾 BACKUP: Servicio iniciado")
	print(f"💾 BACKUP: Loop cada {poll_seconds}s | Healthcheck MySQL cada {healthcheck_seconds}s")

	last_healthcheck_time: float = 0.0
	last_healthcheck_ok: bool | None = None

	while True:
		now = time.time()
		if now - last_healthcheck_time >= healthcheck_seconds:
			ok, message = test_mysql_connection()
			if ok:
				if verbose_ok or last_healthcheck_ok is not True:
					print(f"✅ BACKUP: {message}")
			else:
				print(f"⚠ BACKUP: {message}")
			last_healthcheck_ok = ok
			last_healthcheck_time = now

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

	verbose_ok = os.getenv("BACKUP_HEALTHCHECK_VERBOSE", "0").lower() in {"1", "true", "yes", "on"}
	try:
		run_backup_service(poll_seconds=max(10, poll), verbose_ok=verbose_ok)
	except KeyboardInterrupt:
		print("🛑 BACKUP: Servicio detenido por usuario")

