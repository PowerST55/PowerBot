"""
Earning logic for points by YouTube chat activity.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from backend.managers.economy_manager import award_youtube_message_points
from backend.services.discord_bot.config.economy import (
	get_economy_config,
	list_configured_economy_guild_ids,
)
from backend.services.youtube_api.config.economy import get_youtube_economy_config


logger = logging.getLogger(__name__)


def _resolve_discord_earning_source() -> tuple[Optional[int], Optional[object]]:
	"""Obtiene la config de Discord que gobierna earning de YouTube."""
	config = get_youtube_economy_config()
	source_guild_id = config.get_sync_source_guild_id()

	if source_guild_id is None:
		guild_ids = list_configured_economy_guild_ids()
		if len(guild_ids) == 1:
			source_guild_id = guild_ids[0]

	if source_guild_id is None:
		return (None, None)

	return (source_guild_id, get_economy_config(source_guild_id))


def process_message_earning(
	youtube_channel_id: str,
	live_chat_id: str,
	source_id: str | None = None,
) -> Dict[str, Optional[int]]:
	"""
	Procesa un mensaje de YouTube y otorga puntos si corresponde por cooldown.
	"""
	youtube_config = get_youtube_economy_config()
	source_guild_id, discord_config = _resolve_discord_earning_source()

	if discord_config is not None:
		if not discord_config.is_earning_enabled():
			return {
				"awarded": 0,
				"points_added": 0,
				"global_points": None,
				"reason": "earning_disabled",
				"source_guild_id": source_guild_id,
			}
		amount = discord_config.get_points_amount()
		interval = discord_config.get_points_interval()
	else:
		if not youtube_config.is_earning_enabled():
			return {
				"awarded": 0,
				"points_added": 0,
				"global_points": None,
				"reason": "earning_disabled",
			}
		amount = youtube_config.get_points_amount()
		interval = youtube_config.get_points_interval()

	if amount <= 0 or interval <= 0:
		return {
			"awarded": 0,
			"points_added": 0,
			"global_points": None,
			"reason": "invalid_amount_or_interval",
		}

	result = award_youtube_message_points(
		youtube_channel_id=str(youtube_channel_id),
		chat_id=str(live_chat_id),
		amount=amount,
		interval_seconds=interval,
		source_id=source_id,
	)

	if not result.get("awarded"):
		logger.info(
			"YouTube earning omitido: channel_id=%s chat_id=%s source_id=%s reason=%s source_guild_id=%s",
			youtube_channel_id,
			live_chat_id,
			source_id,
			result.get("reason", "unknown"),
			source_guild_id,
		)

	if source_guild_id is not None:
		result.setdefault("source_guild_id", source_guild_id)

	return result

