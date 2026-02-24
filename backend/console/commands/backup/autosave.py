"""
Comandos de autosave para el servicio backup.
"""

from __future__ import annotations

from typing import Any

from backend.services.backup.autosave_packager import (
	cleanup_mysql_residual_tables,
	create_autosave,
	delete_backup_by_index,
	list_backups,
	recover_backup_by_index,
	sync_mysql_to_sqlite,
	sync_sqlite_to_mysql,
)
from backend.services.backup.config.autosave import create_backup_autosave_manager


async def cmd_backup_autosave(ctx: Any) -> None:
	"""
	Subcomandos:
	  backup autosave interval <segundos>
	  backup autosave list
	  backup autosave recovery <index>
	  backup autosave run
	  backup autosave delete <index>
	  backup autosave clean_mysql
	  backup autosave mysql_to_local
	  backup autosave local_to_mysql
	"""
	manager = create_backup_autosave_manager()
	action = str(ctx.args[0]).strip().lower() if ctx.args else "help"

	if action in {"help", "-h", "--help"}:
		ctx.print("Comandos backup autosave:")
		ctx.print("  backup autosave interval <segundos>")
		ctx.print("  backup autosave list")
		ctx.print("  backup autosave recovery <index>")
		ctx.print("  backup autosave run")
		ctx.print("  backup autosave delete <index>")
		ctx.print("  backup autosave clean_mysql")
		ctx.print("  backup autosave mysql_to_local")
		ctx.print("  backup autosave local_to_mysql")
		return

	if action == "interval":
		if len(ctx.args) < 2:
			ctx.error("Uso: backup autosave interval <segundos>")
			return
		try:
			interval = int(str(ctx.args[1]).strip())
		except Exception:
			ctx.error("El intervalo debe ser numérico")
			return

		if interval < 30:
			ctx.error("Intervalo mínimo: 30 segundos")
			return

		cfg = manager.set_interval(interval)
		ctx.success(f"Autosave interval configurado en {cfg.get('interval_seconds')}s")
		ctx.print("Se guardó en data/backup/autosave.json")
		return

	if action == "list":
		cfg = manager.get_status()
		ctx.print("Estado autosave:")
		ctx.print(f"  • Enabled: {'ON' if cfg.get('enabled') else 'OFF'}")
		ctx.print(f"  • Intervalo: {cfg.get('interval_seconds')}s")
		ctx.print(f"  • Última ejecución: {cfg.get('last_run_at') or 'N/A'}")
		ctx.print(f"  • Archivo config: {cfg.get('config_file')}")

		items = list_backups()
		if not items:
			ctx.print("No hay backups registrados")
			return

		ctx.print("Backups disponibles:")
		for idx, item in enumerate(items, start=1):
			ts = item.get("created_at")
			ok = "OK" if item.get("mysql_sync_ok") else "PARCIAL"
			reason = item.get("reason") or "manual"
			ctx.print(f"  {idx}. [{ok}] {ts} | reason={reason}")
		return

	if action == "run":
		ok, msg, item = create_autosave(reason="manual")
		if ok:
			ctx.success(msg)
			if item:
				ctx.print(f"Backup generado: {item.get('file_path')}")
		else:
			ctx.error(msg)
		return

	if action == "recovery":
		if len(ctx.args) < 2:
			ctx.error("Uso: backup autosave recovery <index>")
			return
		try:
			index = int(str(ctx.args[1]).strip())
		except Exception:
			ctx.error("Índice inválido")
			return

		ok, msg = recover_backup_by_index(index)
		if ok:
			ctx.success(msg)
		else:
			ctx.error(msg)
		return

	if action == "delete":
		if len(ctx.args) < 2:
			ctx.error("Uso: backup autosave delete <index>")
			return
		try:
			index = int(str(ctx.args[1]).strip())
		except Exception:
			ctx.error("Índice inválido")
			return

		ok, msg = delete_backup_by_index(index)
		if ok:
			ctx.success(msg)
		else:
			ctx.error(msg)
		return

	if action == "clean_mysql":
		ok, msg = cleanup_mysql_residual_tables()
		if ok:
			manager.set_last_cleanup_now()
			ctx.success(msg)
		else:
			ctx.error(msg)
		return

	if action == "mysql_to_local":
		ok, msg, stats = sync_mysql_to_sqlite()
		if ok:
			ctx.success(msg)
			ctx.print(f"Tablas sincronizadas: {len(stats)}")
		else:
			ctx.error(msg)
		return

	if action == "local_to_mysql":
		ok, msg, stats = sync_sqlite_to_mysql(tag="manual_local_to_mysql")
		if ok:
			ctx.success(msg)
			ctx.print(f"Tablas sincronizadas: {len(stats)}")
		else:
			ctx.error(msg)
		return

	ctx.error(f"Subcomando desconocido: backup autosave {action}")
	ctx.print("Usa: backup autosave help")

