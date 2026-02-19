"""
Helpers para enviar mensajes al chat de YouTube.
Implementa reintentos conservadores para evitar duplicados.
"""

import asyncio
import logging
import time

from .youtube_core import YouTubeClient

logger = logging.getLogger(__name__)


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
	
	while attempt <= max_retries:
		attempt += 1
		
		try:
			# Intentar enviar
			response = client.send_message(live_chat_id, message)
			
			# Verificar resultado
			if isinstance(response, dict):
				# ✅ Mensaje enviado exitosamente - tenemos ID
				if response.get("id"):
					logger.info(f"✅ [Intento {attempt}] Mensaje enviado CONFIRMADO (ID: {response.get('id')})")
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

