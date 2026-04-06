"""
Comandos de consola para gestionar la economia centralizada.
"""

from __future__ import annotations

from typing import Any

from backend.managers import economy_manager


def _format_amount(value: float) -> str:
	return f"{float(value):,.2f}"


def _print_overview(ctx: Any, title: str = "Estado de la economia") -> None:
	overview = economy_manager.get_economy_overview()
	ctx.print(f"{title}:")
	ctx.print(f"  • Fondo comun: {_format_amount(overview['common_fund'])} pews")
	ctx.print(f"  • Fondo casino: {_format_amount(overview['casino_fund'])} pews")
	ctx.print(f"  • Fondo mina: {_format_amount(overview['mine_fund'])} pews")
	ctx.print(f"  • En circulacion: {_format_amount(overview['circulating_supply'])} pews")
	ctx.print(f"  • Oferta total: {_format_amount(overview['total_supply'])} pews")


def _parse_amount(raw: str) -> float:
	try:
		value = round(float(str(raw).replace(",", ".")), 2)
	except Exception as exc:
		raise ValueError("La cantidad debe ser numerica") from exc
	if value < 0:
		raise ValueError("La cantidad no puede ser negativa")
	return value


async def cmd_economy(ctx: Any) -> None:
	"""
	Gestiona economia centralizada y fondo comun.

	Uso:
	  economy status
	  economy fondo_comun
	  economy fondo_comun aps <monto>
	  economy fondo_comun rps <monto>
	  economy circulacion
	  economy oferta
	"""
	action = ctx.args[0].strip().lower() if ctx.args else "status"

	if action in {"help", "-h", "--help"}:
		ctx.print("Comandos economy disponibles:")
		ctx.print("  economy status                - Resumen de fondo comun y oferta")
		ctx.print("  economy fondo_comun          - Ver saldo actual del fondo comun")
		ctx.print("  economy fondo_comun aps 500  - Agrega 500 pews al fondo comun")
		ctx.print("  economy fondo_comun rps 1000 - Remueve 1000 pews del fondo comun")
		ctx.print("  economy fondo_comun taxeveryone 10 - Cobra hasta 10 pews a cada usuario y lo envia al fondo comun")
		ctx.print("  economy fondo_casino         - Ver saldo actual del fondo casino")
		ctx.print("  economy fondo_casino aps 500 - Agrega 500 pews al fondo casino")
		ctx.print("  economy fondo_casino rps 500 - Remueve 500 pews del fondo casino")
		ctx.print("  economy fondo_mina           - Ver saldo actual del fondo mina")
		ctx.print("  economy fondo_mina aps 500   - Agrega 500 pews al fondo mina")
		ctx.print("  economy fondo_mina rps 500   - Remueve 500 pews del fondo mina")
		ctx.print("  economy circulacion          - Ver pews en circulacion")
		ctx.print("  economy oferta               - Ver oferta monetaria total")
		return

	if action in {"status", "resumen", "overview"}:
		_print_overview(ctx)
		return

	if action in {"circulacion", "circulation"}:
		circulating = economy_manager.get_circulating_supply()
		ctx.print(f"Pews en circulacion: {_format_amount(circulating)}")
		return

	if action in {"oferta", "supply", "total_supply"}:
		total_supply = economy_manager.get_total_supply()
		ctx.print(f"Oferta total actual: {_format_amount(total_supply)} pews")
		return

	if action in {"fondo_comun", "fondo", "common_fund"}:
		if len(ctx.args) == 1:
			common_fund = economy_manager.get_common_fund_balance()
			ctx.print(f"Saldo del fondo comun: {_format_amount(common_fund)} pews")
			return

		if len(ctx.args) < 3:
			ctx.error("Uso: economy fondo_comun <aps|rps> <cantidad>")
			return

		operation = str(ctx.args[1]).strip().lower()
		try:
			amount = _parse_amount(ctx.args[2])
		except ValueError as exc:
			ctx.error(str(exc))
			return

		if amount <= 0:
			ctx.error("La cantidad debe ser mayor a 0")
			return

		if operation == "aps":
			result = economy_manager.adjust_common_fund(
				delta=amount,
				reason="console_common_fund_add",
			)
			ctx.success(f"Se agregaron {_format_amount(amount)} pews al fondo comun")
			ctx.print(f"Nuevo saldo del fondo comun: {_format_amount(result['common_fund'])} pews")
			ctx.print(f"Nueva oferta total: {_format_amount(result['total_supply'])} pews")
			return

		if operation == "rps":
			try:
				result = economy_manager.adjust_common_fund(
					delta=-amount,
					reason="console_common_fund_remove",
				)
			except ValueError as exc:
				ctx.error(str(exc))
				return
			ctx.success(f"Se removieron {_format_amount(amount)} pews del fondo comun")
			ctx.print(f"Nuevo saldo del fondo comun: {_format_amount(result['common_fund'])} pews")
			ctx.print(f"Nueva oferta total: {_format_amount(result['total_supply'])} pews")
			return

		if operation in {"taxeveryone", "tax_all", "taxall"}:
			try:
				result = economy_manager.tax_everyone_to_common_fund(
					amount_per_user=amount,
					reason="console_emergency_tax_everyone",
				)
			except ValueError as exc:
				ctx.error(str(exc))
				return

			ctx.success(
				f"Impuesto global aplicado: hasta {_format_amount(float(result['amount_per_user']))} pews por usuario"
			)
			ctx.print(f"Usuarios evaluados: {int(result['users_scanned'])}")
			ctx.print(f"Usuarios gravados: {int(result['taxed_users'])}")
			ctx.print(f"Total recaudado: {_format_amount(float(result['total_collected']))} pews")
			ctx.print(f"Nuevo saldo del fondo comun: {_format_amount(float(result['common_fund']))} pews")
			ctx.print(f"Pews en circulacion: {_format_amount(float(result['circulating_supply']))}")
			ctx.print(f"Oferta total: {_format_amount(float(result['total_supply']))} pews")
			return

		ctx.error("Operacion desconocida. Usa aps para agregar, rps para remover o taxeveryone para impuesto global")
		return

	if action in {"fondo_casino", "casino", "casino_fund"}:
		if len(ctx.args) == 1:
			casino_fund = economy_manager.get_casino_fund_balance()
			ctx.print(f"Saldo del fondo casino: {_format_amount(casino_fund)} pews")
			return

		if len(ctx.args) < 3:
			ctx.error("Uso: economy fondo_casino <aps|rps> <cantidad>")
			return

		operation = str(ctx.args[1]).strip().lower()
		try:
			amount = _parse_amount(ctx.args[2])
		except ValueError as exc:
			ctx.error(str(exc))
			return

		if amount <= 0:
			ctx.error("La cantidad debe ser mayor a 0")
			return

		if operation == "aps":
			result = economy_manager.adjust_casino_fund(
				delta=amount,
				reason="console_casino_fund_add",
			)
			ctx.success(f"Se agregaron {_format_amount(amount)} pews al fondo casino")
			ctx.print(f"Nuevo saldo del fondo casino: {_format_amount(result['casino_fund'])} pews")
			ctx.print(f"Nueva oferta total: {_format_amount(result['total_supply'])} pews")
			return

		if operation == "rps":
			try:
				result = economy_manager.adjust_casino_fund(
					delta=-amount,
					reason="console_casino_fund_remove",
				)
			except ValueError as exc:
				ctx.error(str(exc))
				return
			ctx.success(f"Se removieron {_format_amount(amount)} pews del fondo casino")
			ctx.print(f"Nuevo saldo del fondo casino: {_format_amount(result['casino_fund'])} pews")
			ctx.print(f"Nueva oferta total: {_format_amount(result['total_supply'])} pews")
			return

		ctx.error("Operacion desconocida. Usa aps para agregar o rps para remover")
		return

	if action in {"fondo_mina", "mina", "mine_fund"}:
		if len(ctx.args) == 1:
			mine_fund = economy_manager.get_mine_fund_balance()
			ctx.print(f"Saldo del fondo mina: {_format_amount(mine_fund)} pews")
			return

		if len(ctx.args) < 3:
			ctx.error("Uso: economy fondo_mina <aps|rps> <cantidad>")
			return

		operation = str(ctx.args[1]).strip().lower()
		try:
			amount = _parse_amount(ctx.args[2])
		except ValueError as exc:
			ctx.error(str(exc))
			return

		if amount <= 0:
			ctx.error("La cantidad debe ser mayor a 0")
			return

		if operation == "aps":
			result = economy_manager.adjust_mine_fund(
				delta=amount,
				reason="console_mine_fund_add",
			)
			ctx.success(f"Se agregaron {_format_amount(amount)} pews al fondo mina")
			ctx.print(f"Nuevo saldo del fondo mina: {_format_amount(result['mine_fund'])} pews")
			ctx.print(f"Nueva oferta total: {_format_amount(result['total_supply'])} pews")
			return

		if operation == "rps":
			try:
				result = economy_manager.adjust_mine_fund(
					delta=-amount,
					reason="console_mine_fund_remove",
				)
			except ValueError as exc:
				ctx.error(str(exc))
				return
			ctx.success(f"Se removieron {_format_amount(amount)} pews del fondo mina")
			ctx.print(f"Nuevo saldo del fondo mina: {_format_amount(result['mine_fund'])} pews")
			ctx.print(f"Nueva oferta total: {_format_amount(result['total_supply'])} pews")
			return

		ctx.error("Operacion desconocida. Usa aps para agregar o rps para remover")
		return

	ctx.error(f"Subcomando desconocido: 'economy {action}'")
	ctx.print("Usa 'economy help' para ver comandos disponibles")
