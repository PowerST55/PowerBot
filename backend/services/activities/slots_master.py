"""
Logica reutilizable para tragamonedas.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List, Tuple


SLOT_PAYOUTS = {
	"🍒": {"x3": 2.5, "x2": 1.05, "prob": 0.35},
	"🍍": {"x3": 4.0, "x2": 1.1, "prob": 0.25},
	"🍎": {"x3": 6.0, "x2": 1.2, "prob": 0.15},
	"🍇": {"x3": 10.0, "x2": 1.4, "prob": 0.08},
	"🥭": {"x3": 20.0, "x2": 1.8, "prob": 0.04},
	"🔔": {"x3": 30.0, "x2": 2.2, "prob": 0.02},
	"💎": {"x3": 999.0, "x2": 99.0, "prob": 0.01},
}

SLOT_SYMBOLS = list(SLOT_PAYOUTS.keys())
SLOT_WEIGHTS = [SLOT_PAYOUTS[s]["prob"] for s in SLOT_SYMBOLS]

LUCK_FILE = Path(__file__).resolve().parents[2] / "data" / "activities" / "slot_luck.json"


def load_luck_multipliers() -> Dict[str, float]:
	try:
		with LUCK_FILE.open("r", encoding="utf-8") as handle:
			return json.load(handle)
	except (FileNotFoundError, json.JSONDecodeError):
		return {}


def save_luck_multipliers(luck_data: Dict[str, float]) -> None:
	LUCK_FILE.parent.mkdir(parents=True, exist_ok=True)
	with LUCK_FILE.open("w", encoding="utf-8") as handle:
		json.dump(luck_data, handle, indent=4, ensure_ascii=False)


def get_user_luck_multiplier(user_id: str) -> float:
	luck_data = load_luck_multipliers()
	return float(luck_data.get(str(user_id), 1.0))


def update_user_luck_multiplier(user_id: str, multiplier: float) -> None:
	luck_data = load_luck_multipliers()
	luck_data[str(user_id)] = round(max(1.0, multiplier), 2)
	save_luck_multipliers(luck_data)


def reset_user_luck_multiplier(user_id: str) -> None:
	update_user_luck_multiplier(user_id, 1.0)


def increment_user_luck_multiplier(user_id: str, increment: float = 0.1) -> None:
	current = get_user_luck_multiplier(user_id)
	update_user_luck_multiplier(user_id, current + increment)


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


def spin_slots(bet_amount: int, user_id: str) -> Tuple[List[str], int, float, str, bool, float]:
	luck_multiplier = get_user_luck_multiplier(user_id)

	result_type = random.choices(
		["loss", "x2", "x3"],
		weights=[0.70, 0.20, 0.10],
		k=1
	)[0]

	prob_sum = sum(SLOT_PAYOUTS[s]["prob"] for s in SLOT_SYMBOLS)
	relative_weights = [SLOT_PAYOUTS[s]["prob"] / prob_sum for s in SLOT_SYMBOLS]

	if result_type == "loss":
		combo = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
		while combo[0] == combo[1] or combo[1] == combo[2] or combo[0] == combo[2]:
			combo = [random.choice(SLOT_SYMBOLS) for _ in range(3)]

		ganancia_neta = -bet_amount
		return combo, ganancia_neta, 0.0, "Sin premio", False, luck_multiplier

	if result_type == "x2":
		symbol = random.choices(SLOT_SYMBOLS, weights=relative_weights, k=1)[0]
		combo = [symbol, symbol, random.choice(SLOT_SYMBOLS)]
		while combo[2] == symbol:
			combo[2] = random.choice(SLOT_SYMBOLS)
		random.shuffle(combo)

		multiplicador = SLOT_PAYOUTS[symbol]["x2"]
		payout = int(bet_amount * multiplicador * luck_multiplier)
		ganancia_neta = payout - bet_amount

		return combo, ganancia_neta, multiplicador, f"{symbol} X2", True, luck_multiplier

	symbol = random.choices(SLOT_SYMBOLS, weights=relative_weights, k=1)[0]
	combo = [symbol, symbol, symbol]

	multiplicador = SLOT_PAYOUTS[symbol]["x3"]
	payout = int(bet_amount * multiplicador * luck_multiplier)
	ganancia_neta = payout - bet_amount

	return combo, ganancia_neta, multiplicador, f"{symbol} X3", True, luck_multiplier


def get_slot_summary(
	username: str,
	bet_amount: int,
	combo: List[str],
	ganancia_neta: int,
	multiplicador: float,
	descripcion: str,
	es_ganancia: bool,
	luck_multiplier: float,
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
		"luck_multiplier": luck_multiplier,
		"payout_total": payout_total,
	}
