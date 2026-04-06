"""
Helpers para enviar mensajes al chat de YouTube.
Implementa reintentos conservadores para evitar duplicados.
"""

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from threading import Lock

from .youtube_core import YouTubeClient

logger = logging.getLogger(__name__)


_SEND_LOCK = Lock()
_CHAT_SEND_TIMESTAMPS = defaultdict(deque)
_LAST_MESSAGE_BY_CHAT = {}
_SEND_WINDOW_SEC = float(os.getenv("YT_SEND_WINDOW_SEC", "15"))
_SEND_MAX_PER_WINDOW = int(os.getenv("YT_SEND_MAX_PER_WINDOW", "12"))
_SEND_DUPLICATE_COOLDOWN_SEC = float(os.getenv("YT_SEND_DUPLICATE_COOLDOWN_SEC", "4"))


def _should_send_message(live_chat_id: str, message: str) -> bool:
	now = time.monotonic()
	chat_key = str(live_chat_id)
	message_key = (chat_key, str(message or "").strip())

	with _SEND_LOCK:
		last_sent = _LAST_MESSAGE_BY_CHAT.get(message_key)
		if last_sent is not None and (now - last_sent) < _SEND_DUPLICATE_COOLDOWN_SEC:
			return False

		timestamps = _CHAT_SEND_TIMESTAMPS[chat_key]
		while timestamps and (now - timestamps[0]) > _SEND_WINDOW_SEC:
			timestamps.popleft()

		if len(timestamps) >= _SEND_MAX_PER_WINDOW:
			return False

		timestamps.append(now)
		_LAST_MESSAGE_BY_CHAT[message_key] = now
		return True


def send_chat_message_sync(
	client: YouTubeClient,
	live_chat_id: str,
	message: str,
	max_retries: int = 2,
) -> bool:
	"""
	Envia un mensaje al chat con reintentos inteligentes.
	Solo retorna True si el mensaje fue REALMENTE entregado.
	
	Args:
		client: Cliente de YouTube
		live_chat_id: ID del chat en vivo
		message: Mensaje a enviar
		max_retries: Máximo 2 reintentos para errores recuperables
	
	Returns:
		True si se envió CONFIRMATORIAMENTE, False si error o incierto
	"""
	response = None
	attempt = 0

	if not _should_send_message(live_chat_id, message):
		logger.warning(
			"⏱ Mensaje de YouTube omitido por control de rafaga/duplicado (chat=%s)",
			live_chat_id,
		)
		return False
	
	while attempt <= max_retries:
		attempt += 1
		
		try:
			# Intentar enviar
			response = client.send_message(live_chat_id, message)
			
			# Verificar resultado
			if isinstance(response, dict):
				# ✅ Mensaje enviado exitosamente - tenemos ID
				if response.get("id"):
					logger.debug(f"Mensaje enviado confirmado (intento {attempt}, ID: {response.get('id')})")
					return True
				
				# 🔴 SSL error: reintentar una vez más
				if response.get("ssl_error"):
					if attempt < max_retries:
						logger.warning(f"🔴 [Intento {attempt}] SSL error: {response.get('message')} - reintentando en 1s...")
						time.sleep(1)
						continue
					else:
						logger.error(f"❌ [Intento {attempt}] SSL error persistente - no se confirma entrega")
						return False  # No asumir éxito
				
				# 🔴 Error de red: reintentar una vez
				if response.get("network_error"):
					if attempt < max_retries:
						logger.warning(f"🔴 [Intento {attempt}] Error de red: {response.get('message')} - reintentando en 1s...")
						time.sleep(1)
						continue
					else:
						logger.error(f"❌ [Intento {attempt}] Error de red persistente - no se confirma entrega")
						return False
				
				# ❌ Errores que no se deben reintentar
				if response.get("quota_error"):
					logger.error("❌ Cuota de YouTube excedida - intenta más tarde")
					return False
				if response.get("permission_error"):
					logger.error("❌ Permiso denegado - verifica credenciales")
					return False
				if response.get("http_error"):
					logger.error("❌ Error HTTP - verifica el chat ID")
					return False
				if response.get("unexpected_error"):
					logger.error("❌ Error inesperado en la API")
					return False
				if response.get("empty_response"):
					logger.warning("⚠️  Respuesta vacía del servidor (chat cerrado?)")
					return False
				
				# ❌ Respuesta vacía o sin ID claro
				logger.warning(f"❌ [Intento {attempt}] Respuesta no concluyente: {response}")
				if attempt < max_retries:
					logger.info(f"Reintentando (intento {attempt + 1}/{max_retries})...")
					time.sleep(1)
					continue
				else:
					logger.error("❌ No se pudo confirmar envío después de reintentos")
					return False
			
			# ❌ No es dict (inesperado)
			logger.error(f"❌ Tipo de respuesta inesperado: {type(response)} = {response}")
			return False
			
		except Exception as exc:
			logger.error(f"❌ Excepción en send_chat_message_sync: {type(exc).__name__}: {exc}")
			if attempt < max_retries:
				logger.info(f"Reintentando (intento {attempt + 1}/{max_retries})...")
				time.sleep(1)
				continue
			return False
	
	logger.error("❌ Agotados todos los reintentos")
	return False


async def send_chat_message(
	client: YouTubeClient,
	live_chat_id: str,
	message: str,
) -> bool:
	"""
	Envia un mensaje al chat usando un thread para la llamada sync.
	
	Args:
		client: Cliente de YouTube
		live_chat_id: ID del chat en vivo
		message: Mensaje a enviar
	
	Returns:
		True si se envió, False si error
	"""
	try:
		return await asyncio.to_thread(
			send_chat_message_sync,
			client,
			live_chat_id,
			message
		)
	except Exception as e:
		logger.error(f"Error en send_chat_message: {e}")
		return False

