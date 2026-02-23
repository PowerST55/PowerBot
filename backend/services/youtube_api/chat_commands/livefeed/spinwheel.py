"""Comando de participación de ruleta para YouTube chat."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.services.activities.livefeed.spinwheel import get_spinwheel_state
from backend.services.events_websocket.livefeed import spinwheel as ws_spinwheel

from ...send_message import send_chat_message

if TYPE_CHECKING:
	from ...youtube_core import YouTubeClient
	from ...youtube_types import YouTubeMessage


PARTICIPATE_ALIASES = {"p", "participar", "join"}
DEFAULT_AVATAR = "https://th.bing.com/th/id/OIP.aiDGdmdUAX_iNgRMERipyQHaHF?rs=1&pid=ImgDetMain"


async def process_spinwheel_participation_command(
	command: str,
	args: list[str],
	message: "YouTubeMessage",
	client: "YouTubeClient",
	live_chat_id: str,
) -> bool:
	"""Procesa !p / !participar / !join para unirse a la ruleta activa."""
	if command not in PARTICIPATE_ALIASES:
		return False

	state = get_spinwheel_state()
	if not state.active:
		await send_chat_message(client, live_chat_id, "❌ La ruleta no está activa. Espera a que un admin use !ruleta")
		return True

	added, participant = state.add_participant(
		channel_id=message.author_channel_id,
		username=message.author_name,
		avatar_url=message.profile_image_url or DEFAULT_AVATAR,
	)

	if not added:
		await send_chat_message(client, live_chat_id, f"⚠ @{message.author_name} ya estás dentro de esta ruleta.")
		return True

	assert participant is not None
	await ws_spinwheel.add_item(participant.username, participant.avatar_url or DEFAULT_AVATAR)
	await send_chat_message(client, live_chat_id, f"✅ @{participant.username} se unió a la ruleta.")
	return True

