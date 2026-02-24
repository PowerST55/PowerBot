"""
Autosave packager para backup SQLite <-> MySQL.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.database.connection import DB_PATH
from backend.services.backup.config.autosave import create_backup_autosave_manager
from backend.services.backup.mysql_client import connect_mysql, load_mysql_config


BACKUP_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "backup"
SNAPSHOT_DIR = BACKUP_DATA_DIR / "snapshots"
MANIFEST_FILE = BACKUP_DATA_DIR / "autosave_manifest.json"
MYSQL_META_TABLE = "powerbot_backup_metadata"


def _utcnow() -> datetime:
	return datetime.now(timezone.utc)


def _to_utc_datetime(value: str | datetime | None) -> datetime:
	"""Normaliza cualquier datetime/string a aware UTC."""
	if isinstance(value, datetime):
		dt = value
	elif value is None:
		dt = _utcnow()
	else:
		try:
			dt = datetime.fromisoformat(str(value))
		except Exception:
			return datetime.min.replace(tzinfo=timezone.utc)

	if dt.tzinfo is None:
		return dt.replace(tzinfo=timezone.utc)
	return dt.astimezone(timezone.utc)


def _ts_for_file(now: datetime | None = None) -> str:
	now = now or _utcnow()
	return now.strftime("%Y%m%d_%H%M%S")


def _ensure_dirs() -> None:
	BACKUP_DATA_DIR.mkdir(parents=True, exist_ok=True)
	SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _load_manifest() -> dict:
	_ensure_dirs()
	if MANIFEST_FILE.exists():
		try:
			with open(MANIFEST_FILE, "r", encoding="utf-8") as file:
				data = json.load(file)
				if isinstance(data, dict):
					data.setdefault("backups", [])
					return data
		except Exception:
			pass
	return {"backups": []}


def _save_manifest(manifest: dict) -> None:
	_ensure_dirs()
	with open(MANIFEST_FILE, "w", encoding="utf-8") as file:
		json.dump(manifest, file, indent=2, ensure_ascii=False)


def _list_sqlite_tables(conn: sqlite3.Connection) -> list[str]:
	rows = conn.execute(
		"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
	).fetchall()
	return [str(row[0]) for row in rows if row and row[0]]


def _normalize_sqlite_type_to_mysql(sqlite_type: str) -> str:
	t = str(sqlite_type or "").upper()
	if "INT" in t:
		return "BIGINT"
	if any(token in t for token in ["REAL", "FLOA", "DOUB", "NUMERIC", "DECIMAL"]):
		return "DOUBLE"
	if any(token in t for token in ["DATE", "TIME"]):
		return "DATETIME"
	if "BLOB" in t:
		return "LONGBLOB"
	return "LONGTEXT"


def _get_sqlite_table_columns(conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
	rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
	columns: list[dict[str, Any]] = []
	for row in rows:
		columns.append(
			{
				"cid": row[0],
				"name": row[1],
				"type": row[2],
				"notnull": row[3],
				"default": row[4],
				"pk": row[5],
			}
		)
	return columns


def _table_has_autoincrement_pk(columns: list[dict[str, Any]]) -> bool:
	pk_columns = [c for c in columns if int(c.get("pk", 0)) > 0]
	if len(pk_columns) != 1:
		return False
	type_name = str(pk_columns[0].get("type") or "").upper()
	return "INT" in type_name


def _create_mysql_table_from_sqlite(mysql_cursor, table_name: str, columns: list[dict[str, Any]]) -> None:
	column_sql: list[str] = []
	pk_columns: list[str] = []
	auto_inc_pk = _table_has_autoincrement_pk(columns)

	for col in columns:
		name = str(col["name"])
		mysql_type = _normalize_sqlite_type_to_mysql(str(col.get("type") or ""))
		not_null = bool(col.get("notnull"))
		is_pk = int(col.get("pk", 0)) > 0

		parts = [f"`{name}`", mysql_type]
		if is_pk and auto_inc_pk:
			parts.append("AUTO_INCREMENT")
		if not_null or is_pk:
			parts.append("NOT NULL")
		column_sql.append(" ".join(parts))

		if is_pk:
			pk_columns.append(f"`{name}`")

	constraints = []
	if pk_columns:
		constraints.append(f"PRIMARY KEY ({', '.join(pk_columns)})")

	create_sql = (
		f"CREATE TABLE IF NOT EXISTS `{table_name}` ("
		+ ", ".join(column_sql + constraints)
		+ ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
	)
	mysql_cursor.execute(create_sql)


def _ensure_mysql_meta_table(mysql_cursor) -> None:
	mysql_cursor.execute(
		f"""
		CREATE TABLE IF NOT EXISTS `{MYSQL_META_TABLE}` (
			id BIGINT NOT NULL AUTO_INCREMENT,
			backup_tag VARCHAR(64) NOT NULL,
			created_at DATETIME NOT NULL,
			source VARCHAR(32) NOT NULL,
			note TEXT NULL,
			PRIMARY KEY (id)
		) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
		"""
	)


def cleanup_mysql_residual_tables() -> tuple[bool, str]:
	"""Elimina tablas residuales en MySQL que no existen en SQLite ni son metadata."""
	cfg = load_mysql_config()
	if not cfg.database:
		return False, "No se puede limpiar MySQL: falta nombre de base de datos (BACKUP_DB_NAME/MYSQL_DATABASE)."

	sqlite_conn = sqlite3.connect(str(DB_PATH))
	try:
		sqlite_tables = set(_list_sqlite_tables(sqlite_conn))
	finally:
		sqlite_conn.close()

	mysql_conn, _ = connect_mysql(cfg)
	try:
		cur = mysql_conn.cursor()
		cur.execute("SHOW TABLES")
		rows = cur.fetchall()
		mysql_tables = {str(row[0]) for row in rows}
		allowed = set(sqlite_tables)
		allowed.add(MYSQL_META_TABLE)
		to_drop = sorted(mysql_tables - allowed)

		for table in to_drop:
			cur.execute(f"DROP TABLE IF EXISTS `{table}`")

		mysql_conn.commit()
		return True, f"Tablas residuales eliminadas: {len(to_drop)}"
	finally:
		try:
			mysql_conn.close()
		except Exception:
			pass


def sync_sqlite_to_mysql(tag: str | None = None) -> tuple[bool, str, dict[str, int]]:
	"""Sincroniza toda la base SQLite actual hacia MySQL (replace total por tabla)."""
	cfg = load_mysql_config()
	if not cfg.database:
		return False, "Falta nombre de base de datos MySQL (BACKUP_DB_NAME/MYSQL_DATABASE).", {}

	sqlite_conn = sqlite3.connect(str(DB_PATH))
	sqlite_conn.row_factory = sqlite3.Row
	mysql_conn, driver = connect_mysql(cfg)
	stats: dict[str, int] = {}

	try:
		s_cur = sqlite_conn.cursor()
		m_cur = mysql_conn.cursor()
		_ensure_mysql_meta_table(m_cur)

		tables = _list_sqlite_tables(sqlite_conn)
		for table_name in tables:
			columns = _get_sqlite_table_columns(sqlite_conn, table_name)
			if not columns:
				continue

			_create_mysql_table_from_sqlite(m_cur, table_name, columns)

			m_cur.execute(f"DELETE FROM `{table_name}`")

			col_names = [str(col["name"]) for col in columns]
			s_cur.execute(f"SELECT * FROM `{table_name}`")
			rows = s_cur.fetchall()

			if rows:
				insert_sql = (
					f"INSERT INTO `{table_name}` ("
					+ ",".join([f"`{c}`" for c in col_names])
					+ ") VALUES ("
					+ ",".join(["%s"] * len(col_names))
					+ ")"
				)
				payload = [tuple(row[c] for c in col_names) for row in rows]
				m_cur.executemany(insert_sql, payload)

			stats[table_name] = len(rows)

		backup_tag = tag or _ts_for_file()
		m_cur.execute(
			f"INSERT INTO `{MYSQL_META_TABLE}` (backup_tag, created_at, source, note) VALUES (%s, %s, %s, %s)",
			(backup_tag, _utcnow().strftime("%Y-%m-%d %H:%M:%S"), "sqlite_to_mysql", f"driver={driver}"),
		)

		mysql_conn.commit()
		return True, f"Sincronización SQLite→MySQL completada con {driver}", stats
	except Exception as exc:
		try:
			mysql_conn.rollback()
		except Exception:
			pass
		return False, f"Error sincronizando SQLite→MySQL: {exc}", stats
	finally:
		try:
			sqlite_conn.close()
		except Exception:
			pass
		try:
			mysql_conn.close()
		except Exception:
			pass


def sync_mysql_to_sqlite() -> tuple[bool, str, dict[str, int]]:
	"""Sincroniza toda la base MySQL actual hacia SQLite (replace total por tabla)."""
	cfg = load_mysql_config()
	if not cfg.database:
		return False, "Falta nombre de base de datos MySQL (BACKUP_DB_NAME/MYSQL_DATABASE).", {}

	sqlite_conn = sqlite3.connect(str(DB_PATH))
	mysql_conn, _ = connect_mysql(cfg)
	stats: dict[str, int] = {}

	try:
		s_cur = sqlite_conn.cursor()
		m_cur = mysql_conn.cursor()

		m_cur.execute("SHOW TABLES")
		tables = [str(row[0]) for row in m_cur.fetchall()]

		for table_name in tables:
			if table_name == MYSQL_META_TABLE:
				continue

			m_cur.execute(f"SHOW COLUMNS FROM `{table_name}`")
			cols = [str(row[0]) for row in m_cur.fetchall()]
			if not cols:
				continue

			m_cur.execute(f"SELECT * FROM `{table_name}`")
			rows = m_cur.fetchall()

			s_cur.execute(f"DELETE FROM `{table_name}`")

			if rows:
				insert_sql = (
					f"INSERT INTO `{table_name}` ("
					+ ",".join(cols)
					+ ") VALUES ("
					+ ",".join(["?"] * len(cols))
					+ ")"
				)
				s_cur.executemany(insert_sql, rows)

			stats[table_name] = len(rows)

		sqlite_conn.commit()
		return True, "Sincronización MySQL→SQLite completada", stats
	except Exception as exc:
		try:
			sqlite_conn.rollback()
		except Exception:
			pass
		return False, f"Error sincronizando MySQL→SQLite: {exc}", stats
	finally:
		try:
			sqlite_conn.close()
		except Exception:
			pass
		try:
			mysql_conn.close()
		except Exception:
			pass


def _create_snapshot_file() -> Path:
	_ensure_dirs()
	ts = _ts_for_file()
	file_path = SNAPSHOT_DIR / f"autosave_{ts}.db"
	shutil.copy2(DB_PATH, file_path)
	return file_path


def _next_backup_id(backups: list[dict]) -> int:
	if not backups:
		return 1
	return max(int(item.get("id", 0)) for item in backups) + 1


def _apply_retention(backups: list[dict]) -> list[dict]:
	def to_dt(item: dict) -> datetime:
		value = item.get("created_at")
		return _to_utc_datetime(value)

	sorted_items = sorted(backups, key=to_dt, reverse=True)
	recent_keep = sorted_items[:5]
	remaining = sorted_items[5:]

	older_by_day: dict[str, dict] = {}
	for item in remaining:
		dt = to_dt(item)
		day_key = dt.date().isoformat()
		if day_key not in older_by_day:
			older_by_day[day_key] = item

	older_keep = sorted(older_by_day.values(), key=to_dt, reverse=True)[:10]
	keep_ids = {int(item.get("id", 0)) for item in (recent_keep + older_keep)}

	for item in sorted_items:
		item_id = int(item.get("id", 0))
		if item_id in keep_ids:
			continue
		file_path = Path(str(item.get("file_path") or ""))
		if file_path.exists():
			try:
				file_path.unlink()
			except Exception:
				pass

	kept = [item for item in sorted_items if int(item.get("id", 0)) in keep_ids]
	return sorted(kept, key=to_dt, reverse=True)


def create_autosave(reason: str = "manual") -> tuple[bool, str, dict | None]:
	"""Ejecuta autosave completo: snapshot local + sync SQLite→MySQL + retención."""
	_ensure_dirs()
	autosave_cfg = create_backup_autosave_manager()

	if not DB_PATH.exists():
		return False, f"No existe DB SQLite local: {DB_PATH}", None

	cleanup_ok, cleanup_msg = cleanup_mysql_residual_tables()
	if cleanup_ok:
		autosave_cfg.set_last_cleanup_now()

	snapshot_file = _create_snapshot_file()
	tag = snapshot_file.stem
	ok, msg, table_stats = sync_sqlite_to_mysql(tag=tag)

	manifest = _load_manifest()
	backups: list[dict] = list(manifest.get("backups", []))
	backup_item = {
		"id": _next_backup_id(backups),
		"created_at": _utcnow().isoformat(),
		"reason": reason,
		"file_path": str(snapshot_file),
		"mysql_sync_ok": bool(ok),
		"mysql_sync_message": msg,
		"mysql_cleanup_ok": bool(cleanup_ok),
		"mysql_cleanup_message": cleanup_msg,
		"tables": table_stats,
	}
	backups.append(backup_item)
	manifest["backups"] = _apply_retention(backups)
	_save_manifest(manifest)
	autosave_cfg.set_last_run_now()

	status = "OK" if ok else "PARCIAL"
	return True, f"Autosave {status}: {msg}", backup_item


def list_backups() -> list[dict]:
	manifest = _load_manifest()
	items = list(manifest.get("backups", []))

	def to_dt(item: dict) -> datetime:
		return _to_utc_datetime(item.get("created_at"))

	return sorted(items, key=to_dt, reverse=True)


def delete_backup_by_index(index_1_based: int) -> tuple[bool, str]:
	items = list_backups()
	if index_1_based <= 0 or index_1_based > len(items):
		return False, "Índice fuera de rango"

	target = items[index_1_based - 1]
	target_id = int(target.get("id", 0))
	file_path = Path(str(target.get("file_path") or ""))

	manifest = _load_manifest()
	manifest["backups"] = [
		item for item in manifest.get("backups", []) if int(item.get("id", 0)) != target_id
	]
	_save_manifest(manifest)

	if file_path.exists():
		try:
			file_path.unlink()
		except Exception:
			pass

	return True, f"Backup {index_1_based} eliminado"


def recover_backup_by_index(index_1_based: int) -> tuple[bool, str]:
	items = list_backups()
	if index_1_based <= 0 or index_1_based > len(items):
		return False, "Índice fuera de rango"

	target = items[index_1_based - 1]
	file_path = Path(str(target.get("file_path") or ""))
	if not file_path.exists():
		return False, f"Archivo de backup no existe: {file_path}"

	try:
		shutil.copy2(file_path, DB_PATH)
	except Exception as exc:
		return False, f"No se pudo restaurar SQLite desde backup: {exc}"

	ok, msg, _ = sync_sqlite_to_mysql(tag=f"recovery_{_ts_for_file()}")
	if ok:
		return True, f"Recovery completado y sincronizado a MySQL: {msg}"
	return False, f"SQLite restaurado, pero falló sync a MySQL: {msg}"


def run_due_autosave_if_needed() -> tuple[bool, str]:
	"""Ejecuta autosave si está habilitado y ya venció el intervalo."""
	cfg_manager = create_backup_autosave_manager()
	cfg = cfg_manager.load_config()
	if not bool(cfg.get("enabled", False)):
		return False, "Autosave desactivado"

	interval = int(cfg.get("interval_seconds", 3600))
	last_run_at = cfg.get("last_run_at")
	if not last_run_at:
		ok, msg, _ = create_autosave(reason="scheduler:first")
		return ok, msg

	try:
		last_dt = _to_utc_datetime(last_run_at)
	except Exception:
		ok, msg, _ = create_autosave(reason="scheduler:invalid_last_run")
		return ok, msg

	if _utcnow() - last_dt < timedelta(seconds=interval):
		return False, "Aún no vence el intervalo de autosave"

	ok, msg, _ = create_autosave(reason="scheduler")
	return ok, msg

