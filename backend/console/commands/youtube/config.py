"""
Comandos de configuración de YouTube para la consola interactiva.
"""

from .games import apply_youtube_game_settings
from backend.services.youtube_api.config.economy import get_youtube_economy_config


async def cmd_youtube_set(ctx) -> None:
	"""
	Configura parámetros de YouTube.

	Uso:
	  yt set currency <nombre> <simbolo>
	  yt set points <amount> <interval_segundos>
	  yt set gamble <limite> <cooldown_segundos>
	  yt set slots <limite> <cooldown_segundos>
	  /set currency <nombre> <simbolo>
	"""
	if not ctx.args:
		ctx.error(
			"Uso: yt set currency <nombre> <simbolo> | yt set points <amount> <interval_segundos> | "
			"yt set gamble <limite> <cooldown_segundos> | yt set slots <limite> <cooldown_segundos>"
		)
		return

	section = ctx.args[0].lower()
	economy_config = get_youtube_economy_config()

	if section == "currency":
		if len(ctx.args) < 3:
			ctx.error("Faltan argumentos")
			ctx.print("Uso: yt set currency <nombre> <simbolo>")
			return

		currency_parts = ctx.args[1:]
		symbol = currency_parts[-1].strip()
		name = " ".join(currency_parts[:-1]).strip()

		if not name:
			ctx.error("El nombre de la moneda no puede estar vacío")
			return

		if not symbol:
			ctx.error("El símbolo de la moneda no puede estar vacío")
			return

		economy_config.set_currency(name=name, symbol=symbol)

		ctx.success("Moneda de YouTube actualizada")
		ctx.print(f"Nombre: {economy_config.get_currency_name()}")
		ctx.print(f"Símbolo: {economy_config.get_currency_symbol()}")
		return

	if section == "points":
		if len(ctx.args) != 3:
			ctx.error("Uso: yt set points <amount> <interval_segundos>")
			return

		amount_raw = ctx.args[1].strip()
		interval_raw = ctx.args[2].strip()

		try:
			amount = int(amount_raw)
			interval = int(interval_raw)
		except ValueError:
			ctx.error("amount e interval deben ser números enteros")
			return

		if amount <= 0:
			ctx.error("amount debe ser mayor a 0")
			return

		if interval <= 0:
			ctx.error("interval debe ser mayor a 0 segundos")
			return

		economy_config.set_points(amount=amount, interval=interval)

		ctx.success("Puntos de YouTube actualizados")
		ctx.print(f"Cantidad: {economy_config.get_points_amount()}")
		ctx.print(f"Intervalo: {economy_config.get_points_interval()} segundos")
		return

	if section in {"gamble", "slots"}:
		if apply_youtube_game_settings(ctx, section, ctx.args[1:]):
			return

	ctx.error(f"Configuración desconocida: '{section}'")
	ctx.print("Uso disponible: yt set currency <nombre> <simbolo>")
	ctx.print("Uso disponible: yt set points <amount> <interval_segundos>")
	ctx.print("Uso disponible: yt set gamble <limite> <cooldown_segundos>")
	ctx.print("Uso disponible: yt set slots <limite> <cooldown_segundos>")


async def cmd_youtube_earning(ctx) -> None:
	"""
	Activa/desactiva la ganancia de puntos por escribir en chat de YouTube.

	Uso:
	  yt earning true
	  yt earning false
	"""
	economy_config = get_youtube_economy_config()

	if not ctx.args:
		status = "activado" if economy_config.is_earning_enabled() else "desactivado"
		ctx.print(f"Earning actual: {status}")
		ctx.print("Uso: yt earning <true|false>")
		return

	value = ctx.args[0].strip().lower()
	if value not in {"true", "false"}:
		ctx.error("Valor inválido. Usa: yt earning <true|false>")
		return

	new_enabled = value == "true"

	if new_enabled:
		from .general import _get_listener
		listener = _get_listener()
		if not listener or not listener.is_running:
			ctx.error("No puedes activar earning sin yapi activo")
			ctx.print("Primero ejecuta 'yapi' (o 'yt listener') y luego vuelve a activar earning")
			return

	economy_config.set_earning_enabled(new_enabled)

	if new_enabled:
		ctx.success("Earning de YouTube activado")
		ctx.print("Los usuarios ganarán puntos al escribir según points.amount/points.interval")
	else:
		ctx.success("Earning de YouTube desactivado")
		ctx.print("Ya no se otorgarán puntos por mensajes en YouTube")


YOUTUBE_CONFIG_COMMANDS = {
	"set": cmd_youtube_set,
	"earning": cmd_youtube_earning,
}

