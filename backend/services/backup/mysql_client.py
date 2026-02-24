"""
Cliente compartido MySQL para servicio backup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


DEFAULT_MYSQL_HOST = "panther.teramont.net"
DEFAULT_MYSQL_PORT = 3306
DEFAULT_MYSQL_USER = "u4130_wkNOuSaty4"
DEFAULT_MYSQL_PASSWORD = "rGXKte2!GaZ!vNewtild+Pry"


@dataclass
class MySQLConfig:
	host: str
	port: int
	user: str
	password: str
	database: str | None = None
	connect_timeout: int = 8


def _load_env_file() -> None:
	backend_dir = Path(__file__).resolve().parents[2]
	env_path = backend_dir / "keys" / ".env"
	if env_path.exists():
		load_dotenv(env_path)


def _parse_host_and_port(host_value: str | None, port_value: str | None) -> tuple[str, int]:
	host_raw = str(host_value or "").strip()
	if host_raw and ":" in host_raw:
		host_part, port_part = host_raw.rsplit(":", 1)
		if host_part:
			host_raw = host_part
			if not port_value:
				port_value = port_part

	host = host_raw or DEFAULT_MYSQL_HOST
	try:
		port = int(str(port_value or DEFAULT_MYSQL_PORT).strip())
	except Exception:
		port = DEFAULT_MYSQL_PORT

	return host, port


def load_mysql_config() -> MySQLConfig:
	_load_env_file()

	host_env = (
		os.getenv("BACKUP_DB_HOST")
		or os.getenv("MYSQL_HOST")
		or os.getenv("DB_HOST")
	)
	port_env = (
		os.getenv("BACKUP_DB_PORT")
		or os.getenv("MYSQL_PORT")
		or os.getenv("DB_PORT")
	)
	host, port = _parse_host_and_port(host_env, port_env)

	user = (
		os.getenv("BACKUP_DB_USER")
		or os.getenv("MYSQL_USER")
		or os.getenv("DB_USER")
		or DEFAULT_MYSQL_USER
	)
	password = (
		os.getenv("BACKUP_DB_PASSWORD")
		or os.getenv("MYSQL_PASSWORD")
		or os.getenv("DB_PASSWORD")
		or DEFAULT_MYSQL_PASSWORD
	)
	database = (
		os.getenv("BACKUP_DB_NAME")
		or os.getenv("MYSQL_DATABASE")
		or os.getenv("DB_NAME")
	)
	timeout = int(os.getenv("BACKUP_DB_TIMEOUT", "8"))

	return MySQLConfig(
		host=host,
		port=port,
		user=user,
		password=password,
		database=database,
		connect_timeout=timeout,
	)


def _connect_with_mysql_connector(cfg: MySQLConfig):
	import mysql.connector  # type: ignore

	kwargs = {
		"host": cfg.host,
		"port": cfg.port,
		"user": cfg.user,
		"password": cfg.password,
		"connection_timeout": cfg.connect_timeout,
	}
	if cfg.database:
		kwargs["database"] = cfg.database
	return mysql.connector.connect(**kwargs)


def _connect_with_pymysql(cfg: MySQLConfig):
	import pymysql  # type: ignore

	kwargs = {
		"host": cfg.host,
		"port": cfg.port,
		"user": cfg.user,
		"password": cfg.password,
		"connect_timeout": cfg.connect_timeout,
		"charset": "utf8mb4",
		"autocommit": True,
	}
	if cfg.database:
		kwargs["database"] = cfg.database
	return pymysql.connect(**kwargs)


def connect_mysql(cfg: MySQLConfig) -> tuple[Any, str]:
	errors: list[str] = []

	try:
		conn = _connect_with_mysql_connector(cfg)
		return conn, "mysql-connector"
	except Exception as exc:
		errors.append(f"mysql-connector: {exc}")

	try:
		conn = _connect_with_pymysql(cfg)
		return conn, "pymysql"
	except Exception as exc:
		errors.append(f"pymysql: {exc}")

	raise RuntimeError("No se pudo conectar a MySQL. " + " | ".join(errors))
