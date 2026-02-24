"""
Earning logic for points by chat activity.
"""
from __future__ import annotations

from typing import Dict, Optional

from backend.managers.economy_manager import award_message_points
from backend.services.discord_bot.config import get_channels_config
from backend.services.discord_bot.config.economy import get_economy_config


def process_message_earning(
	discord_id: str,
	guild_id: int,
	channel_id: int,
) -> Dict[str, Optional[int]]:
	"""
	Processes a message and awards points if eligible.
	"""
	config = get_economy_config(guild_id)

	if not config.is_earning_channel(channel_id):
		return {
			"awarded": 0,
			"points_added": 0,
			"global_points": None,
		}

	amount = config.get_points_amount()
	interval = config.get_points_interval()

	return award_message_points(
		discord_id=str(discord_id),
		guild_id=guild_id,
		amount=amount,
		interval_seconds=interval,
	)


def process_voice_earning(
	discord_id: str,
	guild_id: int,
) -> Dict[str, Optional[int]]:
	"""
	Processes voice-call earning using the same interval/amount as chat earning.
	Skips awarding if user is in configured AFK voice channel.
	"""
	return process_voice_earning_in_channel(
		discord_id=discord_id,
		guild_id=guild_id,
		voice_channel_id=None,
	)


def process_voice_earning_in_channel(
	discord_id: str,
	guild_id: int,
	voice_channel_id: Optional[int],
) -> Dict[str, Optional[int]]:
	"""
	Processes voice-call earning using the same interval/amount as chat earning.
	"""
	channels_config = get_channels_config(guild_id)
	afk_voice_channel_id = channels_config.get_channel("afk_voice_channel")
	if afk_voice_channel_id and voice_channel_id and int(afk_voice_channel_id) == int(voice_channel_id):
		return {
			"awarded": 0,
			"points_added": 0,
			"global_points": None,
		}

	config = get_economy_config(guild_id)
	amount = config.get_points_amount()
	interval = config.get_points_interval()

	return award_message_points(
		discord_id=str(discord_id),
		guild_id=guild_id,
		amount=amount,
		interval_seconds=interval,
	)
