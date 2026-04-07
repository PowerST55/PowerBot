from __future__ import annotations

from typing import Any

from backend.managers.avatar_manager import AvatarManager
from backend.managers.economy_manager import get_global_leaderboard
from backend.managers.user_manager import (
	get_discord_profile_by_user_id,
	get_youtube_profile_by_user_id,
)
from backend.services.web.config.economy import create_web_economy_manager


def _resolve_top_avatar_url(*, discord_profile: Any, youtube_profile: Any) -> str | None:
	"""Prefiere avatar cacheado localmente para evitar URLs remotas vencidas en web."""
	if discord_profile:
		local_avatar = AvatarManager.get_avatar_local_path(str(discord_profile.discord_id), "discord")
		if local_avatar:
			return f"/{local_avatar}"
		if discord_profile.avatar_url:
			return discord_profile.avatar_url

	if youtube_profile:
		local_avatar = AvatarManager.get_avatar_local_path(
			str(youtube_profile.youtube_channel_id),
			"youtube",
		)
		if local_avatar:
			return f"/{local_avatar}"
		if youtube_profile.channel_avatar_url:
			return youtube_profile.channel_avatar_url

	return None


def get_top10_payload(limit: int = 10) -> dict[str, Any]:
	"""Empaqueta el top global para consumo web."""
	raw_top = get_global_leaderboard(limit=limit)
	items: list[dict[str, Any]] = []
	currency_cfg = create_web_economy_manager().get_currency()

	for rank, row in enumerate(raw_top, start=1):
		user_id = int(row.get("user_id", 0))
		username = row.get("username") or f"User {user_id}"
		balance = float(row.get("balance", 0) or 0)

		discord_profile = get_discord_profile_by_user_id(user_id)
		youtube_profile = get_youtube_profile_by_user_id(user_id)

		platforms: list[str] = []
		if youtube_profile:
			platforms.append("YouTube")
		if discord_profile:
			platforms.append("Discord")

		display_name = username
		if discord_profile and discord_profile.discord_username:
			display_name = discord_profile.discord_username
		elif youtube_profile and youtube_profile.youtube_username:
			display_name = youtube_profile.youtube_username

		avatar_url = _resolve_top_avatar_url(
			discord_profile=discord_profile,
			youtube_profile=youtube_profile,
		)

		items.append(
			{
				"rank": rank,
				"user_id": user_id,
				"username": username,
				"display_name": display_name,
				"balance": balance,
				"avatar_url": avatar_url,
				"platforms": platforms,
			}
		)

	return {
		"ok": True,
		"count": len(items),
		"currency": {
			"name": currency_cfg.get("name", "pews"),
			"symbol": currency_cfg.get("symbol", "💎"),
		},
		"items": items,
	}
