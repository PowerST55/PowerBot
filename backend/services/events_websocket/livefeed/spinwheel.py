from __future__ import annotations

import random
from typing import Iterable

from ..general import send_update


_items: list[str] = []
_participantes_ruleta: set[str] = set()


def get_items() -> list[str]:
	return list(_items)


def set_items(items: Iterable[str]) -> None:
	_items.clear()
	_items.extend(items)


def get_participantes_ruleta() -> set[str]:
	return set(_participantes_ruleta)


def set_participantes_ruleta(participantes: Iterable[str]) -> None:
	_participantes_ruleta.clear()
	_participantes_ruleta.update(participantes)


async def add_item(item: str, url: str, timeout: float = 3) -> bool:
	"""Agrega un elemento a la ruleta y lo envía a los clientes."""
	_items.append(item)
	data = {"type": "add_item", "item": item, "url": url}
	return await send_update(data, timeout=timeout)


async def spin_wheel(timeout: float = 3) -> bool:
	"""Gira la ruleta y envía la señal a los clientes."""
	if not _items:
		return False

	angulo_random = random.uniform(0, 3600)
	desplazamiento_extra = random.uniform(0, 3600)
	rotation = 3440 + angulo_random + desplazamiento_extra

	data = {"type": "spin", "rotation": rotation}
	return await send_update(data, timeout=timeout)


async def reset_wheel(timeout: float = 3) -> bool:
	"""Reinicia la ruleta, eliminando elementos y participantes."""
	_items.clear()
	_participantes_ruleta.clear()
	data = {"type": "reset"}
	return await send_update(data, timeout=timeout)


async def keepwinner(value: bool, timeout: float = 3) -> bool:
	"""Alterna el estado de keep winner."""
	data = {"type": "set_keep_winner", "value": value}
	return await send_update(data, timeout=timeout)


async def updaterul(timeout: float = 3) -> bool:
	"""Envía una actualización general de la ruleta."""
	data = {"type": "update"}
	return await send_update(data, timeout=timeout)
