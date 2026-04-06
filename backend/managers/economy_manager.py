"""
Economy manager for awarding points with cooldowns.
Funciones robustas para consultar y gestionar puntos en todas las plataformas.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

from backend.database import get_connection
from backend.managers.link_manager import resolve_active_user_id
from backend.managers.user_manager import (
	get_discord_profile_by_discord_id,
	get_discord_profile_by_user_id,
	get_youtube_profile_by_channel_id,
	get_youtube_profile_by_user_id,
)

SUPPORTED_PLATFORMS = ("discord", "youtube")
COMMON_FUND_ACCOUNT = "common_fund"
CASINO_FUND_ACCOUNT = "casino_fund"
MINE_FUND_ACCOUNT = "mine_fund"

SYSTEM_FUND_DESCRIPTIONS = {
	COMMON_FUND_ACCOUNT: "Fondo comun de la economia",
	CASINO_FUND_ACCOUNT: "Fondo operativo del casino",
	MINE_FUND_ACCOUNT: "Fondo operativo de la mina",
}

EARNING_FULL_FUND_COVERAGE = 20
EARNING_HALF_FUND_COVERAGE = 8
CASINO_BANKRUPTCY_THRESHOLD = 0.0


def _round_amount(value: float | int) -> float:
	return round(float(value), 2)


def _calculate_dynamic_earning_amount(base_amount: float, common_fund_balance: float) -> float:
	"""Reduce el earning cuando el fondo comun pierde estabilidad.

	Regla basada en cobertura del fondo respecto al earning base:
	- cobertura >= 20x: 100%
	- cobertura >= 8x: 50%
	- cobertura > 0: 25%
	- sin saldo: 0%
	"""
	base_amount = _round_amount(base_amount)
	common_fund_balance = _round_amount(common_fund_balance)
	if base_amount <= 0 or common_fund_balance <= 0:
		return 0.0

	if common_fund_balance >= _round_amount(base_amount * EARNING_FULL_FUND_COVERAGE):
		multiplier = 1.0
	elif common_fund_balance >= _round_amount(base_amount * EARNING_HALF_FUND_COVERAGE):
		multiplier = 0.5
	else:
		multiplier = 0.25

	effective_amount = _round_amount(base_amount * multiplier)
	if effective_amount <= 0:
		return 0.0
	return _round_amount(min(effective_amount, common_fund_balance))


def _enqueue_progress_event(
	platform: str,
	platform_user_id: str,
	previous_balance: float,
	new_balance: float,
) -> None:
	"""Encola eventos de progreso económico para que Discord los publique en economy_channel."""
	try:
		data_dir = Path(__file__).resolve().parents[1] / "data" / "discord_bot"
		queue_file = data_dir / "economy_external_events.json"
		data_dir.mkdir(parents=True, exist_ok=True)

		event = {
			"platform": str(platform).strip().lower(),
			"platform_user_id": str(platform_user_id).strip(),
			"previous_balance": float(previous_balance),
			"new_balance": float(new_balance),
		}

		queue: list[dict] = []
		if queue_file.exists():
			try:
				with open(queue_file, "r", encoding="utf-8") as file:
					loaded = json.load(file)
					if isinstance(loaded, list):
						queue = loaded
			except Exception:
				queue = []

		queue.append(event)
		with open(queue_file, "w", encoding="utf-8") as file:
			json.dump(queue, file, indent=2, ensure_ascii=False)
	except Exception:
		pass


def _enqueue_user_progress_event(
	user_id: int,
	platform: str,
	previous_balance: float,
	new_balance: float,
) -> None:
	"""Encola eventos de progreso para la plataforma operativa del movimiento."""
	platform = _normalize_user_platform(platform)
	if platform == "discord":
		discord_profile = get_discord_profile_by_user_id(int(user_id))
		if discord_profile and getattr(discord_profile, "discord_id", None):
			_enqueue_progress_event(
				platform="discord",
				platform_user_id=str(discord_profile.discord_id),
				previous_balance=_round_amount(previous_balance),
				new_balance=_round_amount(new_balance),
			)
		return

	youtube_profile = get_youtube_profile_by_user_id(int(user_id))
	if youtube_profile and getattr(youtube_profile, "youtube_channel_id", None):
		_enqueue_progress_event(
			platform="youtube",
			platform_user_id=str(youtube_profile.youtube_channel_id),
			previous_balance=_round_amount(previous_balance),
			new_balance=_round_amount(new_balance),
		)


def _ensure_earning_cooldown_table(conn) -> None:
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS earning_cooldown (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER NOT NULL,
			guild_id TEXT NOT NULL,
			last_earned_at TEXT NOT NULL,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
			UNIQUE(user_id, guild_id)
		)
		"""
	)


def _ensure_wallet_tables(conn) -> None:
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS wallets (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER NOT NULL UNIQUE,
			balance REAL NOT NULL DEFAULT 0,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
		)
		"""
	)

	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS system_wallets (
			account_key TEXT PRIMARY KEY,
			balance REAL NOT NULL DEFAULT 0,
			description TEXT,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
		)
		"""
	)

	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS system_wallet_ledger (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			account_key TEXT NOT NULL,
			amount REAL NOT NULL,
			reason TEXT NOT NULL,
			counterparty_type TEXT,
			counterparty_id TEXT,
			platform TEXT,
			guild_id TEXT,
			channel_id TEXT,
			source_id TEXT,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			UNIQUE(account_key, source_id)
		)
		"""
	)

	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS platform_wallets (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER NOT NULL,
			platform TEXT NOT NULL,
			balance REAL NOT NULL DEFAULT 0,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
			UNIQUE(user_id, platform)
		)
		"""
	)

	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS wallet_ledger (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER NOT NULL,
			amount REAL NOT NULL,
			reason TEXT NOT NULL,
			platform TEXT,
			guild_id TEXT,
			channel_id TEXT,
			source_id TEXT,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
			UNIQUE(user_id, source_id)
		)
		"""
	)


def _ensure_earning_events_table(conn) -> None:
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS earning_events (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			platform TEXT NOT NULL,
			source_id TEXT NOT NULL,
			user_id INTEGER NOT NULL,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
			UNIQUE(platform, source_id)
		)
		"""
	)


def _ensure_platform_wallet_row(conn, user_id: int, platform: str, now_iso: str) -> None:
	conn.execute(
		"""
		INSERT INTO platform_wallets (user_id, platform, balance, created_at, updated_at)
		VALUES (?, ?, 0, ?, ?)
		ON CONFLICT(user_id, platform) DO NOTHING
		""",
		(user_id, platform, now_iso, now_iso),
	)


def _normalize_user_platform(platform: str | None) -> str:
	platform_text = str(platform or "discord").strip().lower()
	if platform_text not in SUPPORTED_PLATFORMS:
		return "discord"
	return platform_text


def _ensure_system_fund_row(conn, account_key: str, now_iso: str) -> None:
	conn.execute(
		"""
		INSERT INTO system_wallets (account_key, balance, description, created_at, updated_at)
		VALUES (?, 0, ?, ?, ?)
		ON CONFLICT(account_key) DO NOTHING
		""",
		(
			str(account_key).strip().lower(),
			SYSTEM_FUND_DESCRIPTIONS.get(str(account_key).strip().lower(), "Fondo del sistema"),
			now_iso,
			now_iso,
		),
	)


def _ensure_common_fund_row(conn, now_iso: str) -> None:
	_ensure_system_fund_row(conn, COMMON_FUND_ACCOUNT, now_iso)


def _get_system_fund_balance_in_conn(conn, account_key: str, now_iso: str | None = None) -> float:
	ensure_now_iso = now_iso or datetime.utcnow().isoformat()
	account_key = str(account_key).strip().lower()
	_ensure_system_fund_row(conn, account_key, ensure_now_iso)
	row = conn.execute(
		"SELECT balance FROM system_wallets WHERE account_key = ?",
		(account_key,),
	).fetchone()
	return _round_amount(row["balance"] if row else 0.0)


def _get_common_fund_balance_in_conn(conn, now_iso: str | None = None) -> float:
	return _get_system_fund_balance_in_conn(conn, COMMON_FUND_ACCOUNT, now_iso)


def _log_system_fund_movement(
	conn,
	account_key: str,
	amount: float,
	reason: str,
	now_iso: str,
	counterparty_type: str | None = None,
	counterparty_id: str | None = None,
	platform: str | None = None,
	guild_id: str | None = None,
	channel_id: str | None = None,
	source_id: str | None = None,
) -> None:
	conn.execute(
		"""
		INSERT INTO system_wallet_ledger (
			account_key, amount, reason, counterparty_type, counterparty_id,
			platform, guild_id, channel_id, source_id, created_at
		)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(
			str(account_key).strip().lower(),
			_round_amount(amount),
			reason,
			counterparty_type,
			counterparty_id,
			platform,
			guild_id,
			channel_id,
			source_id,
			now_iso,
		),
	)


def _log_common_fund_movement(conn, amount: float, reason: str, now_iso: str, **log_kwargs) -> None:
	_log_system_fund_movement(
		conn,
		COMMON_FUND_ACCOUNT,
		amount,
		reason,
		now_iso,
		**log_kwargs,
	)


def _credit_system_fund(conn, account_key: str, amount: float, now_iso: str, **log_kwargs) -> float:
	credit = _round_amount(amount)
	account_key = str(account_key).strip().lower()
	_ensure_system_fund_row(conn, account_key, now_iso)
	conn.execute(
		"UPDATE system_wallets SET balance = balance + ?, updated_at = ? WHERE account_key = ?",
		(credit, now_iso, account_key),
	)
	_log_system_fund_movement(conn, account_key, credit, now_iso=now_iso, **log_kwargs)
	return _get_system_fund_balance_in_conn(conn, account_key, now_iso)


def _credit_common_fund(conn, amount: float, now_iso: str, **log_kwargs) -> float:
	return _credit_system_fund(conn, COMMON_FUND_ACCOUNT, amount, now_iso, **log_kwargs)


def _debit_system_fund(conn, account_key: str, amount: float, now_iso: str, allow_negative: bool = False, **log_kwargs) -> float:
	debit = _round_amount(amount)
	account_key = str(account_key).strip().lower()
	_ensure_system_fund_row(conn, account_key, now_iso)
	current_balance = _get_system_fund_balance_in_conn(conn, account_key, now_iso)
	if not allow_negative and current_balance < debit:
		raise ValueError(
			f"Fondos insuficientes en {account_key}. Disponible: {current_balance:,.2f}"
		)
	conn.execute(
		"UPDATE system_wallets SET balance = balance - ?, updated_at = ? WHERE account_key = ?",
		(debit, now_iso, account_key),
	)
	_log_system_fund_movement(conn, account_key, -debit, now_iso=now_iso, **log_kwargs)
	return _get_system_fund_balance_in_conn(conn, account_key, now_iso)


def _debit_common_fund(conn, amount: float, now_iso: str, allow_negative: bool = False, **log_kwargs) -> float:
	return _debit_system_fund(conn, COMMON_FUND_ACCOUNT, amount, now_iso, allow_negative=allow_negative, **log_kwargs)


def _sync_wallet_total(conn, user_id: int, now_iso: str) -> float:
	row = conn.execute(
		"SELECT COALESCE(SUM(balance), 0) AS total FROM platform_wallets WHERE user_id = ?",
		(user_id,),
	).fetchone()
	total = _round_amount(row["total"] if row else 0.0)

	conn.execute(
		"""
		INSERT INTO wallets (user_id, balance, created_at, updated_at)
		VALUES (?, ?, ?, ?)
		ON CONFLICT(user_id)
		DO UPDATE SET balance = excluded.balance, updated_at = excluded.updated_at
		""",
		(user_id, total, now_iso, now_iso),
	)
	return total


def _credit_platform_balance(conn, user_id: int, platform: str, amount: float, now_iso: str) -> float:
	_credit = _round_amount(amount)
	platform = _normalize_user_platform(platform)
	_ensure_platform_wallet_row(conn, user_id, platform, now_iso)
	conn.execute(
		"UPDATE platform_wallets SET balance = balance + ?, updated_at = ? WHERE user_id = ? AND platform = ?",
		(_credit, now_iso, user_id, platform),
	)
	return _sync_wallet_total(conn, user_id, now_iso)


def _get_platform_balances(conn, user_id: int) -> Dict[str, float]:
	rows = conn.execute(
		"SELECT platform, balance FROM platform_wallets WHERE user_id = ?",
		(user_id,),
	).fetchall()
	result = {"discord": 0.0, "youtube": 0.0}
	for row in rows:
		platform = str(row["platform"])
		if platform in result:
			result[platform] = _round_amount(row["balance"])
	return result


def _deduct_from_combined_balance(conn, user_id: int, amount: float, preferred_platform: str, now_iso: str) -> bool:
	pending = _round_amount(amount)
	if pending <= 0:
		return True

	balances = _get_platform_balances(conn, user_id)
	preferred_platform = _normalize_user_platform(preferred_platform)
	ordered_platforms: list[str] = []
	for platform in [preferred_platform, "discord", "youtube"]:
		if platform in balances and platform not in ordered_platforms:
			ordered_platforms.append(platform)

	available = _round_amount(sum(balances.values()))
	if available < pending:
		return False

	for platform in ordered_platforms:
		if pending <= 0:
			break
		current = balances.get(platform, 0.0)
		if current <= 0:
			continue
		take = _round_amount(min(current, pending))
		if take <= 0:
			continue
		conn.execute(
			"UPDATE platform_wallets SET balance = balance - ?, updated_at = ? WHERE user_id = ? AND platform = ?",
			(take, now_iso, user_id, platform),
		)
		pending = _round_amount(pending - take)

	_sync_wallet_total(conn, user_id, now_iso)
	return True


def _transfer_common_fund_to_user(
	conn,
	user_id: int,
	amount: float,
	reason: str,
	platform: str,
	now_iso: str,
	guild_id: Optional[str] = None,
	channel_id: Optional[str] = None,
	source_id: Optional[str] = None,
	allow_negative_common_fund: bool = False,
) -> float:
	amount = _round_amount(amount)
	ledger_platform = str(platform or "discord").strip().lower()
	user_platform = _normalize_user_platform(platform)
	_debit_common_fund(
		conn,
		amount,
		now_iso,
		allow_negative=allow_negative_common_fund,
		reason=reason,
		counterparty_type="user",
		counterparty_id=str(user_id),
		platform=ledger_platform,
		guild_id=guild_id,
		channel_id=channel_id,
		source_id=source_id,
	)
	new_total = _credit_platform_balance(conn, user_id, user_platform, amount, now_iso)
	conn.execute(
		"""
		INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, channel_id, source_id, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(user_id, amount, reason, ledger_platform, guild_id, channel_id, source_id, now_iso),
	)
	return new_total


def _transfer_system_fund_to_user(
	conn,
	account_key: str,
	user_id: int,
	amount: float,
	reason: str,
	platform: str,
	now_iso: str,
	guild_id: Optional[str] = None,
	channel_id: Optional[str] = None,
	source_id: Optional[str] = None,
	allow_negative_system_fund: bool = False,
) -> float:
	amount = _round_amount(amount)
	ledger_platform = str(platform or "discord").strip().lower()
	user_platform = _normalize_user_platform(platform)
	_debit_system_fund(
		conn,
		account_key,
		amount,
		now_iso,
		allow_negative=allow_negative_system_fund,
		reason=reason,
		counterparty_type="user",
		counterparty_id=str(user_id),
		platform=ledger_platform,
		guild_id=guild_id,
		channel_id=channel_id,
		source_id=source_id,
	)
	new_total = _credit_platform_balance(conn, user_id, user_platform, amount, now_iso)
	conn.execute(
		"""
		INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, channel_id, source_id, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(user_id, amount, reason, ledger_platform, guild_id, channel_id, source_id, now_iso),
	)
	return new_total


def _transfer_user_to_common_fund(
	conn,
	user_id: int,
	amount: float,
	reason: str,
	platform: str,
	now_iso: str,
	guild_id: Optional[str] = None,
	channel_id: Optional[str] = None,
	source_id: Optional[str] = None,
	allow_negative_balance: bool = False,
) -> float:
	amount = _round_amount(amount)
	ledger_platform = str(platform or "discord").strip().lower()
	user_platform = _normalize_user_platform(platform)
	if allow_negative_balance:
		_ensure_platform_wallet_row(conn, user_id, user_platform, now_iso)
		conn.execute(
			"UPDATE platform_wallets SET balance = balance - ?, updated_at = ? WHERE user_id = ? AND platform = ?",
			(amount, now_iso, user_id, user_platform),
		)
		new_total = _sync_wallet_total(conn, user_id, now_iso)
	else:
		ok = _deduct_from_combined_balance(
			conn,
			user_id,
			amount,
			preferred_platform=user_platform,
			now_iso=now_iso,
		)
		if not ok:
			raise ValueError("Saldo insuficiente para transferir al fondo comun")
		new_total = _sync_wallet_total(conn, user_id, now_iso)

	_credit_common_fund(
		conn,
		amount,
		now_iso,
		reason=reason,
		counterparty_type="user",
		counterparty_id=str(user_id),
		platform=ledger_platform,
		guild_id=guild_id,
		channel_id=channel_id,
		source_id=source_id,
	)
	conn.execute(
		"""
		INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, channel_id, source_id, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(user_id, -amount, reason, ledger_platform, guild_id, channel_id, source_id, now_iso),
	)
	return new_total


def _transfer_user_to_system_fund(
	conn,
	account_key: str,
	user_id: int,
	amount: float,
	reason: str,
	platform: str,
	now_iso: str,
	guild_id: Optional[str] = None,
	channel_id: Optional[str] = None,
	source_id: Optional[str] = None,
	allow_negative_balance: bool = False,
) -> float:
	amount = _round_amount(amount)
	ledger_platform = str(platform or "discord").strip().lower()
	user_platform = _normalize_user_platform(platform)
	if allow_negative_balance:
		_ensure_platform_wallet_row(conn, user_id, user_platform, now_iso)
		conn.execute(
			"UPDATE platform_wallets SET balance = balance - ?, updated_at = ? WHERE user_id = ? AND platform = ?",
			(amount, now_iso, user_id, user_platform),
		)
		new_total = _sync_wallet_total(conn, user_id, now_iso)
	else:
		ok = _deduct_from_combined_balance(
			conn,
			user_id,
			amount,
			preferred_platform=user_platform,
			now_iso=now_iso,
		)
		if not ok:
			raise ValueError(f"Saldo insuficiente para transferir a {account_key}")
		new_total = _sync_wallet_total(conn, user_id, now_iso)

	_credit_system_fund(
		conn,
		account_key,
		amount,
		now_iso,
		reason=reason,
		counterparty_type="user",
		counterparty_id=str(user_id),
		platform=ledger_platform,
		guild_id=guild_id,
		channel_id=channel_id,
		source_id=source_id,
	)
	conn.execute(
		"""
		INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, channel_id, source_id, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(user_id, -amount, reason, ledger_platform, guild_id, channel_id, source_id, now_iso),
	)
	return new_total


def award_message_points(
	discord_id: str,
	guild_id: int,
	amount: float,
	interval_seconds: int,
	source_id: str | None = None,
) -> Dict[str, Optional[float]]:
	"""Aumenta puntos por mensaje de Discord con cooldown e idempotencia."""
	amount = _round_amount(amount)
	if amount <= 0 or interval_seconds < 0:
		return {"awarded": 0, "points_added": 0.0, "global_points": None}

	profile = get_discord_profile_by_discord_id(str(discord_id))
	if not profile:
		return {"awarded": 0, "points_added": 0.0, "global_points": None}

	user_id = resolve_active_user_id(int(profile.user_id))
	now = datetime.utcnow()
	now_iso = now.isoformat()
	guild_id_text = str(guild_id)

	conn = get_connection()
	try:
		_ensure_earning_cooldown_table(conn)
		_ensure_wallet_tables(conn)
		_ensure_earning_events_table(conn)
		conn.execute("BEGIN IMMEDIATE")

		if source_id:
			existing = conn.execute(
				"SELECT 1 FROM earning_events WHERE platform = ? AND source_id = ?",
				("discord", source_id),
			).fetchone()
			if existing:
				conn.rollback()
				return {"awarded": 0, "points_added": 0.0, "global_points": None}

		row = conn.execute(
			"SELECT last_earned_at FROM earning_cooldown WHERE user_id = ? AND guild_id = ?",
			(user_id, guild_id_text),
		).fetchone()

		if row:
			try:
				last_earned = datetime.fromisoformat(row["last_earned_at"])
			except Exception:
				last_earned = None
			if last_earned and (now - last_earned).total_seconds() < interval_seconds:
				conn.rollback()
				return {"awarded": 0, "points_added": 0.0, "global_points": None}

		effective_amount = _calculate_dynamic_earning_amount(
			base_amount=amount,
			common_fund_balance=_get_common_fund_balance_in_conn(conn, now_iso),
		)
		if effective_amount <= 0:
			conn.rollback()
			return {"awarded": 0, "points_added": 0.0, "global_points": None}

		try:
			global_points = _transfer_common_fund_to_user(
				conn,
				user_id=user_id,
				amount=effective_amount,
				reason="message_earning",
				platform="discord",
				now_iso=now_iso,
				guild_id=guild_id_text,
				channel_id=None,
				source_id=source_id,
			)
		except ValueError:
			conn.rollback()
			return {"awarded": 0, "points_added": 0.0, "global_points": None}

		if source_id:
			conn.execute(
				"INSERT INTO earning_events (platform, source_id, user_id, created_at) VALUES (?, ?, ?, ?)",
				("discord", source_id, user_id, now_iso),
			)

		conn.execute(
			"""
			INSERT INTO earning_cooldown (user_id, guild_id, last_earned_at, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?)
			ON CONFLICT(user_id, guild_id)
			DO UPDATE SET last_earned_at = ?, updated_at = ?
			""",
			(user_id, guild_id_text, now_iso, now_iso, now_iso, now_iso, now_iso),
		)

		conn.commit()
		return {"awarded": 1, "points_added": effective_amount, "global_points": global_points}
	except Exception:
		conn.rollback()
		raise
	finally:
		conn.close()


def award_youtube_message_points(
	youtube_channel_id: str,
	chat_id: str,
	amount: float,
	interval_seconds: int,
	source_id: str | None = None,
) -> Dict[str, Optional[float]]:
	"""Aumenta puntos por mensaje de YouTube con cooldown e idempotencia."""
	amount = _round_amount(amount)
	if amount <= 0 or interval_seconds < 0:
		return {"awarded": 0, "points_added": 0.0, "global_points": None}

	profile = get_youtube_profile_by_channel_id(str(youtube_channel_id))
	if not profile:
		return {"awarded": 0, "points_added": 0.0, "global_points": None}

	user_id = resolve_active_user_id(int(profile.user_id))
	now = datetime.utcnow()
	now_iso = now.isoformat()
	chat_id_text = str(chat_id)

	conn = get_connection()
	try:
		_ensure_earning_cooldown_table(conn)
		_ensure_wallet_tables(conn)
		_ensure_earning_events_table(conn)
		conn.execute("BEGIN IMMEDIATE")

		if source_id:
			existing = conn.execute(
				"SELECT 1 FROM earning_events WHERE platform = ? AND source_id = ?",
				("youtube", source_id),
			).fetchone()
			if existing:
				conn.rollback()
				return {"awarded": 0, "points_added": 0.0, "global_points": None}

		row = conn.execute(
			"SELECT last_earned_at FROM earning_cooldown WHERE user_id = ? AND guild_id = ?",
			(user_id, chat_id_text),
		).fetchone()

		if row:
			try:
				last_earned = datetime.fromisoformat(row["last_earned_at"])
			except Exception:
				last_earned = None
			if last_earned and (now - last_earned).total_seconds() < interval_seconds:
				conn.rollback()
				return {"awarded": 0, "points_added": 0.0, "global_points": None}

		effective_amount = _calculate_dynamic_earning_amount(
			base_amount=amount,
			common_fund_balance=_get_common_fund_balance_in_conn(conn, now_iso),
		)
		if effective_amount <= 0:
			conn.rollback()
			return {"awarded": 0, "points_added": 0.0, "global_points": None}

		try:
			global_points = _transfer_common_fund_to_user(
				conn,
				user_id=user_id,
				amount=effective_amount,
				reason="message_earning",
				platform="youtube",
				now_iso=now_iso,
				guild_id=chat_id_text,
				channel_id=str(youtube_channel_id),
				source_id=source_id,
			)
		except ValueError:
			conn.rollback()
			return {"awarded": 0, "points_added": 0.0, "global_points": None}

		if source_id:
			conn.execute(
				"INSERT INTO earning_events (platform, source_id, user_id, created_at) VALUES (?, ?, ?, ?)",
				("youtube", source_id, user_id, now_iso),
			)

		conn.execute(
			"""
			INSERT INTO earning_cooldown (user_id, guild_id, last_earned_at, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?)
			ON CONFLICT(user_id, guild_id)
			DO UPDATE SET last_earned_at = ?, updated_at = ?
			""",
			(user_id, chat_id_text, now_iso, now_iso, now_iso, now_iso, now_iso),
		)

		conn.commit()
		return {"awarded": 1, "points_added": effective_amount, "global_points": global_points}
	except Exception:
		conn.rollback()
		raise
	finally:
		conn.close()


# ============================================================
# FUNCIONES DE CONSULTA DE PUNTOS (ROBUSTAS)
# ============================================================

def get_user_balance_by_id(user_id: int) -> Dict[str, any]:
	"""Obtiene el balance completo de un usuario por ID universal."""
	resolved_user_id = resolve_active_user_id(int(user_id))
	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		user = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (resolved_user_id,)).fetchone()
		if not user:
			return {"user_exists": False, "global_points": 0.0, "platform_balances": {"discord": 0.0, "youtube": 0.0}}

		now_iso = datetime.utcnow().isoformat()
		_ensure_platform_wallet_row(conn, resolved_user_id, "discord", now_iso)
		_ensure_platform_wallet_row(conn, resolved_user_id, "youtube", now_iso)
		global_points = _sync_wallet_total(conn, resolved_user_id, now_iso)
		platform_balances = _get_platform_balances(conn, resolved_user_id)
		conn.commit()

		return {
			"user_exists": True,
			"global_points": global_points,
			"platform_balances": platform_balances,
		}
	finally:
		conn.close()


def get_user_balance_by_discord_id(discord_id: str) -> Optional[Dict[str, any]]:
	profile = get_discord_profile_by_discord_id(str(discord_id))
	if not profile:
		return None
	return get_user_balance_by_id(profile.user_id)


def get_user_balance_by_youtube_id(youtube_channel_id: str) -> Optional[Dict[str, any]]:
	profile = get_youtube_profile_by_channel_id(youtube_channel_id)
	if not profile:
		return None
	return get_user_balance_by_id(profile.user_id)


def get_user_balance_smart(identifier: str, platform: Optional[str] = None) -> Optional[Dict[str, any]]:
	identifier = str(identifier).strip()

	if identifier.isdigit() and len(identifier) < 10:
		try:
			result = get_user_balance_by_id(int(identifier))
			if result and result["user_exists"]:
				return result
		except ValueError:
			pass

	if identifier.startswith("UC") and len(identifier) > 10:
		result = get_user_balance_by_youtube_id(identifier)
		if result:
			return result

	if identifier.isdigit() and len(identifier) >= 10:
		result = get_user_balance_by_discord_id(identifier)
		if result:
			return result

	if platform == "discord":
		return get_user_balance_by_discord_id(identifier)
	if platform == "youtube":
		return get_user_balance_by_youtube_id(identifier)
	if platform == "global":
		try:
			return get_user_balance_by_id(int(identifier))
		except ValueError:
			return None

	return None


def get_total_balance(user_id: int) -> float:
	"""Obtiene saldo combinado total del usuario (Discord + YouTube)."""
	balance = get_user_balance_by_id(int(user_id))
	if not balance.get("user_exists"):
		return 0.0
	return _round_amount(balance.get("global_points", 0.0))


def get_common_fund_balance() -> float:
	"""Obtiene el saldo actual del fondo comun."""
	return get_system_fund_balance(COMMON_FUND_ACCOUNT)


def get_casino_fund_balance() -> float:
	"""Obtiene el saldo actual del fondo de casino."""
	return get_system_fund_balance(CASINO_FUND_ACCOUNT)


def get_mine_fund_balance() -> float:
	"""Obtiene el saldo actual del fondo de mina."""
	return get_system_fund_balance(MINE_FUND_ACCOUNT)


def get_system_fund_balance(account_key: str) -> float:
	"""Obtiene el saldo actual de un fondo del sistema."""
	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		return _get_system_fund_balance_in_conn(conn, account_key)
	finally:
		conn.close()


def get_circulating_supply() -> float:
	"""Obtiene la cantidad de pews en circulacion dentro de wallets de usuarios."""
	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		row = conn.execute("SELECT COALESCE(SUM(balance), 0) AS total FROM wallets").fetchone()
		return _round_amount(row["total"] if row else 0.0)
	finally:
		conn.close()


def get_total_supply() -> float:
	"""Obtiene la oferta total actual sumando circulacion y wallets del sistema."""
	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		user_row = conn.execute("SELECT COALESCE(SUM(balance), 0) AS total FROM wallets").fetchone()
		system_row = conn.execute("SELECT COALESCE(SUM(balance), 0) AS total FROM system_wallets").fetchone()
		user_total = float(user_row["total"] if user_row else 0.0)
		system_total = float(system_row["total"] if system_row else 0.0)
		return _round_amount(user_total + system_total)
	finally:
		conn.close()


def get_economy_overview() -> Dict[str, float]:
	"""Resumen rapido del estado de la economia centralizada."""
	common_fund = get_common_fund_balance()
	casino_fund = get_casino_fund_balance()
	mine_fund = get_mine_fund_balance()
	circulating = get_circulating_supply()
	total_supply = _round_amount(common_fund + casino_fund + mine_fund + circulating)
	return {
		"common_fund": common_fund,
		"casino_fund": casino_fund,
		"mine_fund": mine_fund,
		"circulating_supply": circulating,
		"total_supply": total_supply,
	}


def adjust_common_fund(delta: float, reason: str = "manual_common_fund_adjustment") -> Dict[str, float]:
	"""Ajusta manualmente el fondo comun sin afectar wallets de usuarios."""
	return adjust_system_fund(COMMON_FUND_ACCOUNT, delta, reason=reason)


def tax_everyone_to_common_fund(
	amount_per_user: float,
	reason: str = "emergency_tax_everyone",
) -> Dict[str, float | int]:
	"""Aplica un impuesto global en una sola transacción.

	- Deduce hasta `amount_per_user` del saldo combinado de cada usuario.
	- Si un usuario tiene menos saldo, se deduce solo lo disponible.
	- Todo lo recaudado se acredita al fondo común.
	"""
	amount_per_user = _round_amount(amount_per_user)
	if amount_per_user <= 0:
		raise ValueError("La cantidad a cobrar por usuario debe ser mayor a 0")

	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		now_iso = datetime.utcnow().isoformat()
		conn.execute("BEGIN IMMEDIATE")

		# Aseguramos que el fondo común exista antes de aplicar movimientos.
		_ensure_system_fund_row(conn, COMMON_FUND_ACCOUNT, now_iso)

		rows = conn.execute(
			"""
			SELECT user_id, COALESCE(SUM(balance), 0) AS total_balance
			FROM platform_wallets
			GROUP BY user_id
			HAVING total_balance > 0
			"""
		).fetchall()

		users_scanned = len(rows)
		taxed_users = 0
		total_collected = 0.0

		for row in rows:
			user_id = int(row["user_id"])
			available = _round_amount(row["total_balance"])
			if available <= 0:
				continue

			amount_to_collect = _round_amount(min(amount_per_user, available))
			if amount_to_collect <= 0:
				continue

			_transfer_user_to_common_fund(
				conn,
				user_id=user_id,
				amount=amount_to_collect,
				reason=reason,
				platform="discord",
				now_iso=now_iso,
				guild_id=None,
				channel_id=None,
				source_id=f"{reason}:{now_iso}:user:{user_id}",
				allow_negative_balance=False,
			)

			taxed_users += 1
			total_collected = _round_amount(total_collected + amount_to_collect)

		common_fund_after = _get_common_fund_balance_in_conn(conn, now_iso)
		circulating_after = _round_amount(
			conn.execute("SELECT COALESCE(SUM(balance), 0) AS total FROM wallets").fetchone()["total"]
		)
		total_supply_after = _round_amount(
			common_fund_after
			+ _get_system_fund_balance_in_conn(conn, CASINO_FUND_ACCOUNT, now_iso)
			+ _get_system_fund_balance_in_conn(conn, MINE_FUND_ACCOUNT, now_iso)
			+ circulating_after
		)

		conn.commit()
		return {
			"amount_per_user": amount_per_user,
			"users_scanned": users_scanned,
			"taxed_users": taxed_users,
			"total_collected": total_collected,
			"common_fund": _round_amount(common_fund_after),
			"circulating_supply": _round_amount(circulating_after),
			"total_supply": _round_amount(total_supply_after),
		}
	except Exception:
		conn.rollback()
		raise
	finally:
		conn.close()


def adjust_casino_fund(delta: float, reason: str = "manual_casino_fund_adjustment") -> Dict[str, float]:
	"""Ajusta manualmente el fondo de casino sin afectar wallets de usuarios."""
	return adjust_system_fund(CASINO_FUND_ACCOUNT, delta, reason=reason)


def adjust_mine_fund(delta: float, reason: str = "manual_mine_fund_adjustment") -> Dict[str, float]:
	"""Ajusta manualmente el fondo de mina sin afectar wallets de usuarios."""
	return adjust_system_fund(MINE_FUND_ACCOUNT, delta, reason=reason)


def adjust_system_fund(account_key: str, delta: float, reason: str = "manual_system_fund_adjustment") -> Dict[str, float]:
	"""Ajusta manualmente un fondo del sistema sin afectar wallets de usuarios."""
	delta = _round_amount(delta)
	if delta == 0:
		return get_economy_overview()

	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		now_iso = datetime.utcnow().isoformat()
		conn.execute("BEGIN IMMEDIATE")
		if delta > 0:
			fund_balance = _credit_system_fund(
				conn,
				account_key,
				delta,
				now_iso,
				reason=reason,
				counterparty_type="system",
				counterparty_id="manual",
				platform="system",
				source_id=f"{reason}:{now_iso}:credit",
			)
		else:
			fund_balance = _debit_system_fund(
				conn,
				account_key,
				abs(delta),
				now_iso,
				allow_negative=False,
				reason=reason,
				counterparty_type="system",
				counterparty_id="manual",
				platform="system",
				source_id=f"{reason}:{now_iso}:debit",
			)
		conn.commit()
		overview = get_economy_overview()
		overview[str(account_key).strip().lower()] = _round_amount(fund_balance)
		return overview
	except Exception:
		conn.rollback()
		raise
	finally:
		conn.close()


def transfer_system_funds(
	from_account_key: str,
	to_account_key: str,
	amount: float,
	reason: str = "system_fund_transfer",
) -> Dict[str, float]:
	"""Transfiere saldo entre dos fondos del sistema en una sola transacción."""
	amount = _round_amount(amount)
	from_account_key = str(from_account_key).strip().lower()
	to_account_key = str(to_account_key).strip().lower()
	if amount <= 0:
		raise ValueError("La cantidad a transferir debe ser mayor a 0")
	if from_account_key == to_account_key:
		raise ValueError("No puedes transferir entre el mismo fondo")

	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		now_iso = datetime.utcnow().isoformat()
		conn.execute("BEGIN IMMEDIATE")

		from_before = _get_system_fund_balance_in_conn(conn, from_account_key, now_iso)
		to_before = _get_system_fund_balance_in_conn(conn, to_account_key, now_iso)
		if from_before < amount:
			conn.rollback()
			raise ValueError(
				f"Fondos insuficientes en {from_account_key}. Disponible: {from_before:,.2f}"
			)

		from_after = _debit_system_fund(
			conn,
			from_account_key,
			amount,
			now_iso,
			allow_negative=False,
			reason=reason,
			counterparty_type="system_fund",
			counterparty_id=to_account_key,
			platform="system",
			source_id=f"{reason}:{now_iso}:debit:{from_account_key}->{to_account_key}",
		)
		to_after = _credit_system_fund(
			conn,
			to_account_key,
			amount,
			now_iso,
			reason=reason,
			counterparty_type="system_fund",
			counterparty_id=from_account_key,
			platform="system",
			source_id=f"{reason}:{now_iso}:credit:{from_account_key}->{to_account_key}",
		)
		conn.commit()
		return {
			"transferred": amount,
			"from_account": from_account_key,
			"to_account": to_account_key,
			"from_balance_before": _round_amount(from_before),
			"from_balance_after": _round_amount(from_after),
			"to_balance_before": _round_amount(to_before),
			"to_balance_after": _round_amount(to_after),
		}
	except Exception:
		conn.rollback()
		raise
	finally:
		conn.close()


def apply_balance_delta(
	user_id: int,
	delta: float,
	reason: str,
	platform: str,
	guild_id: Optional[str] = None,
	channel_id: Optional[str] = None,
	source_id: Optional[str] = None,
	allow_negative_balance: bool = False,
	system_account: Optional[str] = None,
) -> float:
	"""Aplica un delta de saldo en wallet por plataforma y devuelve el total resultante."""
	requested_platform = str(platform or "discord").strip().lower()
	user_platform = _normalize_user_platform(requested_platform)
	target_system_account = str(system_account or COMMON_FUND_ACCOUNT).strip().lower()

	resolved_user_id = resolve_active_user_id(int(user_id))
	delta = _round_amount(delta)
	if delta == 0:
		return get_total_balance(resolved_user_id)

	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		now_iso = datetime.utcnow().isoformat()
		conn.execute("BEGIN IMMEDIATE")

		user_row = conn.execute(
			"SELECT user_id FROM users WHERE user_id = ?",
			(resolved_user_id,),
		).fetchone()
		if not user_row:
			conn.rollback()
			raise ValueError(f"Usuario no existe: {resolved_user_id}")

		_ensure_platform_wallet_row(conn, resolved_user_id, "discord", now_iso)
		_ensure_platform_wallet_row(conn, resolved_user_id, "youtube", now_iso)
		_ensure_system_fund_row(conn, target_system_account, now_iso)
		previous_total = _sync_wallet_total(conn, resolved_user_id, now_iso)

		if delta > 0:
			new_total = _transfer_system_fund_to_user(
				conn,
				account_key=target_system_account,
				user_id=resolved_user_id,
				amount=delta,
				reason=reason,
				platform=requested_platform,
				now_iso=now_iso,
				guild_id=guild_id,
				channel_id=channel_id,
				source_id=source_id,
			)
		else:
			new_total = _transfer_user_to_system_fund(
				conn,
				account_key=target_system_account,
				user_id=resolved_user_id,
				amount=abs(delta),
				reason=reason,
				platform=requested_platform,
				now_iso=now_iso,
				guild_id=guild_id,
				channel_id=channel_id,
				source_id=source_id,
				allow_negative_balance=allow_negative_balance,
			)

		conn.commit()

		final_total = _round_amount(new_total)
		_enqueue_user_progress_event(
			user_id=resolved_user_id,
			platform=user_platform,
			previous_balance=previous_total,
			new_balance=final_total,
		)

		return final_total
	except Exception:
		conn.rollback()
		raise
	finally:
		conn.close()


def settle_casino_bet(
	user_id: int,
	delta: float,
	reason: str,
	platform: str,
	guild_id: Optional[str] = None,
	channel_id: Optional[str] = None,
	source_id: Optional[str] = None,
	allow_negative_casino_fund: bool = True,
) -> Dict[str, any]:
	"""Liquida una jugada de casino contra el fondo del casino.

	Delta positivo: el usuario gana y el casino paga.
	Delta negativo: el usuario pierde y el casino cobra.
	"""
	requested_platform = str(platform or "discord").strip().lower()
	user_platform = _normalize_user_platform(requested_platform)
	resolved_user_id = resolve_active_user_id(int(user_id))
	delta = _round_amount(delta)

	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		now_iso = datetime.utcnow().isoformat()
		conn.execute("BEGIN IMMEDIATE")

		user_row = conn.execute(
			"SELECT user_id FROM users WHERE user_id = ?",
			(resolved_user_id,),
		).fetchone()
		if not user_row:
			conn.rollback()
			return {
				"success": False,
				"error": f"Usuario no existe: {resolved_user_id}",
				"user_balance": None,
				"casino_balance_before": None,
				"casino_balance_after": None,
				"bankruptcy_triggered": False,
			}

		_ensure_platform_wallet_row(conn, resolved_user_id, "discord", now_iso)
		_ensure_platform_wallet_row(conn, resolved_user_id, "youtube", now_iso)
		_ensure_system_fund_row(conn, CASINO_FUND_ACCOUNT, now_iso)

		previous_total = _sync_wallet_total(conn, resolved_user_id, now_iso)
		casino_balance_before = _get_system_fund_balance_in_conn(conn, CASINO_FUND_ACCOUNT, now_iso)

		if delta > 0:
			new_total = _transfer_system_fund_to_user(
				conn,
				account_key=CASINO_FUND_ACCOUNT,
				user_id=resolved_user_id,
				amount=delta,
				reason=reason,
				platform=requested_platform,
				now_iso=now_iso,
				guild_id=guild_id,
				channel_id=channel_id,
				source_id=source_id,
				allow_negative_system_fund=allow_negative_casino_fund,
			)
		elif delta < 0:
			new_total = _transfer_user_to_system_fund(
				conn,
				account_key=CASINO_FUND_ACCOUNT,
				user_id=resolved_user_id,
				amount=abs(delta),
				reason=reason,
				platform=requested_platform,
				now_iso=now_iso,
				guild_id=guild_id,
				channel_id=channel_id,
				source_id=source_id,
				allow_negative_balance=False,
			)
		else:
			new_total = previous_total

		casino_balance_after = _get_system_fund_balance_in_conn(conn, CASINO_FUND_ACCOUNT, now_iso)
		conn.commit()

		_enqueue_user_progress_event(
			user_id=resolved_user_id,
			platform=user_platform,
			previous_balance=previous_total,
			new_balance=new_total,
		)

		return {
			"success": True,
			"error": None,
			"user_balance": _round_amount(new_total),
			"user_balance_before": _round_amount(previous_total),
			"casino_balance_before": _round_amount(casino_balance_before),
			"casino_balance_after": _round_amount(casino_balance_after),
			"bankruptcy_triggered": (
				_round_amount(casino_balance_before) > CASINO_BANKRUPTCY_THRESHOLD
				and _round_amount(casino_balance_after) <= CASINO_BANKRUPTCY_THRESHOLD
			),
		}
	except Exception as exc:
		conn.rollback()
		return {
			"success": False,
			"error": str(exc),
			"user_balance": None,
			"casino_balance_before": None,
			"casino_balance_after": None,
			"bankruptcy_triggered": False,
		}
	finally:
		conn.close()


def transfer_points(
	from_user_id: int,
	to_user_id: int,
	amount: float,
	guild_id: Optional[str] = None,
	platform: str = "discord",
) -> Dict[str, any]:
	"""Transfiere puntos usando saldo combinado (Discord + YouTube)."""
	amount = _round_amount(amount)
	if amount <= 0:
		return {"success": False, "error": "La cantidad debe ser positiva", "from_balance": None, "to_balance": None}

	from_user_id = resolve_active_user_id(int(from_user_id))
	to_user_id = resolve_active_user_id(int(to_user_id))

	if from_user_id == to_user_id:
		return {"success": False, "error": "No puedes transferir puntos a ti mismo", "from_balance": None, "to_balance": None}

	platform = str(platform or "discord").lower()
	platform = _normalize_user_platform(platform)

	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		now_iso = datetime.utcnow().isoformat()
		conn.execute("BEGIN IMMEDIATE")

		from_user = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (from_user_id,)).fetchone()
		to_user = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (to_user_id,)).fetchone()
		if not from_user:
			conn.rollback()
			return {"success": False, "error": "El usuario remitente no existe", "from_balance": None, "to_balance": None}
		if not to_user:
			conn.rollback()
			return {"success": False, "error": "El usuario destinatario no existe", "from_balance": None, "to_balance": None}

		for user_id in (from_user_id, to_user_id):
			_ensure_platform_wallet_row(conn, user_id, "discord", now_iso)
			_ensure_platform_wallet_row(conn, user_id, "youtube", now_iso)
			_sync_wallet_total(conn, user_id, now_iso)

		from_total = _sync_wallet_total(conn, from_user_id, now_iso)
		if from_total < amount:
			conn.rollback()
			return {
				"success": False,
				"error": f"Fondos insuficientes. Tienes {from_total:,.2f} puntos",
				"from_balance": from_total,
				"to_balance": None,
			}

		if not _deduct_from_combined_balance(conn, from_user_id, amount, platform, now_iso):
			conn.rollback()
			return {
				"success": False,
				"error": "No fue posible descontar el saldo combinado",
				"from_balance": None,
				"to_balance": None,
			}

		_credit_platform_balance(conn, to_user_id, platform, amount, now_iso)

		conn.execute(
			"""INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, created_at)
			   VALUES (?, ?, ?, ?, ?, ?)""",
			(from_user_id, -amount, f"transfer_to_user_{to_user_id}", platform, guild_id, now_iso),
		)
		conn.execute(
			"""INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, created_at)
			   VALUES (?, ?, ?, ?, ?, ?)""",
			(to_user_id, amount, f"transfer_from_user_{from_user_id}", platform, guild_id, now_iso),
		)

		from_balance = _sync_wallet_total(conn, from_user_id, now_iso)
		to_balance = _sync_wallet_total(conn, to_user_id, now_iso)
		conn.commit()

		if platform == "discord":
			from_profile = get_discord_profile_by_user_id(from_user_id)
			if from_profile and getattr(from_profile, "discord_id", None):
				_enqueue_progress_event(
					platform="discord",
					platform_user_id=str(from_profile.discord_id),
					previous_balance=_round_amount(from_balance + amount),
					new_balance=_round_amount(from_balance),
				)

			to_profile = get_discord_profile_by_user_id(to_user_id)
			if to_profile and getattr(to_profile, "discord_id", None):
				_enqueue_progress_event(
					platform="discord",
					platform_user_id=str(to_profile.discord_id),
					previous_balance=_round_amount(to_balance - amount),
					new_balance=_round_amount(to_balance),
				)

		return {
			"success": True,
			"error": None,
			"from_balance": from_balance,
			"to_balance": to_balance,
		}
	except Exception as e:
		conn.rollback()
		return {
			"success": False,
			"error": f"Error en la transferencia: {str(e)}",
			"from_balance": None,
			"to_balance": None,
		}
	finally:
		conn.close()


def get_user_transactions(user_id: int, limit: int = 50) -> List[Dict[str, any]]:
	"""Obtiene historial de transacciones del usuario (ID activo)."""
	user_id = resolve_active_user_id(int(user_id))
	conn = get_connection()
	try:
		rows = conn.execute(
			"""SELECT id, user_id, amount, reason, platform, guild_id, channel_id, created_at
			   FROM wallet_ledger
			   WHERE user_id = ?
			   ORDER BY created_at DESC
			   LIMIT ?""",
			(user_id, limit),
		).fetchall()
		return [dict(row) for row in rows]
	finally:
		conn.close()


# ============================================================
# LEADERBOARDS
# ============================================================

def get_global_leaderboard(limit: int = 10) -> List[Dict[str, any]]:
	"""Obtiene top global por balance total combinado."""
	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		rows = conn.execute(
			"""SELECT w.user_id, w.balance, u.username
			   FROM wallets w
			   JOIN users u ON w.user_id = u.user_id
			   WHERE w.balance > 0
			   ORDER BY w.balance DESC
			   LIMIT ?""",
			(limit,),
		).fetchall()
		return [dict(row) for row in rows]
	finally:
		conn.close()
