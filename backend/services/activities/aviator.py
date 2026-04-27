"""Logica reusable para Aviator basada en liquidez del casino."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import random
from typing import Dict, Tuple

from backend.services.activities import casino_master


AVIATOR_STEP = Decimal("0.1")
AVIATOR_START = Decimal("1.0")
AVIATOR_MIN_REACH = Decimal("1.1")
AVIATOR_MAX_REACH = Decimal("15.0")


def _quantize_multiplier(value: float | Decimal) -> float:
	return float(Decimal(str(value)).quantize(AVIATOR_STEP, rounding=ROUND_HALF_UP))


def _multiplier_points() -> list[float]:
	points: list[float] = []
	current = AVIATOR_MIN_REACH
	while current <= AVIATOR_MAX_REACH:
		points.append(_quantize_multiplier(current))
		current += AVIATOR_STEP
	return points


AVIATOR_REACH_POINTS = _multiplier_points()


def validate_aviator(user_points: float, bet_amount: float, max_bet: float | None = None) -> Tuple[bool, str]:
	if bet_amount <= 0:
		return False, "❌ Debes apostar al menos 1 punto."

	if max_bet is not None and bet_amount > max_bet:
		return False, (
			f"❌ El limite maximo de apuesta es **{max_bet:,.2f}**. "
			f"Intentaste apostar **{bet_amount:,.2f}**."
		)

	if user_points < bet_amount:
		return False, f"❌ No tienes suficientes puntos. Tienes: **{user_points:,.2f}**."

	return True, ""


def generate_reach_multiplier(bet_amount: float, casino_fund_balance: float) -> float:
	"""Genera el multiplicador maximo alcanzable del vuelo.

	La distribución favorece explosiones tempranas y usa la liquidez del casino
	para recortar multiplicadores altos. Apuestas pequeñas reciben un empujón
	leve entre x2 y x3, pero sin volverlo dominante.
	"""
	bet_amount = round(float(bet_amount), 2)
	casino_fund_balance = round(float(casino_fund_balance), 2)
	health_score = casino_master.get_casino_health_score(casino_fund_balance, bet_amount)
	liquidity_pressure = 1.0 - health_score
	bet_pressure = min(1.0, bet_amount / max(50.0, casino_fund_balance * 0.04, 1.0))
	small_bet_bonus = max(0.0, (1.0 - bet_pressure) * (0.04 + (0.06 * health_score)))

	weights: list[float] = []
	for index, reach_multiplier in enumerate(AVIATOR_REACH_POINTS, start=1):
		base_weight = 1.0 / (index ** 1.18)

		if reach_multiplier <= 1.3:
			base_weight *= 1.22 + (0.22 * liquidity_pressure)
		elif reach_multiplier <= 1.8:
			base_weight *= 1.08 + (0.10 * liquidity_pressure)

		if 2.0 <= reach_multiplier <= 2.8:
			base_weight *= 1.0 + small_bet_bonus
		elif 2.8 < reach_multiplier <= 4.0:
			base_weight *= 0.28 + (0.08 * health_score)
		elif 4.0 < reach_multiplier <= 5.5:
			base_weight *= 0.12 + (0.05 * health_score)
		elif 5.0 < reach_multiplier <= 8.0:
			base_weight *= 0.05 + (0.02 * health_score)
		elif 8.0 < reach_multiplier <= 12.0:
			base_weight *= 0.015 + (0.008 * health_score)
		elif reach_multiplier > 12.0:
			base_weight *= 0.0035 + (0.0025 * health_score)

		net_win = round(bet_amount * (reach_multiplier - 1.0), 2)
		weight_factor = casino_master.get_positive_outcome_weight(
			net_win=net_win,
			casino_fund_balance=casino_fund_balance,
			bet_amount=bet_amount,
		)

		weight = base_weight * weight_factor * (0.94 + (0.14 * health_score))
		if health_score < 0.35 and reach_multiplier >= 2.0:
			weight *= 0.78
		if health_score < 0.20 and reach_multiplier >= 1.6:
			weight *= 0.72
		if reach_multiplier >= 3.0:
			weight *= 0.58 + (0.14 * health_score)
		if reach_multiplier >= 10.0:
			weight *= 0.10 + (0.18 * health_score)

		weights.append(weight)

	selected = random.choices(
		AVIATOR_REACH_POINTS,
		weights=casino_master.normalize_weights(weights),
		k=1,
	)[0]
	return _quantize_multiplier(selected)


def get_next_multiplier(current_multiplier: float) -> float:
	next_multiplier = Decimal(str(current_multiplier)) + AVIATOR_STEP
	if next_multiplier > AVIATOR_MAX_REACH:
		return _quantize_multiplier(AVIATOR_MAX_REACH)
	return _quantize_multiplier(next_multiplier)


def can_advance(current_multiplier: float) -> bool:
	return Decimal(str(current_multiplier)) < AVIATOR_MAX_REACH


def will_crash_on_advance(next_multiplier: float, reach_multiplier: float) -> bool:
	return round(float(next_multiplier), 1) > round(float(reach_multiplier), 1)


def calculate_cashout_delta(bet_amount: float, cashout_multiplier: float) -> float:
	payout_total = round(float(bet_amount) * float(cashout_multiplier), 2)
	return round(payout_total - float(bet_amount), 2)


def get_runway_text(current_multiplier: float, state: str) -> str:
	steps = min(10, max(0, int(round((float(current_multiplier) - 1.0) * 2))))
	sky_slots = max(1, 10 - steps)
	if state == "crashed":
		plane = "💥"
	elif state == "cashed":
		plane = "🪂"
	else:
		plane = "✈️"
	return f"🌲🌲⬜{plane}{'☁️' * sky_slots}"


def get_aviator_summary(
	username: str,
	bet_amount: float,
	current_multiplier: float,
	reach_multiplier: float,
	state: str,
	delta: float,
	final_balance: float | None = None,
) -> Dict[str, object]:
	if state == "cashed":
		headline = "Retirada confirmada"
		status = "success"
		color = "verde"
	elif state == "crashed":
		headline = "El avión se fue"
		status = "danger"
		color = "rojo"
	else:
		headline = "Vuelo en curso"
		status = "active"
		color = "azul"

	if delta > 0:
		delta_text = f"+{delta:,.2f}"
	elif delta < 0:
		delta_text = f"{delta:,.2f}"
	else:
		delta_text = "±0"

	return {
		"username": username,
		"bet_amount": round(float(bet_amount), 2),
		"current_multiplier": _quantize_multiplier(current_multiplier),
		"reach_multiplier": _quantize_multiplier(reach_multiplier),
		"state": state,
		"headline": headline,
		"status": status,
		"color": color,
		"delta": round(float(delta), 2),
		"delta_text": delta_text,
		"final_balance": None if final_balance is None else round(float(final_balance), 2),
		"runway_text": get_runway_text(current_multiplier, state),
	}
