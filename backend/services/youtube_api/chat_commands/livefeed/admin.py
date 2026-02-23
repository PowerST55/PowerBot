"""Comandos administrativos de livefeed para YouTube chat."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.services.activities.livefeed.spinwheel import get_spinwheel_state
from backend.services.events_websocket import general as ws_general
from backend.services.events_websocket.livefeed import spinwheel as ws_spinwheel

from ...send_message import send_chat_message

if TYPE_CHECKING:
	from ...youtube_core import YouTubeClient
	from ...youtube_types import YouTubeMessage


ADMIN_RULETA_ALIASES = {"ruleta"}
ADMIN_SPIN_ALIASES = {"rgirar"}
ADMIN_KEEP_WINNER_ALIASES = {"kw", "keepwinner"}
ADMIN_MINI_ALIASES = {"rmini"}
ADMIN_END_ALIASES = {"rend"}


def _is_admin(message: "YouTubeMessage") -> bool:
	return bool(message.is_owner or message.is_moderator)


def _parse_bool_arg(raw: str) -> bool | None:
	value = raw.strip().lower()
	if value in {"1", "true", "on", "si", "sí", "yes", "y", "activar", "enabled"}:
		return True
	if value in {"0", "false", "off", "no", "n", "desactivar", "disabled"}:
		return False
	return None


async def process_livefeed_admin_command(
	command: str,
	args: list[str],
	message: "YouTubeMessage",
	client: "YouTubeClient",
	live_chat_id: str,
) -> bool:
	"""Procesa comandos admin de ruleta en livefeed."""
	if command not in (
		ADMIN_RULETA_ALIASES
		| ADMIN_SPIN_ALIASES
		| ADMIN_KEEP_WINNER_ALIASES
		| ADMIN_MINI_ALIASES
		| ADMIN_END_ALIASES
	):
		return False

	if not _is_admin(message):
		await send_chat_message(client, live_chat_id, f"❌ @{message.author_name} no tienes permisos de administrador para ese comando.")
		return True

	state = get_spinwheel_state()

	if command in ADMIN_RULETA_ALIASES:
		state.start_round()
		await ws_general.change_page("ruleta.html")
		await ws_spinwheel.reset_wheel()
		await ws_spinwheel.keepwinner(state.keep_winner)
		await ws_general.send_update({"type": "spinwheel_started", "message": "La ruleta ya inició."})
		await send_chat_message(client, live_chat_id, "🎯 Ruleta iniciada. Escriban !p para participar.")
		return True

	if command in ADMIN_SPIN_ALIASES:
		if not state.active:
			await send_chat_message(client, live_chat_id, "❌ No hay ruleta activa. Usa !ruleta primero.")
			return True

		success = await ws_spinwheel.spin_wheel()
		if not success:
			await send_chat_message(client, live_chat_id, "❌ No hay participantes para girar la ruleta.")
			return True

		await send_chat_message(client, live_chat_id, "🎡 Girando ruleta...")
		return True

	if command in ADMIN_KEEP_WINNER_ALIASES:
		if args:
			parsed = _parse_bool_arg(args[0])
			if parsed is None:
				await send_chat_message(client, live_chat_id, "Uso: !kw [on/off]. También puedes usar !keepwinner")
				return True
			new_value = parsed
			state.set_keep_winner(new_value)
		else:
			new_value = state.toggle_keep_winner()

		await ws_spinwheel.keepwinner(new_value)
		status = "ON" if new_value else "OFF"
		await send_chat_message(client, live_chat_id, f"🏆 keep winner: {status}")
		return True

	if command in ADMIN_MINI_ALIASES:
		if not state.active:
			await send_chat_message(client, live_chat_id, "❌ No hay ruleta activa. Usa !ruleta primero.")
			return True

		if args:
			parsed = _parse_bool_arg(args[0])
			if parsed is None:
				await send_chat_message(client, live_chat_id, "Uso: !rmini [on/off]")
				return True
			mini_value = parsed
			state.set_mini_mode(mini_value)
		else:
			mini_value = state.toggle_mini_mode()

		await ws_general.send_update({"type": "toggle_mini", "value": mini_value})
		status = "MINI" if mini_value else "NORMAL"
		await send_chat_message(client, live_chat_id, f"🪄 Ruleta en modo: {status}")
		return True

	if command in ADMIN_END_ALIASES:
		state.reset_all()
		await ws_spinwheel.reset_wheel()
		await ws_spinwheel.keepwinner(False)
		await ws_general.send_update({"type": "toggle_mini", "value": False})
		await ws_general.change_page("main.html")
		await send_chat_message(client, live_chat_id, "✅ Ruleta finalizada y reiniciada. Volviendo a main.html")
		return True

	return False

