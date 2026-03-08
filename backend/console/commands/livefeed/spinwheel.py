"""Comandos de consola para controlar la ruleta livefeed."""

from __future__ import annotations

from typing import Any

from backend.managers.user_lookup_manager import find_user_by_global_id
from backend.services.activities.livefeed.spinwheel import get_spinwheel_state
from backend.services.events_websocket import general as ws_general
from backend.services.events_websocket.livefeed import spinwheel as ws_spinwheel


DEFAULT_AVATAR = "https://th.bing.com/th/id/OIP.aiDGdmdUAX_iNgRMERipyQHaHF?rs=1&pid=ImgDetMain"


def _normalize_avatar_url(raw_url: str | None) -> str:
	value = str(raw_url or "").strip()
	if not value:
		return DEFAULT_AVATAR

	lower = value.lower()
	if lower.startswith("http://") or lower.startswith("https://"):
		return value

	clean = value.lstrip("/").replace("\\", "/")
	if clean.startswith("media/"):
		return f"/{clean}"

	return DEFAULT_AVATAR


async def run_spinwheel_console_action(action: str, ctx: Any) -> None:
	"""
	Ejecuta una acción de ruleta desde consola.

	Acciones soportadas:
	- ruleta: inicia ruleta y redirige a ruleta.html
	- rgirar: gira la ruleta activa
	- ragg <id_universal>: agrega usuario a ruleta con avatar
	- reend/rend: finaliza ruleta y vuelve a main.html
	"""
	command = str(action or "").strip().lower()
	state = get_spinwheel_state()

	guarded_commands = {"ruleta", "rgirar", "ragg", "reend", "rend"}
	if command in guarded_commands and not ws_general.is_ws_endpoint_available():
		ctx.warning("WebSocket no disponible. Enciende primero con 'wsocket on' y verifica con 'wsocket status'.")
		return

	if command == "ruleta":
		state.start_round()
		ok_redirect = await ws_general.change_page("ruleta.html")
		ok_reset = await ws_spinwheel.reset_wheel()
		ok_kw = await ws_spinwheel.keepwinner(state.keep_winner)
		ok_started = await ws_general.send_update({"type": "spinwheel_started", "message": "La ruleta ya inició."})
		if ok_redirect and ok_reset and ok_kw and ok_started:
			ctx.success("Ruleta iniciada. Redirigiendo livefeed a ruleta.html")
		else:
			ctx.warning("Ruleta iniciada, pero hubo fallas enviando eventos por websocket. Verifica 'wsocket status'")
		return

	if command == "rgirar":
		if not state.active:
			ctx.warning("No hay ruleta activa. Usa 'ruleta' primero")
			return

		success = await ws_spinwheel.spin_wheel()
		if not success:
			ctx.warning("No hay participantes cargados para girar la ruleta")
			return

		ctx.success("Girando ruleta...")
		return

	if command == "ragg":
		if not state.active:
			ctx.warning("No hay ruleta activa. Usa 'ruleta' primero")
			return

		if not getattr(ctx, "args", None):
			ctx.error("Uso: ragg <ID_UNIVERSAL>")
			return

		raw_id = str(ctx.args[0]).strip()
		if not raw_id.isdigit():
			ctx.error("ID universal invalido. Debe ser numerico")
			return

		lookup = find_user_by_global_id(int(raw_id))
		if not lookup:
			ctx.error(f"No existe usuario con ID universal {raw_id}")
			return

		if lookup.youtube_profile and lookup.youtube_profile.youtube_channel_id:
			platform_channel_id = f"yt:{lookup.youtube_profile.youtube_channel_id}"
			avatar_url = lookup.youtube_profile.channel_avatar_url
		elif lookup.discord_profile and lookup.discord_profile.discord_id:
			platform_channel_id = f"dc:{lookup.discord_profile.discord_id}"
			avatar_url = lookup.discord_profile.avatar_url
		else:
			platform_channel_id = f"id:{lookup.user_id}"
			avatar_url = None

		display_name = str(lookup.display_name or f"user_{lookup.user_id}").strip()
		if not display_name.startswith("@"):
			display_name = f"@{display_name}"

		final_avatar = _normalize_avatar_url(avatar_url)
		added, participant = state.add_participant(
			channel_id=platform_channel_id,
			username=display_name,
			avatar_url=final_avatar,
		)

		if not added:
			ctx.warning(f"{display_name} ya esta dentro de esta ruleta")
			return

		assert participant is not None
		ok_add = await ws_spinwheel.add_item(participant.username, participant.avatar_url or DEFAULT_AVATAR)
		if not ok_add:
			state.remove_participant(platform_channel_id)
			ctx.warning("No se pudo enviar add_item por websocket. Usuario no agregado a la ruleta (rollback aplicado)")
			return

		ctx.success(f"Agregado a ruleta: {participant.username} (ID {lookup.user_id})")
		return

	if command in {"reend", "rend"}:
		state.reset_all()
		ok_reset = await ws_spinwheel.reset_wheel()
		ok_kw = await ws_spinwheel.keepwinner(False)
		ok_mini = await ws_general.send_update({"type": "toggle_mini", "value": False})
		ok_redirect = await ws_general.change_page("main.html")
		if ok_reset and ok_kw and ok_mini and ok_redirect:
			ctx.success("Ruleta finalizada y reiniciada. Volviendo a main.html")
		else:
			ctx.warning("Ruleta finalizada, pero hubo fallas enviando eventos por websocket. Verifica 'wsocket status'")
		return

	ctx.error(f"Acción de ruleta no soportada: {command}")
