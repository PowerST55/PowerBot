"""
Comandos de YouTube para la consola interactiva.
Combina comandos generales y de configuración.
"""

from .config import YOUTUBE_CONFIG_COMMANDS
from .codes import YOUTUBE_CODES_COMMANDS
from .general import YOUTUBE_COMMANDS as YOUTUBE_GENERAL_COMMANDS

YOUTUBE_COMMANDS = {
    **YOUTUBE_GENERAL_COMMANDS,
    **YOUTUBE_CONFIG_COMMANDS,
    **YOUTUBE_CODES_COMMANDS,
}

__all__ = [
    "YOUTUBE_COMMANDS",
    "YOUTUBE_GENERAL_COMMANDS",
    "YOUTUBE_CONFIG_COMMANDS",
    "YOUTUBE_CODES_COMMANDS",
]
