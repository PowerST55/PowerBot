"""
Logica reutilizable para gamble.
"""
from __future__ import annotations

from decimal import Decimal
import random
from typing import Dict, Tuple


def calculate_gamble_result(bet_amount: float) -> Tuple[int, float, float, str]:
	"""
	Calcula el resultado del gamble usando las mismas probabilidades del sistema anterior.

	Returns:
		Tuple[roll, ganancia_neta, multiplicador, rango]
	"""
	roll = random.randint(1, 100)

	if roll <= 25:
		multiplicador = 0.0
		rango = "0-25: Perdiste todo"
	elif roll <= 40:
		multiplicador = 0.5
		rango = "26-40: Recuperaste el 50%"
	elif roll <= 55:
		multiplicador = 1.0
		rango = "41-55: Reembolso completo"
	elif roll <= 70:
		multiplicador = 1.3
		rango = "56-70: Ganaste 30% extra"
	elif roll <= 85:
		multiplicador = 1.6
		rango = "71-85: Ganaste 60% extra"
	elif roll <= 95:
		multiplicador = 2.0
		rango = "86-95: Duplicaste tu apuesta"
	elif roll <= 99:
		multiplicador = 2.5
		rango = "96-99: Premio grande"
	else:
		multiplicador = 4.0
		rango = "100: Jackpot"

	payout_total = round(bet_amount * multiplicador, 2)
	ganancia_neta = round(payout_total - bet_amount, 2)

	return roll, ganancia_neta, multiplicador, rango


def validate_gamble(user_points: float, bet_amount: float, max_bet: float | None = None) -> Tuple[bool, str]:
	"""
	Valida si un usuario puede apostar.
	"""
	if bet_amount <= 0:
		return False, "Debes apostar al menos 1 punto."

	if max_bet is not None and bet_amount > max_bet:
		return False, (
			f"El limite maximo de apuesta es {max_bet:,.2f}. "
			f"Intentaste apostar {bet_amount:,.2f}."
		)

	if user_points < bet_amount:
		return False, (
			f"No tienes suficientes puntos. Tienes: {user_points:,.2f}."
		)

	return True, ""


def get_gamble_summary(
	username: str,
	bet_amount: float,
	roll: int,
	ganancia_neta: float,
	multiplicador: float,
	rango: str,
	puntos_finales: float
) -> Dict[str, object]:
	"""Genera un resumen del resultado del gamble."""
	if ganancia_neta > 0:
		resultado_emoji = "✅"
		color = "verde"
	elif ganancia_neta == 0:
		resultado_emoji = "🔄"
		color = "amarillo"
	else:
		resultado_emoji = "❌"
		color = "rojo"

	if ganancia_neta > 0:
		ganancia_texto = f"+{ganancia_neta:,.2f}"
	elif ganancia_neta == 0:
		ganancia_texto = "±0"
	else:
		ganancia_texto = f"{ganancia_neta:,.2f}"

	return {
		"username": username,
		"bet_amount": float(Decimal(str(bet_amount)).quantize(Decimal("0.01"))),
		"roll": roll,
		"ganancia_neta": ganancia_neta,
		"ganancia_texto": ganancia_texto,
		"multiplicador": multiplicador,
		"rango": rango,
		"puntos_finales": puntos_finales,
		"resultado_emoji": resultado_emoji,
		"color": color,
	}
