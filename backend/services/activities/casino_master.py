"""Utilidades compartidas para juegos del casino basados en liquidez."""
from __future__ import annotations

from typing import Iterable


SAFE_PAYOUT_RATIO = 0.90
RARE_PAYOUT_RATIO = 1.10
HEALTH_REFERENCE_MULTIPLIER = 20.0


def _safe_float(value: float | int) -> float:
	return round(float(value), 2)


def get_casino_health_score(casino_fund_balance: float, bet_amount: float) -> float:
	"""Devuelve un score entre 0 y 1 según la cobertura del fondo frente a la apuesta."""
	casino_fund_balance = max(0.0, _safe_float(casino_fund_balance))
	bet_amount = max(0.01, _safe_float(bet_amount))
	reference_balance = bet_amount * HEALTH_REFERENCE_MULTIPLIER
	return max(0.0, min(1.0, casino_fund_balance / reference_balance))


def get_safe_net_win_limit(casino_fund_balance: float) -> float:
	return max(0.0, _safe_float(casino_fund_balance) * SAFE_PAYOUT_RATIO)


def get_rare_net_win_limit(casino_fund_balance: float) -> float:
	return max(0.0, _safe_float(casino_fund_balance) * RARE_PAYOUT_RATIO)


def get_positive_outcome_weight(net_win: float, casino_fund_balance: float, bet_amount: float) -> float:
	"""Escala una probabilidad positiva según la liquidez del casino.

	- Hasta 90% del fondo: normal, con mejor probabilidad al subir liquidez.
	- Entre 90% y 110%: evento raro pero posible.
	- Más allá de 110%: desactivado.
	"""
	net_win = _safe_float(net_win)
	if net_win <= 0:
		return 1.0

	health_score = get_casino_health_score(casino_fund_balance, bet_amount)
	safe_limit = get_safe_net_win_limit(casino_fund_balance)
	rare_limit = get_rare_net_win_limit(casino_fund_balance)

	if safe_limit <= 0:
		return 0.0

	if net_win <= safe_limit:
		return 0.95 + (1.10 * health_score)

	if net_win <= rare_limit:
		overshoot_span = max(0.01, rare_limit - safe_limit)
		overshoot_ratio = min(1.0, max(0.0, (net_win - safe_limit) / overshoot_span))
		return max(0.08, (0.34 + (0.16 * health_score)) * (1.0 - (0.32 * overshoot_ratio)))

	return 0.0


def normalize_weights(weights: Iterable[float]) -> list[float]:
	normalized = [max(0.0, float(weight)) for weight in weights]
	total = sum(normalized)
	if total <= 0:
		return [1.0 for _ in normalized]
	return normalized


def get_casino_tier(casino_fund_balance: float, bet_amount: float) -> str:
	health = get_casino_health_score(casino_fund_balance, bet_amount)
	if health >= 0.75:
		return "Liquidez alta"
	if health >= 0.35:
		return "Liquidez media"
	if health > 0:
		return "Liquidez baja"
	return "Sin liquidez"