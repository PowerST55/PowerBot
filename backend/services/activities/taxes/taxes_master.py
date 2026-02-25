"""Lógica de cobro automático de impuestos (taxes).

Este módulo es agnóstico de Discord. Se encarga de:
- Leer la configuración de impuestos desde taxes_config.
- Calcular qué impuestos están vencidos según su intervalo.
- Determinar el usuario objetivo (usuario fijo o Top N global).
- Calcular el monto del impuesto sobre el balance global del usuario
  (todas las plataformas).
- Aplicar el descuento usando economy_manager.apply_balance_delta.

La notificación a economy_channel puede hacerse usando el resultado
devuelto por collect_due_taxes() desde el contexto de Discord.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.managers import economy_manager
from backend.services.activities.taxes import taxes_config


@dataclass
class TaxChargeResult:
	"""Resultado de un cobro de impuesto sobre un usuario."""
	tax_id: str
	user_id: int
	percent: float
	amount: float
	previous_balance: float
	new_balance: float
	reason: str | None
	target_type: str
	target_top_rank: int | None
	timestamp: float

	def to_dict(self) -> Dict[str, Any]:
		return {
			"tax_id": self.tax_id,
			"user_id": self.user_id,
			"percent": self.percent,
			"amount": self.amount,
			"previous_balance": self.previous_balance,
			"new_balance": self.new_balance,
			"reason": self.reason,
			"target_type": self.target_type,
			"target_top_rank": self.target_top_rank,
			"timestamp": self.timestamp,
		}


def _now_ts() -> float:
	return datetime.now(timezone.utc).timestamp()


def _get_top_user_id(rank: int) -> int | None:
	"""Devuelve el user_id global del Top N (1,2,3) o None si no existe."""
	from backend.managers.economy_manager import get_global_leaderboard

	if rank <= 0:
		return None

	rows = get_global_leaderboard(limit=rank)
	if not rows or len(rows) < rank:
		return None

	row = rows[rank - 1]
	try:
		return int(row.get("user_id"))
	except Exception:
		return None


def collect_due_taxes() -> List[TaxChargeResult]:
	"""Cobra todos los impuestos vencidos hasta ahora.

	Devuelve una lista de resultados por usuario/impuesto cobrado.
	El llamador (por ejemplo, un servicio de Discord) puede usar este
	resultado para notificar en economy_channel o en logs.
	"""
	now = _now_ts()
	results: List[TaxChargeResult] = []

	for tax in taxes_config.list_taxes():
		if tax.interval_seconds <= 0 or tax.percent <= 0:
			continue

		# ¿Está vencido este impuesto?
		if tax.last_run > 0 and (now - tax.last_run) < tax.interval_seconds:
			continue

		# Determinar usuario objetivo
		user_id: int | None = None
		if tax.target_type == "user" and tax.target_user_id is not None:
			user_id = int(tax.target_user_id)
		elif tax.target_type == "top" and tax.target_top_rank is not None:
			user_id = _get_top_user_id(int(tax.target_top_rank))

		if not user_id:
			# No hay usuario válido para este impuesto en este momento
			# (por ejemplo, no hay Top 3 completo)
			# Actualizamos last_run para no saturar en cada llamada.
			taxes_config.update_tax_last_run(tax.id, now)
			continue

		# Obtener balance global actual
		previous_balance = float(economy_manager.get_total_balance(user_id))
		if previous_balance <= 0:
			# Nada que cobrar
			taxes_config.update_tax_last_run(tax.id, now)
			continue

		amount = round(previous_balance * (tax.percent / 100.0), 2)
		if amount <= 0:
			taxes_config.update_tax_last_run(tax.id, now)
			continue

		# Aplicar descuento (delta negativo). Usamos plataforma "system"
		# para indicar que no viene de Discord/YT directamente.
		new_balance = float(
			economy_manager.apply_balance_delta(
				user_id=user_id,
				delta=-amount,
				reason="tax",
				platform="system",
				guild_id=None,
				channel_id=None,
				source_id=f"tax:{tax.id}:{int(now)}",
			)
		)

		result = TaxChargeResult(
			tax_id=tax.id,
			user_id=user_id,
			percent=tax.percent,
			amount=amount,
			previous_balance=previous_balance,
			new_balance=new_balance,
			reason=tax.reason,
			target_type=tax.target_type,
			target_top_rank=tax.target_top_rank,
			timestamp=now,
		)
		results.append(result)

		# Marcar como ejecutado
		taxes_config.update_tax_last_run(tax.id, now)

	return results

