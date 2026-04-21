"""Compatibilidad para imports antiguos del toggle de economía admin."""

from backend.services.youtube_api.config.admin_economy_toggle import (
	is_admin_aps_enabled,
	load_admin_economy_toggle,
	save_admin_economy_toggle,
	set_admin_aps_enabled,
)
