"""
Logica reutilizable para gamble.
"""
from __future__ import annotations

from decimal import Decimal
import random
from typing import Dict, Tuple

from backend.services.activities import casino_master


GAMBLE_OUTCOMES = [
	{"min_roll": 1, "max_roll": 25, "multiplier": 0.0, "label": "0-25: Perdiste todo", "base_weight": 25.0},
	{"min_roll": 26, "max_roll": 40, "multiplier": 0.5, "label": "26-40: Recuperaste el 50%", "base_weight": 15.0},
	{"min_roll": 41, "max_roll": 55, "multiplier": 1.0, "label": "41-55: Reembolso completo", "base_weight": 15.0},
	{"min_roll": 56, "max_roll": 70, "multiplier": 1.3, "label": "56-70: Ganaste 30% extra", "base_weight": 15.0},
	{"min_roll": 71, "max_roll": 85, "multiplier": 1.6, "label": "71-85: Ganaste 60% extra", "base_weight": 15.0},
	{"min_roll": 86, "max_roll": 95, "multiplier": 2.0, "label": "86-95: Duplicaste tu apuesta", "base_weight": 10.0},
	{"min_roll": 96, "max_roll": 99, "multiplier": 2.5, "label": "96-99: Premio grande", "base_weight": 4.0},
	{"min_roll": 100, "max_roll": 100, "multiplier": 4.0, "label": "100: Jackpot", "base_weight": 1.0},
]


def calculate_gamble_result(bet_amount: float, casino_fund_balance: float) -> Tuple[int, float, float, str]:
	"""
	Calcula el resultado del gamble según la liquidez actual del casino.

	Returns:
		Tuple[roll, ganancia_neta, multiplicador, rango]
	"""
	bet_amount = round(float(bet_amount), 2)
	casino_fund_balance = round(float(casino_fund_balance), 2)
	health_score = casino_master.get_casino_health_score(casino_fund_balance, bet_amount)

	dynamic_weights = []
	for outcome in GAMBLE_OUTCOMES:
		base_weight = float(outcome["base_weight"])
		multiplier = float(outcome["multiplier"])
		net_win = round((bet_amount * multiplier) - bet_amount, 2)
		if net_win > 0:
			weight_factor = casino_master.get_positive_outcome_weight(net_win, casino_fund_balance, bet_amount)
		elif net_win == 0:
			weight_factor = 0.95 + (0.20 * health_score)
		else:
			weight_factor = 1.10 - (0.10 * health_score)
		dynamic_weights.append(base_weight * weight_factor)

	normalized_weights = casino_master.normalize_weights(dynamic_weights)
	selected = random.choices(GAMBLE_OUTCOMES, weights=normalized_weights, k=1)[0]
	roll = random.randint(int(selected["min_roll"]), int(selected["max_roll"]))
	multiplicador = float(selected["multiplier"])
	rango = str(selected["label"])

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
