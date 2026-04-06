"""
Logica reutilizable para tragamonedas.
"""
from __future__ import annotations

import random
from typing import Dict, List, Tuple

from backend.services.activities import casino_master


SLOT_PAYOUTS = {
	"🍒": {"x3": 2.5, "x2": 1.05, "prob": 0.35},
	"🍍": {"x3": 4.0, "x2": 1.1, "prob": 0.25},
	"🍎": {"x3": 6.0, "x2": 1.2, "prob": 0.15},
	"🍇": {"x3": 10.0, "x2": 1.4, "prob": 0.10},
	"🥭": {"x3": 20.0, "x2": 1.8, "prob": 0.07},
	"🔔": {"x3": 30.0, "x2": 2.2, "prob": 0.04},
	"💎": {"x3": 100.0, "x2": 60.0, "prob": 0.03},
}

SLOT_SYMBOLS = list(SLOT_PAYOUTS.keys())


def validate_gamble(user_points: float, bet_amount: float, max_bet: float | None = None) -> Tuple[bool, str]:
	if bet_amount <= 0:
		return False, "❌ Debes apostar al menos 1 punto."

	if max_bet is not None and bet_amount > max_bet:
		return False, (
			f"❌ El limite maximo de apuesta es **{max_bet:,}**. "
			f"Intentaste apostar **{bet_amount:,}**."
		)

	if user_points < bet_amount:
		return False, (
			f"❌ No tienes suficientes puntos. Tienes: **{user_points:,}**."
		)

	return True, ""


def spin_slots(bet_amount: int, casino_fund_balance: float) -> Tuple[List[str], int, float, str, bool, str]:
	health_score = casino_master.get_casino_health_score(casino_fund_balance, bet_amount)
	casino_tier = casino_master.get_casino_tier(casino_fund_balance, bet_amount)

	result_type = random.choices(
		["loss", "x2", "x3"],
		weights=casino_master.normalize_weights([
			0.60 - (0.06 * health_score),
			0.26 + (0.03 * health_score),
			0.14 + (0.03 * health_score),
		]),
		k=1
	)[0]

	x2_symbol_weights = []
	x3_symbol_weights = []
	for symbol in SLOT_SYMBOLS:
		x2_net_win = round((bet_amount * SLOT_PAYOUTS[symbol]["x2"]) - bet_amount, 2)
		x3_net_win = round((bet_amount * SLOT_PAYOUTS[symbol]["x3"]) - bet_amount, 2)
		base_prob = float(SLOT_PAYOUTS[symbol]["prob"])
		x2_symbol_weights.append(
			base_prob * casino_master.get_positive_outcome_weight(x2_net_win, casino_fund_balance, bet_amount)
		)
		x3_symbol_weights.append(
			base_prob * casino_master.get_positive_outcome_weight(x3_net_win, casino_fund_balance, bet_amount)
		)

	if result_type == "loss":
		combo = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
		while combo[0] == combo[1] or combo[1] == combo[2] or combo[0] == combo[2]:
			combo = [random.choice(SLOT_SYMBOLS) for _ in range(3)]

		ganancia_neta = -bet_amount
		return combo, ganancia_neta, 0.0, "Sin premio", False, casino_tier

	if result_type == "x2":
		symbol = random.choices(SLOT_SYMBOLS, weights=casino_master.normalize_weights(x2_symbol_weights), k=1)[0]
		combo = [symbol, symbol, random.choice(SLOT_SYMBOLS)]
		while combo[2] == symbol:
			combo[2] = random.choice(SLOT_SYMBOLS)
		random.shuffle(combo)

		multiplicador = SLOT_PAYOUTS[symbol]["x2"]
		payout = int(round(bet_amount * multiplicador))
		ganancia_neta = payout - bet_amount

		return combo, ganancia_neta, multiplicador, f"{symbol} X2", True, casino_tier

	symbol = random.choices(SLOT_SYMBOLS, weights=casino_master.normalize_weights(x3_symbol_weights), k=1)[0]
	combo = [symbol, symbol, symbol]

	multiplicador = SLOT_PAYOUTS[symbol]["x3"]
	payout = int(round(bet_amount * multiplicador))
	ganancia_neta = payout - bet_amount

	return combo, ganancia_neta, multiplicador, f"{symbol} X3", True, casino_tier


def get_slot_summary(
	username: str,
	bet_amount: int,
	combo: List[str],
	ganancia_neta: int,
	multiplicador: float,
	descripcion: str,
	es_ganancia: bool,
	casino_tier: str,
	puntos_finales: int,
) -> Dict[str, object]:
	if not es_ganancia:
		tipo_resultado = "loss"
		resultado_emoji = "🎰"
		color = "rojo"
	elif "X2" in descripcion:
		tipo_resultado = "x2"
		resultado_emoji = "🎰"
		color = "amarillo"
	else:
		tipo_resultado = "x3"
		resultado_emoji = "🎰"
		color = "verde"

	if ganancia_neta > 0:
		ganancia_perdida_label = "Ganancia"
		ganancia_perdida_texto = f"+{ganancia_neta:,}"
	elif ganancia_neta == 0:
		ganancia_perdida_label = "Balance"
		ganancia_perdida_texto = "±0"
	else:
		ganancia_perdida_label = "Perdida"
		ganancia_perdida_texto = f"{ganancia_neta:,}"

	combo_display = " ".join(combo)
	payout_total = bet_amount + ganancia_neta

	return {
		"username": username,
		"bet_amount": bet_amount,
		"combo": combo,
		"combo_display": combo_display,
		"ganancia_neta": ganancia_neta,
		"ganancia_perdida_label": ganancia_perdida_label,
		"ganancia_perdida_texto": ganancia_perdida_texto,
		"multiplicador": multiplicador,
		"descripcion": descripcion,
		"es_ganancia": es_ganancia,
		"puntos_finales": puntos_finales,
		"resultado_emoji": resultado_emoji,
		"color": color,
		"tipo_resultado": tipo_resultado,
		"casino_tier": casino_tier,
		"payout_total": payout_total,
	}
