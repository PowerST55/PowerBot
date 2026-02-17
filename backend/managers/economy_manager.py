"""
Economy manager for awarding points with cooldowns.
Funciones robustas para consultar y gestionar puntos en todas las plataformas.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, List, Tuple

from backend.database import get_connection
from backend.managers.user_manager import (
	get_discord_profile_by_discord_id,
	get_youtube_profile_by_channel_id,
	get_user_by_id
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
			balance INTEGER NOT NULL DEFAULT 0,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
		)
		"""
	)
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS wallet_ledger (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER NOT NULL,
			amount INTEGER NOT NULL,
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


def award_message_points(
	discord_id: str,
	guild_id: int,
	amount: int,
	interval_seconds: int,
	source_id: str | None = None,
) -> Dict[str, Optional[int]]:
	"""
	Awards message points with cooldown enforcement.
	Solo actualiza puntos globales (wallets), sin separación por servidor.
	"""
	if amount <= 0 or interval_seconds < 0:
		return {
			"awarded": 0,
			"points_added": 0,
			"global_points": None,
		}

	profile = get_discord_profile_by_discord_id(str(discord_id))
	if not profile:
		return {
			"awarded": 0,
			"points_added": 0,
			"global_points": None,
		}

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
				return {
					"awarded": 0,
					"points_added": 0,
					"global_points": None,
				}

		row = conn.execute(
			"SELECT last_earned_at FROM earning_cooldown WHERE user_id = ? AND guild_id = ?",
			(profile.user_id, guild_id_text),
		).fetchone()

		if row:
			try:
				last_earned = datetime.fromisoformat(row["last_earned_at"])
			except Exception:
				last_earned = None
			if last_earned:
				elapsed = (now - last_earned).total_seconds()
				if elapsed < interval_seconds:
					conn.rollback()
					return {
						"awarded": 0,
						"points_added": 0,
						"global_points": None,
					}

		# Crear wallet si no existe
		conn.execute(
			"INSERT INTO wallets (user_id, balance, created_at, updated_at) VALUES (?, 0, ?, ?) "
			"ON CONFLICT(user_id) DO NOTHING",
			(profile.user_id, now_iso, now_iso),
		)
		
		# Actualizar balance global
		conn.execute(
			"UPDATE wallets SET balance = balance + ?, updated_at = ? WHERE user_id = ?",
			(amount, now_iso, profile.user_id),
		)

		# Registrar transacción
		conn.execute(
			"""
			INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, channel_id, source_id, created_at)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?)
			""",
			(
				profile.user_id,
				amount,
				"message_earning",
				"discord",
				guild_id_text,
				None,
				source_id,
				now_iso,
			),
		)

		if source_id:
			conn.execute(
				"INSERT INTO earning_events (platform, source_id, user_id, created_at) VALUES (?, ?, ?, ?)",
				("discord", source_id, profile.user_id, now_iso),
			)

		# Actualizar cooldown
		conn.execute(
			"""
			INSERT INTO earning_cooldown (user_id, guild_id, last_earned_at, created_at, updated_at)
			VALUES (?, ?, ?, ?, ?)
			ON CONFLICT(user_id, guild_id)
			DO UPDATE SET last_earned_at = ?, updated_at = ?
			""",
			(
				profile.user_id,
				guild_id_text,
				now_iso,
				now_iso,
				now_iso,
				now_iso,
				now_iso,
			),
		)

		# Obtener balance final
		global_points = conn.execute(
			"SELECT balance FROM wallets WHERE user_id = ?",
			(profile.user_id,),
		).fetchone()

		conn.commit()

		return {
			"awarded": 1,
			"points_added": amount,
			"global_points": global_points["balance"] if global_points else None,
		}
	except Exception:
		conn.rollback()
		raise
	finally:
		conn.close()


# ============================================================
# FUNCIONES DE CONSULTA DE PUNTOS (ROBUSTAS)
# ============================================================

def get_user_balance_by_id(user_id: int) -> Dict[str, any]:
	"""
	Obtiene el balance completo de un usuario por ID universal.
	
	Esta es la función principal y más robusta para consultar puntos.
	Se usa internamente por las otras funciones de consulta.
	
	Args:
		user_id: ID único universal del usuario
		
	Returns:
		Dict con:
			- global_points: Puntos globales totales
			- user_exists: Si el usuario existe
			
	Example:
		>>> balance = get_user_balance_by_id(42)
		>>> print(f"Puntos globales: {balance['global_points']}")
	"""
	conn = get_connection()
	try:
		# Verificar si el usuario existe
		user = conn.execute(
			"SELECT user_id FROM users WHERE user_id = ?",
			(user_id,)
		).fetchone()
		
		if not user:
			return {
				"user_exists": False,
				"global_points": 0
			}
		
		# Obtener puntos globales
		wallet = conn.execute(
			"SELECT balance FROM wallets WHERE user_id = ?",
			(user_id,)
		).fetchone()
		
		global_points = wallet["balance"] if wallet else 0
		
		return {
			"user_exists": True,
			"global_points": global_points
		}
		
	finally:
		conn.close()


def get_user_balance_by_discord_id(discord_id: str) -> Optional[Dict[str, any]]:
	"""
	Obtiene el balance de un usuario por su Discord ID.
	
	Args:
		discord_id: Discord ID del usuario (string numérico)
		
	Returns:
		Dict con balance o None si no existe
		
	Example:
		>>> balance = get_user_balance_by_discord_id("123456789012345678")
		>>> if balance:
		...     print(f"Puntos: {balance['global_points']}")
	"""
	profile = get_discord_profile_by_discord_id(str(discord_id))
	if not profile:
		return None
	
	return get_user_balance_by_id(profile.user_id)


def get_user_balance_by_youtube_id(youtube_channel_id: str) -> Optional[Dict[str, any]]:
	"""
	Obtiene el balance de un usuario por su YouTube Channel ID.
	
	Args:
		youtube_channel_id: YouTube Channel ID del usuario
		
	Returns:
		Dict con balance o None si no existe
		
	Example:
		>>> balance = get_user_balance_by_youtube_id("UCxxxxxxxxxxxxxxxxxx")
		>>> if balance:
		...     print(f"Puntos: {balance['global_points']}")
	"""
	profile = get_youtube_profile_by_channel_id(youtube_channel_id)
	if not profile:
		return None
	
	return get_user_balance_by_id(profile.user_id)


def get_user_balance_smart(identifier: str, platform: Optional[str] = None) -> Optional[Dict[str, any]]:
	"""
	Búsqueda inteligente de balance que detecta automáticamente la plataforma.
	
	Args:
		identifier: ID del usuario (puede ser Discord ID, YouTube ID, o ID global)
		platform: Plataforma preferida si hay ambigüedad ("discord", "youtube", "global")
		
	Returns:
		Dict con balance o None si no existe
		
	Example:
		>>> # Auto-detecta
		>>> balance = get_user_balance_smart("123456789012345678")  # Discord
		>>> balance = get_user_balance_smart("42")  # ID Global
		>>> balance = get_user_balance_smart("UCxxxxxxxxxx")  # YouTube
	"""
	identifier = str(identifier).strip()
	
	# 1. Intentar ID global si es numérico corto
	if identifier.isdigit() and len(identifier) < 10:
		try:
			result = get_user_balance_by_id(int(identifier))
			if result and result["user_exists"]:
				return result
		except ValueError:
			pass
	
	# 2. Intentar YouTube si empieza con UC
	if identifier.startswith("UC") and len(identifier) > 10:
		result = get_user_balance_by_youtube_id(identifier)
		if result:
			return result
	
	# 3. Intentar Discord si es numérico largo
	if identifier.isdigit() and len(identifier) >= 10:
		result = get_user_balance_by_discord_id(identifier)
		if result:
			return result
	
	# 4. Intentar plataforma preferida
	if platform == "discord":
		return get_user_balance_by_discord_id(identifier)
	elif platform == "youtube":
		return get_user_balance_by_youtube_id(identifier)
	elif platform == "global":
		try:
			return get_user_balance_by_id(int(identifier))
		except ValueError:
			return None
	
	return None





def transfer_points(
	from_user_id: int,
	to_user_id: int,
	amount: int,
	guild_id: Optional[str] = None,
	platform: str = "discord"
) -> Dict[str, any]:
	"""
	Transfiere puntos de un usuario a otro de forma atómica.
	
	Args:
		from_user_id: ID del usuario que envía puntos
		to_user_id: ID del usuario que recibe puntos
		amount: Cantidad de puntos a transferir (debe ser positiva)
		guild_id: ID del servidor donde se realiza la transferencia
		platform: Plataforma donde se realiza ("discord", "youtube", etc.)
		
	Returns:
		Dict con:
			- success: True si la transferencia fue exitosa
			- error: Mensaje de error si falló
			- from_balance: Balance final del remitente
			- to_balance: Balance final del destinatario
			
	Example:
		>>> result = transfer_points(42, 83, 100, guild_id="123456789")
		>>> if result["success"]:
		...     print(f"Transferencia exitosa. Balance final: {result['from_balance']}")
	"""
	if amount <= 0:
		return {
			"success": False,
			"error": "La cantidad debe ser positiva",
			"from_balance": None,
			"to_balance": None
		}
	
	if from_user_id == to_user_id:
		return {
			"success": False,
			"error": "No puedes transferir puntos a ti mismo",
			"from_balance": None,
			"to_balance": None
		}
	
	conn = get_connection()
	try:
		_ensure_wallet_tables(conn)
		now_iso = datetime.utcnow().isoformat()
		
		conn.execute("BEGIN IMMEDIATE")
		
		# Verificar que ambos usuarios existen
		from_user = conn.execute(
			"SELECT user_id FROM users WHERE user_id = ?",
			(from_user_id,)
		).fetchone()
		
		to_user = conn.execute(
			"SELECT user_id FROM users WHERE user_id = ?",
			(to_user_id,)
		).fetchone()
		
		if not from_user:
			conn.rollback()
			return {
				"success": False,
				"error": "El usuario remitente no existe",
				"from_balance": None,
				"to_balance": None
			}
		
		if not to_user:
			conn.rollback()
			return {
				"success": False,
				"error": "El usuario destinatario no existe",
				"from_balance": None,
				"to_balance": None
			}
		
		# Crear wallets si no existen
		conn.execute(
			"INSERT INTO wallets (user_id, balance, created_at, updated_at) VALUES (?, 0, ?, ?) "
			"ON CONFLICT(user_id) DO NOTHING",
			(from_user_id, now_iso, now_iso)
		)
		conn.execute(
			"INSERT INTO wallets (user_id, balance, created_at, updated_at) VALUES (?, 0, ?, ?) "
			"ON CONFLICT(user_id) DO NOTHING",
			(to_user_id, now_iso, now_iso)
		)
		
		# Verificar balance del remitente
		from_wallet = conn.execute(
			"SELECT balance FROM wallets WHERE user_id = ?",
			(from_user_id,)
		).fetchone()
		
		if not from_wallet or from_wallet["balance"] < amount:
			conn.rollback()
			current_balance = from_wallet["balance"] if from_wallet else 0
			return {
				"success": False,
				"error": f"Fondos insuficientes. Tienes {current_balance:,} puntos",
				"from_balance": current_balance,
				"to_balance": None
			}
		
		# Restar puntos del remitente
		conn.execute(
			"UPDATE wallets SET balance = balance - ?, updated_at = ? WHERE user_id = ?",
			(amount, now_iso, from_user_id)
		)
		
		# Sumar puntos al destinatario
		conn.execute(
			"UPDATE wallets SET balance = balance + ?, updated_at = ? WHERE user_id = ?",
			(amount, now_iso, to_user_id)
		)
		
		# Registrar transacción del remitente (gasto)
		conn.execute(
			"""INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, created_at)
			   VALUES (?, ?, ?, ?, ?, ?)""",
			(from_user_id, -amount, f"transfer_to_user_{to_user_id}", platform, guild_id, now_iso)
		)
		
		# Registrar transacción del destinatario (ingreso)
		conn.execute(
			"""INSERT INTO wallet_ledger (user_id, amount, reason, platform, guild_id, created_at)
			   VALUES (?, ?, ?, ?, ?, ?)""",
			(to_user_id, amount, f"transfer_from_user_{from_user_id}", platform, guild_id, now_iso)
		)
		
		# Obtener balances finales
		from_balance = conn.execute(
			"SELECT balance FROM wallets WHERE user_id = ?",
			(from_user_id,)
		).fetchone()
		
		to_balance = conn.execute(
			"SELECT balance FROM wallets WHERE user_id = ?",
			(to_user_id,)
		).fetchone()
		
		conn.commit()
		
		return {
			"success": True,
			"error": None,
			"from_balance": from_balance["balance"] if from_balance else 0,
			"to_balance": to_balance["balance"] if to_balance else 0
		}
		
	except Exception as e:
		conn.rollback()
		return {
			"success": False,
			"error": f"Error en la transferencia: {str(e)}",
			"from_balance": None,
			"to_balance": None
		}
	finally:
		conn.close()


def get_user_transactions(user_id: int, limit: int = 50) -> List[Dict[str, any]]:
	"""
	Obtiene el historial de transacciones de un usuario.
	
	Args:
		user_id: ID único universal del usuario
		limit: Número máximo de transacciones a retornar
		
	Returns:
		List[Dict]: Lista de transacciones ordenadas por fecha (más reciente primero)
		
	Example:
		>>> txs = get_user_transactions(42, limit=10)
		>>> for tx in txs:
		...     print(f"{tx['created_at']}: {tx['amount']:+d} pts - {tx['reason']}")
	"""
	conn = get_connection()
	try:
		rows = conn.execute(
			"""SELECT id, user_id, amount, reason, platform, guild_id, channel_id, created_at
			   FROM wallet_ledger 
			   WHERE user_id = ? 
			   ORDER BY created_at DESC 
			   LIMIT ?""",
			(user_id, limit)
		).fetchall()
		return [dict(row) for row in rows]
	finally:
		conn.close()


# ============================================================
# LEADERBOARDS
# ============================================================

def get_global_leaderboard(limit: int = 10) -> List[Dict[str, any]]:
	"""
	Obtiene el top de usuarios con más puntos globales.
	
	Args:
		limit: Número de usuarios a retornar
		
	Returns:
		List[Dict]: Top usuarios ordenados por balance descendente
		
	Example:
		>>> top = get_global_leaderboard(10)
		>>> for i, user in enumerate(top, 1):
		...     print(f"{i}. {user['username']}: {user['balance']:,} pts")
	"""
	conn = get_connection()
	try:
		rows = conn.execute(
			"""SELECT w.user_id, w.balance, u.username
			   FROM wallets w
			   JOIN users u ON w.user_id = u.user_id
			   WHERE w.balance > 0
			   ORDER BY w.balance DESC
			   LIMIT ?""",
			(limit,)
		).fetchall()
		return [dict(row) for row in rows]
	finally:
		conn.close()



