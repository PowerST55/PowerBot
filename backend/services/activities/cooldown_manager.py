"""
Sistema de cooldowns global para juegos.
Funciona para Discord y cualquier futuro servicio.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple


COOLDOWN_FILE = Path(__file__).resolve().parents[2] / "data" / "activities" / "cooldowns.json"


def load_cooldowns() -> Dict[str, Dict[str, float]]:
	"""
	Carga los cooldowns desde el archivo JSON.
	Estructura: {user_id: {game_type: timestamp_unix}}
	"""
	try:
		with COOLDOWN_FILE.open("r", encoding="utf-8") as handle:
			return json.load(handle)
	except (FileNotFoundError, json.JSONDecodeError):
		return {}


def save_cooldowns(cooldown_data: Dict[str, Dict[str, float]]) -> None:
	"""Guarda los cooldowns en el archivo JSON."""
	COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
	with COOLDOWN_FILE.open("w", encoding="utf-8") as handle:
		json.dump(cooldown_data, handle, indent=4, ensure_ascii=False)


def check_cooldown(user_id: str, game_type: str, cooldown_seconds: int) -> Tuple[bool, Optional[float]]:
	"""
	Verifica si un usuario puede jugar basandose en el cooldown.

	Args:
		user_id: ID del usuario
		game_type: Tipo de juego (gamble, slots, etc.)
		cooldown_seconds: Duracion del cooldown en segundos

	Returns:
		Tuple[puede_jugar, segundos_restantes]
		- puede_jugar: True si puede jugar, False si esta en cooldown
		- segundos_restantes: None si puede jugar, o los segundos que faltan
	"""
	if cooldown_seconds == 0:
		return True, None

	cooldowns = load_cooldowns()
	user_cooldowns = cooldowns.get(str(user_id), {})
	last_play_timestamp = user_cooldowns.get(game_type)

	if last_play_timestamp is None:
		return True, None

	now = datetime.now(timezone.utc).timestamp()
	elapsed = now - last_play_timestamp
	remaining = cooldown_seconds - elapsed

	if remaining <= 0:
		return True, None

	return False, round(remaining, 1)


def update_cooldown(user_id: str, game_type: str) -> None:
	"""
	Actualiza el cooldown de un usuario para un tipo de juego.

	Args:
		user_id: ID del usuario
		game_type: Tipo de juego (gamble, slots, etc.)
	"""
	cooldowns = load_cooldowns()

	if str(user_id) not in cooldowns:
		cooldowns[str(user_id)] = {}

	now = datetime.now(timezone.utc).timestamp()
	cooldowns[str(user_id)][game_type] = now

	save_cooldowns(cooldowns)


def reset_cooldown(user_id: str, game_type: str) -> None:
	"""
	Resetea el cooldown de un usuario para un tipo de juego.

	Args:
		user_id: ID del usuario
		game_type: Tipo de juego (gamble, slots, etc.)
	"""
	cooldowns = load_cooldowns()

	if str(user_id) in cooldowns and game_type in cooldowns[str(user_id)]:
		del cooldowns[str(user_id)][game_type]
		save_cooldowns(cooldowns)


def get_all_user_cooldowns(user_id: str) -> Dict[str, float]:
	"""
	Obtiene todos los cooldowns de un usuario.

	Args:
		user_id: ID del usuario

	Returns:
		Dict con game_type como clave y timestamp como valor
	"""
	cooldowns = load_cooldowns()
	return cooldowns.get(str(user_id), {})
