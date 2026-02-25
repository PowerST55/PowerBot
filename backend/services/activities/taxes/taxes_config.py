"""Configuración de impuestos (taxes) para economía global.

Se almacena en data/activities/taxes/taxes_config.json con el formato:

{
  "taxes": [
    {
      "id": "T1",
      "percent": 5.0,
      "interval_seconds": 3600,
      "target_type": "user" | "top",
      "target_user_id": 42,        # cuando target_type == "user"
      "target_top_rank": 1,        # cuando target_type == "top" (1, 2 o 3)
      "reason": "...",
      "created_at": "ISO",
      "last_run": 0.0
    }
  ]
}

Los helpers de este módulo son síncronos y agnósticos de Discord.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "activities" / "taxes"
CONFIG_FILE = DATA_DIR / "taxes_config.json"


@dataclass
class TaxConfig:
	id: str
	percent: float
	interval_seconds: int
	target_type: str  # "user" o "top"
	target_user_id: Optional[int] = None
	target_top_rank: Optional[int] = None
	reason: str | None = None
	created_at: str | None = None
	last_run: float = 0.0

	@classmethod
	def from_dict(cls, data: Dict[str, Any]) -> "TaxConfig":
		return cls(
			id=str(data.get("id")),
			percent=float(data.get("percent", 0.0) or 0.0),
			interval_seconds=int(data.get("interval_seconds", 0) or 0),
			target_type=str(data.get("target_type", "user")),
			target_user_id=(
				int(data.get("target_user_id"))
				if data.get("target_user_id") is not None
				else None
			),
			target_top_rank=(
				int(data.get("target_top_rank"))
				if data.get("target_top_rank") is not None
				else None
			),
			reason=str(data.get("reason") or "") or None,
			created_at=str(data.get("created_at") or "" ) or None,
			last_run=float(data.get("last_run", 0.0) or 0.0),
		)

	def to_dict(self) -> Dict[str, Any]:
		return asdict(self)


def _load_raw() -> Dict[str, Any]:
	if not CONFIG_FILE.exists():
		return {"taxes": []}
	try:
		with CONFIG_FILE.open("r", encoding="utf-8") as handle:
			data = json.load(handle)
		if not isinstance(data, dict):
			return {"taxes": []}
		data.setdefault("taxes", [])
		return data
	except (OSError, json.JSONDecodeError):
		return {"taxes": []}


def _save_raw(data: Dict[str, Any]) -> None:
	DATA_DIR.mkdir(parents=True, exist_ok=True)
	data.setdefault("taxes", [])
	with CONFIG_FILE.open("w", encoding="utf-8") as handle:
		json.dump(data, handle, indent=2, ensure_ascii=False)


def list_taxes() -> List[TaxConfig]:
	"""Devuelve la lista de impuestos configurados."""
	data = _load_raw()
	taxes_raw = data.get("taxes", []) or []
	return [TaxConfig.from_dict(entry) for entry in taxes_raw if isinstance(entry, dict)]


def _next_tax_id(existing: List[TaxConfig]) -> str:
	max_n = 0
	for tax in existing:
		if not tax.id:
			continue
		if tax.id.startswith("T") and tax.id[1:].isdigit():
			max_n = max(max_n, int(tax.id[1:]))
	return f"T{max_n + 1}"


def add_tax(
	percent: float,
	interval_seconds: int,
	target_type: str,
	target_user_id: Optional[int] = None,
	target_top_rank: Optional[int] = None,
	reason: str | None = None,
) -> TaxConfig:
	"""Crea y guarda un nuevo impuesto.

	Args:
		percent: Porcentaje a descontar (ej. 5.0 = 5%).
		interval_seconds: Intervalo de cobro en segundos.
		target_type: "user" o "top".
		target_user_id: ID global de usuario cuando target_type == "user".
		target_top_rank: 1, 2 o 3 cuando target_type == "top".
		reason: Texto descriptivo opcional.
	"""
	existing = list_taxes()
	new_id = _next_tax_id(existing)
	now = datetime.now(timezone.utc).isoformat()
	new_tax = TaxConfig(
		id=new_id,
		percent=float(percent),
		interval_seconds=int(interval_seconds),
		target_type=str(target_type),
		target_user_id=target_user_id,
		target_top_rank=target_top_rank,
		reason=reason,
		created_at=now,
		last_run=0.0,
	)
	data = _load_raw()
	taxes_raw = data.get("taxes", []) or []
	taxes_raw.append(new_tax.to_dict())
	data["taxes"] = taxes_raw
	_save_raw(data)
	return new_tax


def remove_tax(tax_id: str) -> bool:
	"""Elimina un impuesto por ID. Devuelve True si se eliminó algo."""
	data = _load_raw()
	taxes_raw = data.get("taxes", []) or []
	before = len(taxes_raw)
	taxes_raw = [entry for entry in taxes_raw if str(entry.get("id")) != str(tax_id)]
	data["taxes"] = taxes_raw
	if len(taxes_raw) != before:
		_save_raw(data)
		return True
	return False


def update_tax_last_run(tax_id: str, last_run_ts: float) -> None:
	"""Actualiza la marca de tiempo last_run de un impuesto."""
	data = _load_raw()
	taxes_raw = data.get("taxes", []) or []
	modified = False
	for entry in taxes_raw:
		if str(entry.get("id")) == str(tax_id):
			entry["last_run"] = float(last_run_ts)
			modified = True
			break
	if modified:
		data["taxes"] = taxes_raw
		_save_raw(data)

