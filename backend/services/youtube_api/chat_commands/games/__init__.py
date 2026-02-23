"""Comandos de juegos para YouTube chat."""

from .gamble import process_gamble_command
from .slots import process_slots_command

__all__ = ["process_gamble_command", "process_slots_command"]
