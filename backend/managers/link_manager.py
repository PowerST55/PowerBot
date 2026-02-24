"""
Manager de vinculación Discord <-> YouTube.

Flujo:
- Discord genera código temporal.
- YouTube consume código y vincula cuentas.
- Si ambas plataformas existen en users distintos, se fusiona en un user_id canónico.
"""

from __future__ import annotations

import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from backend.database import get_connection
from backend.managers.user_manager import (
	get_or_create_discord_user,
)


TOKEN_TTL_MINUTES = 10
TOKEN_LENGTH = 8
TOKEN_ALPHABET = string.ascii_uppercase + string.digits


@dataclass
class LinkCodeResult:
	success: bool
	message: str
	code: Optional[str] = None
	expires_at: Optional[str] = None
	user_id: Optional[int] = None


@dataclass
class LinkConsumeResult:
	success: bool
	message: str
	primary_user_id: Optional[int] = None
	discord_user_id: Optional[str] = None
	youtube_channel_id: Optional[str] = None


@dataclass
class UnlinkResult:
	success: bool
	message: str
	kept_user_id: Optional[int] = None
	new_user_id: Optional[int] = None


@dataclass
class ForceLinkResult:
	success: bool
	message: str
	target_user_id: Optional[int] = None
	previous_user_id: Optional[int] = None


def _utc_now() -> datetime:
	return datetime.utcnow()


def _to_iso(dt: datetime) -> str:
	return dt.isoformat()


def _ensure_link_tables(conn) -> None:
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS link_tokens (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			code TEXT NOT NULL UNIQUE,
			discord_user_id TEXT NOT NULL,
			discord_user_name TEXT,
			discord_owner_user_id INTEGER NOT NULL,
			status TEXT NOT NULL DEFAULT 'active',
			created_at TEXT NOT NULL,
			expires_at TEXT NOT NULL,
			consumed_at TEXT,
			consumed_by_youtube_channel_id TEXT,
			FOREIGN KEY (discord_owner_user_id) REFERENCES users(user_id) ON DELETE CASCADE
		)
		"""
	)

	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS user_id_links (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			primary_user_id INTEGER NOT NULL,
			inactive_user_id INTEGER NOT NULL UNIQUE,
			link_reason TEXT NOT NULL,
			created_at TEXT NOT NULL,
			is_active INTEGER NOT NULL DEFAULT 1,
			FOREIGN KEY (primary_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
			FOREIGN KEY (inactive_user_id) REFERENCES users(user_id) ON DELETE CASCADE
		)
		"""
	)

	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS linked_accounts (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER NOT NULL,
			provider TEXT NOT NULL,
			provider_user_id TEXT NOT NULL,
			provider_username_snapshot TEXT,
			is_active INTEGER NOT NULL DEFAULT 1,
			linked_at TEXT NOT NULL,
			unlinked_at TEXT,
			FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
			UNIQUE(provider, provider_user_id, is_active)
		)
		"""
	)

	conn.execute(
		"CREATE INDEX IF NOT EXISTS idx_link_tokens_discord_user_id ON link_tokens(discord_user_id)"
	)
	conn.execute(
		"CREATE INDEX IF NOT EXISTS idx_linked_accounts_user_id ON linked_accounts(user_id)"
	)


def _ensure_optional_tables_for_merge(conn) -> None:
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS user_inventory (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER NOT NULL,
			item_id INTEGER NOT NULL,
			quantity INTEGER NOT NULL DEFAULT 1,
			acquired_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			UNIQUE(user_id, item_id)
		)
		"""
	)


def _generate_code() -> str:
	return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))


def _invalidate_previous_codes(conn, discord_user_id: str) -> None:
	now_iso = _to_iso(_utc_now())
	conn.execute(
		"""
		UPDATE link_tokens
		SET status = 'replaced', consumed_at = ?
		WHERE discord_user_id = ? AND status = 'active'
		""",
		(now_iso, str(discord_user_id)),
	)


def create_discord_link_code(discord_user_id: str, discord_user_name: str) -> LinkCodeResult:
	"""Genera un código de vinculación para un usuario de Discord."""
	owner_user, _, _ = get_or_create_discord_user(
		discord_id=str(discord_user_id),
		discord_username=str(discord_user_name),
		avatar_url=None,
	)

	now = _utc_now()
	expires_at = now + timedelta(minutes=TOKEN_TTL_MINUTES)
	now_iso = _to_iso(now)
	expires_iso = _to_iso(expires_at)

	conn = get_connection()
	try:
		_ensure_link_tables(conn)
		conn.execute("BEGIN IMMEDIATE")
		_invalidate_previous_codes(conn, str(discord_user_id))

		code = _generate_code()
		for _ in range(5):
			existing = conn.execute("SELECT 1 FROM link_tokens WHERE code = ?", (code,)).fetchone()
			if not existing:
				break
			code = _generate_code()

		conn.execute(
			"""
			INSERT INTO link_tokens (
				code, discord_user_id, discord_user_name, discord_owner_user_id,
				status, created_at, expires_at
			)
			VALUES (?, ?, ?, ?, 'active', ?, ?)
			""",
			(
				code,
				str(discord_user_id),
				str(discord_user_name),
				owner_user.user_id,
				now_iso,
				expires_iso,
			),
		)

		conn.commit()
		return LinkCodeResult(
			success=True,
			message="Código generado correctamente",
			code=code,
			expires_at=expires_iso,
			user_id=owner_user.user_id,
		)
	except Exception as exc:
		conn.rollback()
		return LinkCodeResult(success=False, message=f"Error generando código: {exc}")
	finally:
		conn.close()


def _register_linked_account(
	conn,
	user_id: int,
	provider: str,
	provider_user_id: str,
	provider_username_snapshot: str | None,
) -> None:
	now_iso = _to_iso(_utc_now())
	conn.execute(
		"""
		DELETE FROM linked_accounts
		WHERE provider = ? AND provider_user_id = ? AND is_active = 0
		""",
		(provider, provider_user_id),
	)
	conn.execute(
		"""
		UPDATE linked_accounts
		SET is_active = 0, unlinked_at = ?
		WHERE provider = ? AND provider_user_id = ? AND is_active = 1
		""",
		(now_iso, provider, provider_user_id),
	)

	conn.execute(
		"""
		INSERT INTO linked_accounts (
			user_id, provider, provider_user_id, provider_username_snapshot,
			is_active, linked_at
		)
		VALUES (?, ?, ?, ?, 1, ?)
		""",
		(user_id, provider, provider_user_id, provider_username_snapshot, now_iso),
	)


def _sync_total_wallet(conn, user_id: int) -> None:
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS platform_wallets (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER NOT NULL,
			platform TEXT NOT NULL,
			balance REAL NOT NULL DEFAULT 0,
			created_at TEXT DEFAULT CURRENT_TIMESTAMP,
			updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
			UNIQUE(user_id, platform)
		)
		"""
	)

	now_iso = _to_iso(_utc_now())
	total_row = conn.execute(
		"SELECT COALESCE(SUM(balance), 0) AS total FROM platform_wallets WHERE user_id = ?",
		(user_id,),
	).fetchone()
	total = float(total_row["total"] if total_row else 0.0)

	conn.execute(
		"""
		INSERT INTO wallets (user_id, balance, created_at, updated_at)
		VALUES (?, ?, ?, ?)
		ON CONFLICT(user_id)
		DO UPDATE SET balance = excluded.balance, updated_at = excluded.updated_at
		""",
		(user_id, total, now_iso, now_iso),
	)


def _merge_inventory(conn, from_user_id: int, to_user_id: int) -> None:
	rows = conn.execute(
		"SELECT item_id, quantity FROM user_inventory WHERE user_id = ?",
		(from_user_id,),
	).fetchall()
	now_iso = _to_iso(_utc_now())
	for row in rows:
		conn.execute(
			"""
			INSERT INTO user_inventory (user_id, item_id, quantity, acquired_at, updated_at)
			VALUES (?, ?, ?, ?, ?)
			ON CONFLICT(user_id, item_id)
			DO UPDATE SET
				quantity = user_inventory.quantity + excluded.quantity,
				updated_at = excluded.updated_at
			""",
			(to_user_id, row["item_id"], row["quantity"], now_iso, now_iso),
		)

	conn.execute("DELETE FROM user_inventory WHERE user_id = ?", (from_user_id,))


def _merge_platform_wallets(conn, from_user_id: int, to_user_id: int) -> None:
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS platform_wallets (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER NOT NULL,
			platform TEXT NOT NULL,
			balance REAL NOT NULL DEFAULT 0,
			created_at TEXT DEFAULT CURRENT_TIMESTAMP,
			updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
			UNIQUE(user_id, platform)
		)
		"""
	)

	now_iso = _to_iso(_utc_now())
	rows = conn.execute(
		"SELECT platform, balance FROM platform_wallets WHERE user_id = ?",
		(from_user_id,),
	).fetchall()

	for row in rows:
		conn.execute(
			"""
			INSERT INTO platform_wallets (user_id, platform, balance, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?)
			ON CONFLICT(user_id, platform)
			DO UPDATE SET
				balance = platform_wallets.balance + excluded.balance,
				updated_at = excluded.updated_at
			""",
			(to_user_id, row["platform"], float(row["balance"]), now_iso, now_iso),
		)

	conn.execute("DELETE FROM platform_wallets WHERE user_id = ?", (from_user_id,))


def _merge_user_data(conn, from_user_id: int, to_user_id: int) -> None:
	if from_user_id == to_user_id:
		return

	_ensure_optional_tables_for_merge(conn)

	# Mover trazas de economía e inventario
	conn.execute("UPDATE wallet_ledger SET user_id = ? WHERE user_id = ?", (to_user_id, from_user_id))
	conn.execute("UPDATE earning_events SET user_id = ? WHERE user_id = ?", (to_user_id, from_user_id))

	# Cooldown: mover de forma segura por clave (user_id, guild_id)
	rows = conn.execute(
		"SELECT guild_id, last_earned_at FROM earning_cooldown WHERE user_id = ?",
		(from_user_id,),
	).fetchall()
	now_iso = _to_iso(_utc_now())
	for row in rows:
		conn.execute(
			"""
			INSERT INTO earning_cooldown (user_id, guild_id, last_earned_at, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?)
			ON CONFLICT(user_id, guild_id)
			DO UPDATE SET
				last_earned_at = CASE
					WHEN excluded.last_earned_at > earning_cooldown.last_earned_at
					THEN excluded.last_earned_at
					ELSE earning_cooldown.last_earned_at
				END,
				updated_at = excluded.updated_at
			""",
			(to_user_id, row["guild_id"], row["last_earned_at"], now_iso, now_iso),
		)
	conn.execute("DELETE FROM earning_cooldown WHERE user_id = ?", (from_user_id,))

	_merge_platform_wallets(conn, from_user_id, to_user_id)
	_merge_inventory(conn, from_user_id, to_user_id)

	# Mantener compatibilidad con wallets total
	_sync_total_wallet(conn, to_user_id)
	conn.execute("UPDATE wallets SET balance = 0, updated_at = ? WHERE user_id = ?", (now_iso, from_user_id))

	# Registrar id inactivo -> id principal
	conn.execute(
		"""
		INSERT INTO user_id_links (primary_user_id, inactive_user_id, link_reason, created_at, is_active)
		VALUES (?, ?, 'discord_youtube_link_merge', ?, 1)
		ON CONFLICT(inactive_user_id)
		DO UPDATE SET
			primary_user_id = excluded.primary_user_id,
			link_reason = excluded.link_reason,
			created_at = excluded.created_at,
			is_active = 1
		""",
		(to_user_id, from_user_id, now_iso),
	)


def resolve_active_user_id(user_id: int) -> int:
	"""Resuelve un ID inactivo a su ID principal activo."""
	conn = get_connection()
	try:
		_ensure_link_tables(conn)
		row = _resolve_active_user_id_in_conn(conn, user_id)
		if not row:
			return int(user_id)
		return int(row)
	finally:
		conn.close()


def _resolve_active_user_id_in_conn(conn, user_id: int) -> int | None:
	row = conn.execute(
		"""
		SELECT primary_user_id
		FROM user_id_links
		WHERE inactive_user_id = ? AND is_active = 1
		LIMIT 1
		""",
		(user_id,),
	).fetchone()
	if not row:
		return None
	return int(row["primary_user_id"])


def consume_youtube_link_code(
	code: str,
	youtube_channel_id: str,
	youtube_username: str,
	channel_avatar_url: str | None = None,
) -> LinkConsumeResult:
	"""Consume un código generado en Discord y vincula YouTube al mismo user_id."""
	now = _utc_now()
	now_iso = _to_iso(now)
	normalized_code = str(code).strip().upper()

	if not normalized_code:
		return LinkConsumeResult(success=False, message="Código vacío")

	conn = get_connection()
	try:
		_ensure_link_tables(conn)
		conn.execute("BEGIN IMMEDIATE")

		row = conn.execute(
			"""
			SELECT * FROM link_tokens
			WHERE code = ?
			LIMIT 1
			""",
			(normalized_code,),
		).fetchone()

		if not row:
			conn.rollback()
			return LinkConsumeResult(success=False, message="Código inválido")

		status = str(row["status"])
		expires_at = datetime.fromisoformat(str(row["expires_at"]))
		if status != "active":
			conn.rollback()
			return LinkConsumeResult(success=False, message="Código ya fue usado o invalidado")

		if now > expires_at:
			conn.execute(
				"UPDATE link_tokens SET status = 'expired' WHERE id = ?",
				(row["id"],),
			)
			conn.commit()
			return LinkConsumeResult(success=False, message="Código expirado")

		discord_owner_user_id = int(row["discord_owner_user_id"])
		discord_user_id = str(row["discord_user_id"])
		youtube_profile = conn.execute(
			"SELECT * FROM youtube_profile WHERE youtube_channel_id = ? LIMIT 1",
			(str(youtube_channel_id),),
		).fetchone()

		if youtube_profile is None:
			conn.execute(
				"""
				INSERT INTO users (username, created_at, updated_at)
				VALUES (?, ?, ?)
				""",
				(str(youtube_username or youtube_channel_id), now_iso, now_iso),
			)
			youtube_user_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])

			conn.execute(
				"""
				INSERT INTO youtube_profile (
					user_id, youtube_channel_id, youtube_username,
					channel_avatar_url, user_type, subscribers,
					created_at, updated_at
				)
				VALUES (?, ?, ?, ?, 'regular', 0, ?, ?)
				""",
				(
					youtube_user_id,
					str(youtube_channel_id),
					str(youtube_username or "unknown"),
					channel_avatar_url,
					now_iso,
					now_iso,
				),
			)
		else:
			youtube_user_id = int(youtube_profile["user_id"])
			conn.execute(
				"""
				UPDATE youtube_profile
				SET youtube_username = ?,
					channel_avatar_url = ?,
					updated_at = ?
				WHERE youtube_channel_id = ?
				""",
				(
					str(youtube_username or youtube_profile["youtube_username"] or "unknown"),
					channel_avatar_url or youtube_profile["channel_avatar_url"],
					now_iso,
					str(youtube_channel_id),
				),
			)

		primary_user_id = discord_owner_user_id
		secondary_user_id = youtube_user_id

		if secondary_user_id != primary_user_id:
			_merge_user_data(conn, from_user_id=secondary_user_id, to_user_id=primary_user_id)

		conn.execute(
			"UPDATE youtube_profile SET user_id = ?, updated_at = ? WHERE youtube_channel_id = ?",
			(primary_user_id, now_iso, str(youtube_channel_id)),
		)

		_register_linked_account(
			conn,
			user_id=primary_user_id,
			provider="discord",
			provider_user_id=discord_user_id,
			provider_username_snapshot=row["discord_user_name"],
		)
		_register_linked_account(
			conn,
			user_id=primary_user_id,
			provider="youtube",
			provider_user_id=str(youtube_channel_id),
			provider_username_snapshot=str(youtube_username or ""),
		)

		conn.execute(
			"""
			UPDATE link_tokens
			SET status = 'consumed', consumed_at = ?, consumed_by_youtube_channel_id = ?
			WHERE id = ?
			""",
			(now_iso, str(youtube_channel_id), row["id"]),
		)

		conn.commit()
		return LinkConsumeResult(
			success=True,
			message="Cuentas vinculadas correctamente",
			primary_user_id=primary_user_id,
			discord_user_id=discord_user_id,
			youtube_channel_id=str(youtube_channel_id),
		)
	except Exception as exc:
		conn.rollback()
		return LinkConsumeResult(success=False, message=f"Error en vinculación: {exc}")
	finally:
		conn.close()


def _ensure_platform_wallet_row(conn, user_id: int, platform: str, now_iso: str) -> None:
	conn.execute(
		"""
		INSERT INTO platform_wallets (user_id, platform, balance, created_at, updated_at)
		VALUES (?, ?, 0, ?, ?)
		ON CONFLICT(user_id, platform) DO NOTHING
		""",
		(user_id, platform, now_iso, now_iso),
	)


def _set_platform_balance(conn, user_id: int, platform: str, balance: float, now_iso: str) -> None:
	_ensure_platform_wallet_row(conn, user_id, platform, now_iso)
	conn.execute(
		"""
		UPDATE platform_wallets
		SET balance = ?, updated_at = ?
		WHERE user_id = ? AND platform = ?
		""",
		(float(balance), now_iso, user_id, platform),
	)


def _deactivate_linked_accounts(conn, user_id: int) -> None:
	now_iso = _to_iso(_utc_now())
	conn.execute(
		"""
		DELETE FROM linked_accounts
		WHERE is_active = 0
		  AND EXISTS (
			SELECT 1
			FROM linked_accounts AS la_active
			WHERE la_active.user_id = ?
			  AND la_active.is_active = 1
			  AND la_active.provider = linked_accounts.provider
			  AND la_active.provider_user_id = linked_accounts.provider_user_id
		  )
		""",
		(user_id,),
	)
	conn.execute(
		"""
		UPDATE linked_accounts
		SET is_active = 0, unlinked_at = ?
		WHERE user_id = ? AND is_active = 1
		""",
		(now_iso, user_id),
	)


def _find_recoverable_inactive_user_id(conn, active_user_id: int) -> int | None:
	"""Busca un user_id histórico inactivo para reutilizar al hacer split."""
	rows = conn.execute(
		"""
		SELECT inactive_user_id
		FROM user_id_links
		WHERE primary_user_id = ? AND is_active = 1
		ORDER BY created_at DESC, id DESC
		""",
		(active_user_id,),
	).fetchall()

	for row in rows:
		candidate_id = int(row["inactive_user_id"])
		if candidate_id == active_user_id:
			continue

		exists = conn.execute(
			"SELECT 1 FROM users WHERE user_id = ? LIMIT 1",
			(candidate_id,),
		).fetchone()
		if not exists:
			continue

		has_discord = conn.execute(
			"SELECT 1 FROM discord_profile WHERE user_id = ? LIMIT 1",
			(candidate_id,),
		).fetchone()
		has_youtube = conn.execute(
			"SELECT 1 FROM youtube_profile WHERE user_id = ? LIMIT 1",
			(candidate_id,),
		).fetchone()

		# Reutilizar solo si está libre de perfiles activos
		if not has_discord and not has_youtube:
			return candidate_id

	return None


def _split_linked_user(conn, active_user_id: int, keep_provider: str) -> UnlinkResult:
	if keep_provider not in {"discord", "youtube"}:
		return UnlinkResult(success=False, message="Proveedor de desvinculación no soportado")

	move_provider = "youtube" if keep_provider == "discord" else "discord"
	now_iso = _to_iso(_utc_now())

	balances_rows = conn.execute(
		"SELECT platform, balance FROM platform_wallets WHERE user_id = ?",
		(active_user_id,),
	).fetchall()
	current_balances: dict[str, float] = {"discord": 0.0, "youtube": 0.0}
	for balance_row in balances_rows:
		platform_name = str(balance_row["platform"])
		if platform_name in current_balances:
			current_balances[platform_name] = float(balance_row["balance"] or 0.0)

	keep_balance = float(current_balances.get("discord", 0.0) + current_balances.get("youtube", 0.0))

	discord_profile = conn.execute(
		"SELECT * FROM discord_profile WHERE user_id = ? LIMIT 1",
		(active_user_id,),
	).fetchone()
	youtube_profile = conn.execute(
		"SELECT * FROM youtube_profile WHERE user_id = ? LIMIT 1",
		(active_user_id,),
	).fetchone()

	if not discord_profile or not youtube_profile:
		return UnlinkResult(
			success=False,
			message="La cuenta no está vinculada entre Discord y YouTube",
			kept_user_id=active_user_id,
		)

	if move_provider == "discord":
		move_username = str(discord_profile["discord_username"] or discord_profile["discord_id"])
		move_provider_user_id = str(discord_profile["discord_id"])
		keep_provider_user_id = str(youtube_profile["youtube_channel_id"])
		keep_snapshot = str(youtube_profile["youtube_username"] or "")
		move_snapshot = str(discord_profile["discord_username"] or "")
	else:
		move_username = str(youtube_profile["youtube_username"] or youtube_profile["youtube_channel_id"])
		move_provider_user_id = str(youtube_profile["youtube_channel_id"])
		keep_provider_user_id = str(discord_profile["discord_id"])
		keep_snapshot = str(discord_profile["discord_username"] or "")
		move_snapshot = str(youtube_profile["youtube_username"] or "")

	recovered_user_id = _find_recoverable_inactive_user_id(conn, active_user_id)
	if recovered_user_id is not None:
		new_user_id = recovered_user_id
		conn.execute(
			"UPDATE users SET username = ?, updated_at = ? WHERE user_id = ?",
			(move_username, now_iso, new_user_id),
		)
	else:
		conn.execute(
			"INSERT INTO users (username, created_at, updated_at) VALUES (?, ?, ?)",
			(move_username, now_iso, now_iso),
		)
		new_user_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])

	if move_provider == "discord":
		conn.execute(
			"UPDATE discord_profile SET user_id = ?, updated_at = ? WHERE id = ?",
			(new_user_id, now_iso, discord_profile["id"]),
		)
	else:
		conn.execute(
			"UPDATE youtube_profile SET user_id = ?, updated_at = ? WHERE id = ?",
			(new_user_id, now_iso, youtube_profile["id"]),
		)

	# Política solicitada: donde se desvincula conserva saldo total acumulado; la otra plataforma queda en 0.
	_set_platform_balance(conn, active_user_id, keep_provider, keep_balance, now_iso)
	_set_platform_balance(conn, active_user_id, move_provider, 0.0, now_iso)
	_set_platform_balance(conn, new_user_id, move_provider, 0.0, now_iso)
	_set_platform_balance(conn, new_user_id, keep_provider, 0.0, now_iso)

	_sync_total_wallet(conn, active_user_id)
	_sync_total_wallet(conn, new_user_id)

	# Refrescar linked_accounts para reflejar split
	_deactivate_linked_accounts(conn, active_user_id)
	_register_linked_account(
		conn,
		user_id=active_user_id,
		provider=keep_provider,
		provider_user_id=keep_provider_user_id,
		provider_username_snapshot=keep_snapshot,
	)
	_register_linked_account(
		conn,
		user_id=new_user_id,
		provider=move_provider,
		provider_user_id=move_provider_user_id,
		provider_username_snapshot=move_snapshot,
	)

	# Desactivar mapeo de IDs inactivos que apunten a este user principal en split
	conn.execute(
		"""
		UPDATE user_id_links
		SET is_active = 0
		WHERE primary_user_id = ?
		""",
		(active_user_id,),
	)

	return UnlinkResult(
		success=True,
		message=f"Desvinculación completada: {keep_provider} conserva el saldo total y {move_provider} reinicia en 0",
		kept_user_id=active_user_id,
		new_user_id=new_user_id,
	)


def unlink_from_discord(discord_user_id: str) -> UnlinkResult:
	"""Desvincula desde Discord: Discord conserva saldo, YouTube queda en 0."""
	conn = get_connection()
	try:
		_ensure_link_tables(conn)
		conn.execute("BEGIN IMMEDIATE")

		profile = conn.execute(
			"SELECT user_id FROM discord_profile WHERE discord_id = ? LIMIT 1",
			(str(discord_user_id),),
		).fetchone()
		if not profile:
			conn.rollback()
			return UnlinkResult(success=False, message="No se encontró perfil de Discord para desvincular")

		active_user_id = _resolve_active_user_id_in_conn(conn, int(profile["user_id"])) or int(profile["user_id"])
		result = _split_linked_user(conn, active_user_id=active_user_id, keep_provider="discord")
		if not result.success:
			conn.rollback()
			return result

		conn.commit()
		return result
	except Exception as exc:
		conn.rollback()
		return UnlinkResult(success=False, message=f"Error al desvincular desde Discord: {exc}")
	finally:
		conn.close()


def unlink_from_youtube(youtube_channel_id: str) -> UnlinkResult:
	"""Desvincula desde YouTube: YouTube conserva saldo, Discord queda en 0."""
	conn = get_connection()
	try:
		_ensure_link_tables(conn)
		conn.execute("BEGIN IMMEDIATE")

		profile = conn.execute(
			"SELECT user_id FROM youtube_profile WHERE youtube_channel_id = ? LIMIT 1",
			(str(youtube_channel_id),),
		).fetchone()
		if not profile:
			conn.rollback()
			return UnlinkResult(success=False, message="No se encontró perfil de YouTube para desvincular")

		active_user_id = _resolve_active_user_id_in_conn(conn, int(profile["user_id"])) or int(profile["user_id"])
		result = _split_linked_user(conn, active_user_id=active_user_id, keep_provider="youtube")
		if not result.success:
			conn.rollback()
			return result

		conn.commit()
		return result
	except Exception as exc:
		conn.rollback()
		return UnlinkResult(success=False, message=f"Error al desvincular desde YouTube: {exc}")
	finally:
		conn.close()


def force_link_discord_to_universal(
	discord_user_id: str,
	discord_user_name: str,
	universal_user_id: int,
) -> ForceLinkResult:
	"""Vincula forzadamente un usuario Discord a un ID universal de YouTube."""
	conn = get_connection()
	now_iso = _to_iso(_utc_now())
	try:
		_ensure_link_tables(conn)
		_ensure_optional_tables_for_merge(conn)
		conn.execute("BEGIN IMMEDIATE")

		target_user_id = _resolve_active_user_id_in_conn(conn, int(universal_user_id)) or int(universal_user_id)

		target_user = conn.execute(
			"SELECT user_id, username FROM users WHERE user_id = ? LIMIT 1",
			(target_user_id,),
		).fetchone()
		if not target_user:
			conn.rollback()
			return ForceLinkResult(success=False, message="ID universal no existe")

		target_youtube = conn.execute(
			"SELECT id, youtube_channel_id FROM youtube_profile WHERE user_id = ? LIMIT 1",
			(target_user_id,),
		).fetchone()
		if not target_youtube:
			conn.rollback()
			return ForceLinkResult(
				success=False,
				message="El ID universal indicado no corresponde a una cuenta de YouTube",
			)

		source_discord = conn.execute(
			"SELECT id, user_id FROM discord_profile WHERE discord_id = ? LIMIT 1",
			(str(discord_user_id),),
		).fetchone()

		if source_discord is None:
			conn.execute(
				"INSERT INTO users (username, created_at, updated_at) VALUES (?, ?, ?)",
				(str(discord_user_name or discord_user_id), now_iso, now_iso),
			)
			source_user_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
			conn.execute(
				"""
				INSERT INTO discord_profile (
					user_id, discord_id, discord_username, avatar_url, created_at, updated_at
				)
				VALUES (?, ?, ?, NULL, ?, ?)
				""",
				(source_user_id, str(discord_user_id), str(discord_user_name or ""), now_iso, now_iso),
			)
			source_discord_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
		else:
			source_user_id = int(source_discord["user_id"])
			source_discord_id = int(source_discord["id"])

		source_user_id = _resolve_active_user_id_in_conn(conn, source_user_id) or source_user_id

		source_youtube = conn.execute(
			"SELECT youtube_channel_id FROM youtube_profile WHERE user_id = ? LIMIT 1",
			(source_user_id,),
		).fetchone()
		if source_youtube and source_user_id != target_user_id:
			source_channel = str(source_youtube["youtube_channel_id"])
			target_channel = str(target_youtube["youtube_channel_id"])
			if source_channel != target_channel:
				conn.rollback()
				return ForceLinkResult(
					success=False,
					message="Ese Discord ya está vinculado a otro YouTube. Desvincula primero.",
				)

		if source_user_id != target_user_id:
			_merge_user_data(conn, from_user_id=source_user_id, to_user_id=target_user_id)

		conn.execute(
			"UPDATE discord_profile SET user_id = ?, discord_username = ?, updated_at = ? WHERE id = ?",
			(target_user_id, str(discord_user_name or ""), now_iso, source_discord_id),
		)

		_deactivate_linked_accounts(conn, target_user_id)
		_register_linked_account(
			conn,
			user_id=target_user_id,
			provider="discord",
			provider_user_id=str(discord_user_id),
			provider_username_snapshot=str(discord_user_name or ""),
		)
		_register_linked_account(
			conn,
			user_id=target_user_id,
			provider="youtube",
			provider_user_id=str(target_youtube["youtube_channel_id"]),
			provider_username_snapshot=None,
		)

		_sync_total_wallet(conn, target_user_id)
		conn.commit()

		return ForceLinkResult(
			success=True,
			message="Vinculación forzada completada",
			target_user_id=target_user_id,
			previous_user_id=source_user_id,
		)
	except Exception as exc:
		conn.rollback()
		return ForceLinkResult(success=False, message=f"Error en force_link: {exc}")
	finally:
		conn.close()


def force_unlink_discord(discord_user_id: str) -> UnlinkResult:
	"""Desvinculación forzada de Discord (misma lógica de /desvincular)."""
	return unlink_from_discord(str(discord_user_id))
