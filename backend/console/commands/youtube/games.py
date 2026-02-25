"""
Helpers de configuración de juegos YouTube desde consola.
"""

from __future__ import annotations

from backend.services.activities import games_config


def apply_youtube_game_settings(ctx, game_name: str, args: list[str]) -> bool:
	"""
	Aplica configuración de juego (gamble/slots) para YouTube.

	Uso:
	  yt set gamble <limite_inferior> <limite_superior> <cooldown_segundos>
	  yt set slots <limite_inferior> <limite_superior> <cooldown_segundos>
	"""
	if len(args) != 3:
		ctx.error(f"Uso: yt set {game_name} <limite_inferior> <limite_superior> <cooldown_segundos>")
		return False

	min_raw, max_raw, cooldown_raw = (
		args[0].strip(),
		args[1].strip(),
		args[2].strip(),
	)

	try:
		min_limit = float(min_raw)
	except ValueError:
		ctx.error("El limite inferior debe ser un numero (ej: 0, 150 o 150.5)")
		return False

	try:
		max_limit = float(max_raw)
	except ValueError:
		ctx.error("El limite superior debe ser un numero (ej: 0, 150 o 150.5)")
		return False

	try:
		cooldown = int(cooldown_raw)
	except ValueError:
		ctx.error("El cooldown debe ser un numero entero en segundos (ej: 300)")
		return False

	if min_limit < 0 or max_limit < 0 or cooldown < 0:
		ctx.error("Limites y cooldown deben ser >= 0")
		return False

	if max_limit > 0 and min_limit > max_limit:
		ctx.error("El limite inferior no puede ser mayor que el limite superior")
		return False

	if game_name == "gamble":
		result = games_config.set_gamble_config(min_limit, max_limit, cooldown)
		ctx.success("Configuración de gamble actualizada")
	else:
		result = games_config.set_slots_config(min_limit, max_limit, cooldown)
		ctx.success("Configuración de slots actualizada")

	ctx.print(f"Limite inferior: {result['min_limit']}")
	ctx.print(f"Limite superior: {result['max_limit']}")
	ctx.print(f"Cooldown: {result['cooldown']}s")
	ctx.print("Nota: esta configuración se comparte con Discord para mantener paridad")
	return True

