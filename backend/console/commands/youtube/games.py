"""
Helpers de configuración de juegos YouTube desde consola.
"""

from __future__ import annotations

from backend.services.activities import games_config


def apply_youtube_game_settings(ctx, game_name: str, args: list[str]) -> bool:
	"""
	Aplica configuración de juego (gamble/slots) para YouTube.

	Uso:
	  yt set gamble <limite> <cooldown_segundos>
	  yt set slots <limite> <cooldown_segundos>
	"""
	if len(args) != 2:
		ctx.error(f"Uso: yt set {game_name} <limite> <cooldown_segundos>")
		return False

	limit_raw, cooldown_raw = args[0].strip(), args[1].strip()

	try:
		limit = float(limit_raw)
	except ValueError:
		ctx.error("El limite debe ser un numero (ej: 150 o 150.5)")
		return False

	try:
		cooldown = int(cooldown_raw)
	except ValueError:
		ctx.error("El cooldown debe ser un numero entero en segundos (ej: 300)")
		return False

	if limit < 0 or cooldown < 0:
		ctx.error("Limit y cooldown deben ser >= 0")
		return False

	if game_name == "gamble":
		result = games_config.set_gamble_config(limit, cooldown)
		ctx.success("Configuración de gamble actualizada")
	else:
		result = games_config.set_slots_config(limit, cooldown)
		ctx.success("Configuración de slots actualizada")

	ctx.print(f"Limite: {result['limit']}")
	ctx.print(f"Cooldown: {result['cooldown']}s")
	ctx.print("Nota: esta configuración se comparte con Discord para mantener paridad")
	return True

