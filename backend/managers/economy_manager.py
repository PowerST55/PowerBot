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
)

SUPPORTED_PLATFORMS = ("discord", "youtube")


def _round_amount(value: float | int) -> float:
	return round(float(value), 2)


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

		global_points = _credit_platform_balance(conn, user_id, "discord", amount, now_iso)

		conn.execute(
			"""
			INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, channel_id, source_id, created_at)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?)
			""",
			(user_id, amount, "message_earning", "discord", guild_id_text, None, source_id, now_iso),
		)

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
		return {"awarded": 1, "points_added": amount, "global_points": global_points}
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

		global_points = _credit_platform_balance(conn, user_id, "youtube", amount, now_iso)

		conn.execute(
			"""
			INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, channel_id, source_id, created_at)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?)
			""",
			(
				user_id,
				amount,
				"message_earning",
				"youtube",
				chat_id_text,
				str(youtube_channel_id),
				source_id,
				now_iso,
			),
		)

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
		return {"awarded": 1, "points_added": amount, "global_points": global_points}
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


def apply_balance_delta(
	user_id: int,
	delta: float,
	reason: str,
	platform: str,
	guild_id: Optional[str] = None,
	channel_id: Optional[str] = None,
	source_id: Optional[str] = None,
) -> float:
	"""Aplica un delta de saldo en wallet por plataforma y devuelve el total resultante."""
	platform = str(platform or "discord").lower()
	if platform not in SUPPORTED_PLATFORMS:
		platform = "discord"

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
		previous_total = _sync_wallet_total(conn, resolved_user_id, now_iso)

		if delta > 0:
			new_total = _credit_platform_balance(conn, resolved_user_id, platform, delta, now_iso)
		else:
			ok = _deduct_from_combined_balance(
				conn,
				resolved_user_id,
				abs(delta),
				preferred_platform=platform,
				now_iso=now_iso,
			)
			if not ok:
				conn.rollback()
				raise ValueError("Saldo insuficiente para aplicar el delta")
			new_total = _sync_wallet_total(conn, resolved_user_id, now_iso)

		conn.execute(
			"""
			INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, channel_id, source_id, created_at)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?)
			""",
			(
				resolved_user_id,
				delta,
				reason,
				platform,
				guild_id,
				channel_id,
				source_id,
				now_iso,
			),
		)

		conn.commit()

		final_total = _round_amount(new_total)
		if platform == "discord":
			discord_profile = get_discord_profile_by_user_id(resolved_user_id)
			if discord_profile and getattr(discord_profile, "discord_id", None):
				_enqueue_progress_event(
					platform="discord",
					platform_user_id=str(discord_profile.discord_id),
					previous_balance=_round_amount(previous_total),
					new_balance=final_total,
				)

		return final_total
	except Exception:
		conn.rollback()
		raise
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
	if platform not in SUPPORTED_PLATFORMS:
		platform = "discord"

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
