"""Estado y lógica central de la ruleta livefeed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SpinWheelParticipant:
	channel_id: str
	username: str
	avatar_url: str
	joined_at: str


class SpinWheelState:
	def __init__(self) -> None:
		self._active = False
		self._keep_winner = False
		self._mini_mode = False
		self._participants: dict[str, SpinWheelParticipant] = {}
		self._started_at: str | None = None

	@property
	def active(self) -> bool:
		return self._active

	@property
	def keep_winner(self) -> bool:
		return self._keep_winner

	@property
	def mini_mode(self) -> bool:
		return self._mini_mode

	@property
	def participants_count(self) -> int:
		return len(self._participants)

	def start_round(self) -> None:
		self._active = True
		self._mini_mode = False
		self._participants.clear()
		self._started_at = datetime.utcnow().isoformat()

	def stop_round(self) -> None:
		self._active = False

	def reset_all(self) -> None:
		self._active = False
		self._keep_winner = False
		self._mini_mode = False
		self._participants.clear()
		self._started_at = None

	def set_keep_winner(self, value: bool) -> None:
		self._keep_winner = bool(value)

	def toggle_keep_winner(self) -> bool:
		self._keep_winner = not self._keep_winner
		return self._keep_winner

	def set_mini_mode(self, value: bool) -> None:
		self._mini_mode = bool(value)

	def toggle_mini_mode(self) -> bool:
		self._mini_mode = not self._mini_mode
		return self._mini_mode

	def add_participant(self, channel_id: str, username: str, avatar_url: str) -> tuple[bool, SpinWheelParticipant | None]:
		if not self._active:
			return False, None

		channel_key = (channel_id or "").strip()
		if not channel_key or channel_key in self._participants:
			return False, self._participants.get(channel_key)

		participant = SpinWheelParticipant(
			channel_id=channel_key,
			username=username.strip() or "Anónimo",
			avatar_url=(avatar_url or "").strip(),
			joined_at=datetime.utcnow().isoformat(),
		)
		self._participants[channel_key] = participant
		return True, participant


_spinwheel_state: SpinWheelState | None = None


def get_spinwheel_state() -> SpinWheelState:
	global _spinwheel_state
	if _spinwheel_state is None:
		_spinwheel_state = SpinWheelState()
	return _spinwheel_state

