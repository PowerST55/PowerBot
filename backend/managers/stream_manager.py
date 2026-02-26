"""Gestor de estado de stream de YouTube.

Centraliza la detección de emisiones en vivo y mantiene en caché
información básica (título, URL, video_id) para que otros módulos
puedan consultarla sin golpear la API innecesariamente.

Este módulo **no** enciende ni apaga YAPI directamente; sólo expone
el estado del stream. La consola (y, en el futuro, Discord/web)
pueden decidir qué hacer cuando hay o no hay emisión.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


@dataclass
class StreamInfo:
	"""Información básica del stream actual.

	Sólo guarda datos de alto nivel para que otros módulos puedan
	mostrarlos en UI o usarlos en lógica de negocio.
	"""

	is_live: bool = False
	video_id: Optional[str] = None
	title: Optional[str] = None
	url: Optional[str] = None
	last_checked: Optional[str] = None  # ISO 8601
	last_status_change: Optional[str] = None  # ISO 8601


class StreamManager:
	"""Gestiona el estado de la emisión de YouTube.

	- Detecta si hay un stream en vivo usando YouTubeClient.
	- Mantiene en memoria el estado actual.
	- Persiste el último estado en disco para consultas baratas.
	"""

	def __init__(self, data_dir: Optional[Path] = None) -> None:
		# Directorio de datos: backend/data/youtube_bot por defecto
		if data_dir is None:
			backend_dir = Path(__file__).resolve().parents[1]
			data_dir = backend_dir / "data" / "youtube_bot"

		self.data_dir = Path(data_dir)
		self.data_dir.mkdir(parents=True, exist_ok=True)

		self.state_file = self.data_dir / "active_stream.json"

		# Estado en memoria
		self._state: StreamInfo = StreamInfo()

		# Cargar estado previo si existe
		self._load_state()

	# ------------------------------------------------------------------
	# Persistencia
	# ------------------------------------------------------------------
	def _load_state(self) -> None:
		"""Carga el último estado persistido si existe.

		No lanza excepciones al exterior; en caso de error se deja
		el estado en valores por defecto.
		"""

		try:
			if not self.state_file.exists():
				return

			with open(self.state_file, "r", encoding="utf-8") as f:
				data = json.load(f)

			self._state = StreamInfo(
				is_live=bool(data.get("is_live", False)),
				video_id=data.get("video_id"),
				title=data.get("title"),
				url=data.get("url"),
				last_checked=data.get("last_checked"),
				last_status_change=data.get("last_status_change"),
			)
		except Exception as exc:  # pragma: no cover - sólo logging
			logger.error("Error al cargar estado de stream: %s", exc)

	def _save_state(self) -> None:
		"""Persiste el estado actual en disco."""

		try:
			data = asdict(self._state)
			with open(self.state_file, "w", encoding="utf-8") as f:
				json.dump(data, f, indent=2, ensure_ascii=False)
		except Exception as exc:  # pragma: no cover - sólo logging
			logger.error("Error al guardar estado de stream: %s", exc)

	# ------------------------------------------------------------------
	# API pública
	# ------------------------------------------------------------------
	def get_current_stream(self) -> Optional[Dict[str, Any]]:
		"""Devuelve información del stream actual desde memoria.

		No realiza llamadas a la API. Si `is_live` es False, devuelve
		igualmente el último estado conocido para que pueda mostrarse
		información histórica si se desea.
		"""

		data = asdict(self._state)
		return data

	def is_live(self) -> bool:
		"""Indica si el último estado conocido está en vivo."""

		return bool(self._state.is_live)

	def get_status(self) -> Dict[str, Any]:
		"""Devuelve un resumen de estado para comandos tipo `yt status`."""

		return {
			"is_live": self._state.is_live,
			"title": self._state.title,
			"url": self._state.url,
			"video_id": self._state.video_id,
			"last_checked": self._state.last_checked,
			"last_status_change": self._state.last_status_change,
			"data_file": str(self.state_file),
		}

	# ------------------------------------------------------------------
	# Detección usando YouTubeClient
	# ------------------------------------------------------------------
	def detect_stream(self, youtube_client: Any) -> Dict[str, Any]:
		"""Detecta si hay una emisión activa usando YouTubeClient.

		Args:
			youtube_client: Instancia de cliente de YouTube que tenga
				un atributo `service` compatible con `googleapiclient`.

		Returns:
			dict con:
			  - is_live (bool)
			  - title (str|None)
			  - url (str|None)
			  - video_id (str|None)
			  - changed (bool) -> si cambió el estado respecto al anterior
		"""

		now_iso = datetime.utcnow().isoformat()

		try:
			# Usamos directamente el servicio subyacente para evitar
			# duplicar lógica en YouTubeClient y aprovechar una única
			# llamada a liveBroadcasts.list.
			service = getattr(youtube_client, "service", None)
			if service is None:
				raise RuntimeError("YouTubeClient no tiene atributo 'service'")

			request = service.liveBroadcasts().list(
				part="id,snippet",
				broadcastStatus="active",
				maxResults=1,
			)
			response = request.execute()

			items = response.get("items") or []
			if not items:
				# No hay emisión activa
				was_live = self._state.is_live
				if was_live:
					# Cambio de estado: pasó de ON a OFF
					self._state.is_live = False
					self._state.video_id = None
					self._state.title = None
					self._state.url = None
					self._state.last_checked = now_iso
					self._state.last_status_change = now_iso
					self._save_state()
					return {"is_live": False, "title": None, "url": None, "video_id": None, "changed": True}

				# Ya estaba en OFF, sólo actualizamos last_checked
				self._state.last_checked = now_iso
				self._save_state()
				return {"is_live": False, "title": None, "url": None, "video_id": None, "changed": False}

			# Hay al menos una emisión activa
			item = items[0]
			video_id = item.get("id")
			snippet = item.get("snippet") or {}
			title = snippet.get("title")

			url = f"https://www.youtube.com/watch?v={video_id}" if video_id else None

			# Determinar si hubo cambio
			changed = not self._state.is_live or self._state.video_id != video_id

			self._state.is_live = True
			self._state.video_id = video_id
			self._state.title = title
			self._state.url = url
			self._state.last_checked = now_iso
			if changed:
				self._state.last_status_change = now_iso

			self._save_state()

			return {
				"is_live": True,
				"title": title,
				"url": url,
				"video_id": video_id,
				"changed": changed,
			}

		except Exception as exc:  # pragma: no cover - sólo logging
			logger.error("Error al detectar stream activo: %s", exc)
			# No tocamos el estado salvo last_checked para saber que se intentó
			self._state.last_checked = now_iso
			self._save_state()
			return {
				"is_live": self._state.is_live,
				"title": self._state.title,
				"url": self._state.url,
				"video_id": self._state.video_id,
				"changed": False,
				"error": str(exc),
			}


__all__ = ["StreamManager", "StreamInfo"]
