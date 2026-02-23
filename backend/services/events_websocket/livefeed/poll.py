from __future__ import annotations

from ..general import send_update


_mini_encuesta = False


def is_mini_enabled() -> bool:
	return _mini_encuesta


async def toggle_mini(timeout: float = 3) -> bool:
	"""Alterna el mini modo de la encuesta y envía la actualización."""
	global _mini_encuesta
	_mini_encuesta = not _mini_encuesta
	data = {"type": "toggle_mini", "value": _mini_encuesta}
	return await send_update(data, timeout=timeout)


async def settittle(value: str, timeout: float = 3) -> bool:
	"""Cambia el título de la encuesta (compat legacy)."""
	data = {"type": "tittle", "value": value}
	return await send_update(data, timeout=timeout)


async def settitle(value: str, timeout: float = 3) -> bool:
	"""Alias corregido para cambiar título de encuesta."""
	return await settittle(value, timeout=timeout)


async def addoption(value: str, timeout: float = 3) -> bool:
	"""Añade una opción a la encuesta."""
	data = {"type": "addItem", "name": value}
	return await send_update(data, timeout=timeout)


async def addvote(value: int, autor: str, timeout: float = 3) -> bool:
	"""Añade un voto en la encuesta."""
	data = {"type": "voteUpdate", "index": value, "autor": autor}
	return await send_update(data, timeout=timeout)


async def showwinner(timeout: float = 3) -> bool:
	"""Finaliza la encuesta y muestra el ganador."""
	data = {"type": "pollEnd"}
	return await send_update(data, timeout=timeout)


async def polltime(time: int, timeout: float = 3) -> bool:
	"""Envía el tiempo restante de la encuesta."""
	data = {"type": "polltime", "time": time}
	return await send_update(data, timeout=timeout)
