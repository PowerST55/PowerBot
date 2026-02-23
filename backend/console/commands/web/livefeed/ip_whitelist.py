"""
Comandos de whitelist para livefeed.
"""

from __future__ import annotations

from typing import Any

from backend.services.web.config.ip_livefeed import create_livefeed_ip_manager


async def cmd_livefeed(ctx: Any) -> None:
	"""
	Gestiona solicitudes pendientes de livefeed por IP.

	Uso:
	  livefeed status
	  livefeed allow
	  livefeed deny
	  livefeed list
	"""
	manager = create_livefeed_ip_manager()
	action = str(ctx.args[0]).lower() if ctx.args else "status"

	if action in {"help", "-h", "--help"}:
		ctx.print("Comandos livefeed:")
		ctx.print("  livefeed status - Ver última solicitud pendiente")
		ctx.print("  livefeed allow  - Autoriza la última solicitud (agrega IP a whitelist)")
		ctx.print("  livefeed deny   - Rechaza la última solicitud")
		ctx.print("  livefeed list   - Lista IPs autorizadas")
		return

	if action == "status":
		status = manager.get_status()
		pending = status.get("last_pending")
		ctx.print("Livefeed whitelist:")
		ctx.print(f"  • IPs autorizadas: {status.get('allowed_count', 0)}")
		if pending:
			ctx.warning(
				f"Solicitud pendiente: IP={pending.get('ip')} path={pending.get('path')} "
				f"at={pending.get('requested_at')}"
			)
		else:
			ctx.print("  • No hay solicitudes pendientes")
		ctx.print(f"  • Config: {status.get('config_file')}")
		return

	if action == "list":
		status = manager.get_status()
		allowed_ips = status.get("allowed_ips", [])
		if not allowed_ips:
			ctx.print("No hay IPs autorizadas en whitelist")
			return
		ctx.print("IPs autorizadas:")
		for ip in allowed_ips:
			ctx.print(f"  • {ip}")
		return

	if action == "allow":
		pending = manager.allow_last_pending()
		if not pending:
			ctx.warning("No hay solicitud pendiente para autorizar")
			return
		ctx.success(
			f"IP autorizada: {pending.get('ip')} para path {pending.get('path')}"
		)
		return

	if action == "deny":
		pending = manager.deny_last_pending()
		if not pending:
			ctx.warning("No hay solicitud pendiente para rechazar")
			return
		ctx.success(
			f"Solicitud rechazada: IP={pending.get('ip')} path={pending.get('path')}"
		)
		return

	ctx.error(f"Subcomando desconocido: 'livefeed {action}'")
	ctx.print("Usa 'livefeed help' para ver comandos disponibles")

