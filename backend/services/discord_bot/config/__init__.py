"""
Configuración del bot de Discord.
"""
from .channels import get_channels_config, ChannelsConfig
from .economy import get_economy_config, EconomyConfig
from .mine_config import get_mine_config, MineConfig

__all__ = [
	"get_channels_config",
	"ChannelsConfig",
	"get_economy_config",
	"EconomyConfig",
	"get_mine_config",
	"MineConfig",
]
