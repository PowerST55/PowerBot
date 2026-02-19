"""
YouTube Listener Module
Escucha mensajes del chat en vivo de YouTube y los procesa.
Implementa manejo robusto de SSL errors para VPS.
Incluye persistencia automática de usuarios.
"""

import asyncio
import logging
import ssl
from typing import Optional, Callable, Dict, Any, List, Set
from datetime import datetime, timezone
from googleapiclient.errors import HttpError

from .youtube_core import YouTubeClient
from .youtube_types import YouTubeMessage
from .youtube_user_packager import UserPackager
from backend.managers.avatar_manager import AvatarManager

logger = logging.getLogger(__name__)

# Importar YouTubeMessage para backward compatibility
from .youtube_types import YouTubeMessage as YouTubeMessage


class YouTubeListener:
    """
    Escucha mensajes del chat en vivo de YouTube.
    Proporciona una base para procesar comandos y eventos.
    """
    
    def __init__(self, client: YouTubeClient, live_chat_id: str, enable_user_persistence: bool = True):
        """
        Inicializa el listener.
        
        Args:
            client: Cliente de YouTube autenticado
            live_chat_id: ID del chat en vivo
            enable_user_persistence: Si True, guarda automáticamente usuarios en BD
        """
        self.client = client
        self.live_chat_id = live_chat_id
        self.is_running = False
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        
        # Control de mensajes ya procesados
        self._processed_messages: Set[str] = set()
        self._next_page_token: Optional[str] = None
        
        # Configuración de polling
        self.poll_interval_ms = 2000  # Intervalo de polling en milisegundos
        
        # Callbacks para procesar mensajes
        self._message_handlers: List[Callable[[YouTubeMessage], None]] = []
        
        # Persistencia de usuarios
        self.enable_user_persistence = enable_user_persistence
        if enable_user_persistence:
            # Inicializar avatar manager
            AvatarManager.initialize()
            # Registrar handler de persistencia automáticamente
            self.add_message_handler(self._persist_user_handler)
        
        logger.info(f"YouTubeListener initialized for chat: {live_chat_id}")
        if enable_user_persistence:
            logger.info("✅ User persistence enabled")
    
    def add_message_handler(self, handler: Callable[[YouTubeMessage], None]) -> None:
        """
        Agrega un handler para procesar mensajes.
        
        Args:
            handler: Función que recibe un YouTubeMessage
        """
        self._message_handlers.append(handler)
        logger.debug(f"Added message handler: {handler.__name__}")
    
    def remove_message_handler(self, handler: Callable[[YouTubeMessage], None]) -> None:
        """
        Remueve un handler de mensajes.
        
        Args:
            handler: Handler a remover
        """
        if handler in self._message_handlers:
            self._message_handlers.remove(handler)
            logger.debug(f"Removed message handler: {handler.__name__}")
    
    async def start(self) -> None:
        """Inicia el listener en background."""
        if self.is_running:
            logger.warning("Listener already running")
            return

        if not self._message_handlers:
            # Fallback: imprimir mensajes en consola si no hay handlers registrados
            self.add_message_handler(console_message_handler)
        
        self.is_running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._listen_loop())
        logger.info("YouTubeListener started")
    
    async def stop(self) -> None:
        """Detiene el listener."""
        if not self.is_running:
            return
        
        self.is_running = False
        self._stop_event.set()
        
        if self._task:
            await self._task
            self._task = None
        
        logger.info("YouTubeListener stopped")
    
    async def _listen_loop(self) -> None:
        """Loop principal que obtiene mensajes continuamente con protección máxima."""
        logger.info("🎧 Listener loop started - protección máxima activada")
        
        try:
            # Primer fetch: solo guarda IDs existentes sin procesarlos
            # (evita procesar mensajes históricos)
            try:
                await self._fetch_and_skip_existing()
            except Exception as e:
                logger.warning(f"⚠️  Error en skip existing: {e}, continuando...")
            
            poll_failures = 0
            max_consecutive_failures = 10
            
            while self.is_running and not self._stop_event.is_set():
                try:
                    await self._fetch_and_process_messages()
                    poll_failures = 0  # Reset counter on success
                    
                    # Esperar el intervalo de polling
                    poll_interval_seconds = self.poll_interval_ms / 1000.0
                    await asyncio.sleep(poll_interval_seconds)
                    
                except HttpError as e:
                    poll_failures += 1
                    logger.error(f"[{poll_failures}/{max_consecutive_failures}] HTTP error fetching messages: {e}")
                    
                    # Si es un error 403/401, probablemente las credenciales expiraron
                    if e.resp.status in [403, 401]:
                        logger.error("❌ Authentication error - stopping listener")
                        break
                    
                    # Si demasiados errores consecutivos, pausar más
                    if poll_failures >= max_consecutive_failures:
                        logger.error(f"⚠️  {max_consecutive_failures} errores consecutivos, deteniendo temporalmente")
                        break
                    
                    # Esperar un bit más en caso de error
                    await asyncio.sleep(5)
                    
                except ssl.SSLError as e:
                    poll_failures += 1
                    logger.warning(f"🔴 [{poll_failures}/{max_consecutive_failures}] SSL error in listener: {e}")
                    if poll_failures >= max_consecutive_failures:
                        logger.warning(f"⚠️  Demasiados SSL errors, deteniendo")
                        break
                    await asyncio.sleep(3)
                    
                except asyncio.CancelledError:
                    logger.info("Listener loop cancelled")
                    break
                    
                except Exception as e:
                    poll_failures += 1
                    logger.exception(f"❌ [{poll_failures}/{max_consecutive_failures}] Unexpected error in listener loop: {type(e).__name__}: {e}")
                    
                    if poll_failures >= max_consecutive_failures:
                        logger.error(f"⚠️  Demasiados errores inesperados, deteniendo")
                        break
                    
                    # Esperar antes de reintentar
                    await asyncio.sleep(5)
            
            logger.info("✅ Listener loop ended gracefully")
            
        except asyncio.CancelledError:
            logger.info("Listener task was cancelled")
        except Exception as e:
            # EXTERIOR catch-all: NUNCA debe salir sin logging
            logger.exception(f"🔴 CRITICAL: Exception escaped listener loop: {type(e).__name__}: {e}")
        finally:
            self.is_running = False
            logger.info("Listener cleanup complete")

    
    async def _fetch_and_skip_existing(self) -> None:
        """Primera llamada: solo marca mensajes existentes como procesados."""
        try:
            response = await asyncio.to_thread(
                self._fetch_messages_sync
            )
            
            if response:
                items = response.get("items", [])
                for item in items:
                    msg_id = item.get("id")
                    if msg_id:
                        self._processed_messages.add(msg_id)
                
                # Guardar el page token para el siguiente fetch
                self._next_page_token = response.get("nextPageToken")
                self.poll_interval_ms = response.get("pollingIntervalMillis", 2000)
                
                logger.info(f"Skipped {len(items)} existing messages")
        
        except Exception as e:
            logger.error(f"Error skipping existing messages: {e}")
    
    async def _fetch_and_process_messages(self) -> None:
        """Obtiene y procesa nuevos mensajes con protección robusta."""
        try:
            response = await asyncio.to_thread(
                self._fetch_messages_sync
            )
            
            if not response:
                logger.debug("No response from fetch_messages_sync")
                return
            
            try:
                items = response.get("items", [])
                new_messages = []
                
                for item in items:
                    try:
                        msg_id = item.get("id")
                        
                        # Filtrar mensajes ya procesados
                        if msg_id and msg_id not in self._processed_messages:
                            self._processed_messages.add(msg_id)
                            
                            # Crear objeto mensaje
                            message = YouTubeMessage(item)
                            new_messages.append(message)
                            logger.debug(f"New message queued: {message.author_name}: {message.message[:50]}")
                    except Exception as e:
                        logger.error(f"Error processing individual message: {e}")
                        continue
                
                # Procesar nuevos mensajes
                for message in new_messages:
                    try:
                        await self._process_message(message)
                    except Exception as e:
                        logger.error(f"Error in message handler: {type(e).__name__}: {e}")
                        # Continuar con el siguiente mensaje incluso si uno falla
                        continue
                
                # ⚠️ IMPORTANTE: Solo actualizar page token si el fetch fue exitoso
                # Esto evita saltar mensajes si hay errores
                new_page_token = response.get("nextPageToken")
                if new_page_token and new_page_token != self._next_page_token:
                    self._next_page_token = new_page_token
                    logger.debug(f"Updated page token: {new_page_token[:20]}...")
                
                self.poll_interval_ms = response.get("pollingIntervalMillis", 2000)
                
                # Limpiar mensajes antiguos del set (mantener solo los últimos 1000)
                if len(self._processed_messages) > 1000:
                    # Convertir a lista, mantener los últimos 500
                    msg_list = list(self._processed_messages)
                    self._processed_messages = set(msg_list[-500:])
                    logger.debug(f"Cleaned up processed messages cache (kept 500 of {len(msg_list)})")
            except Exception as e:
                logger.error(f"Error in message processing batch: {type(e).__name__}: {e}")
        
        except Exception as e:
            logger.error(f"Error in _fetch_and_process_messages: {type(e).__name__}: {e}")
    
    def _fetch_messages_sync(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene mensajes de la API de forma sincrónica con reintentos para errores SSL.
        
        Returns:
            Response de la API o None si hay error después de reintentos
        """
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                request = self.client.service.liveChatMessages().list(
                    liveChatId=self.live_chat_id,
                    part="snippet,authorDetails",
                    pageToken=self._next_page_token
                )
                response = request.execute()
                
                # ✅ Validar que la respuesta sea válida
                if response and isinstance(response, dict):
                    logger.debug(f"✅ Fetch successful (attempt {attempt + 1}/{max_retries})")
                    return response
                else:
                    logger.warning(f"⚠️  Invalid response format: {type(response)}")
                    return None
                
            except ssl.SSLError as e:
                logger.warning(f"🔴 SSL error fetching messages (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Backoff exponencial
                    continue
                else:
                    logger.error("❌ SSL error persisted after all retries")
                    return None
                
            except HttpError as e:
                if "quotaExceeded" in str(e):
                    logger.warning("⚠️  YouTube API quota exceeded")
                    return None
                elif "badRequest" in str(e):
                    logger.warning(f"❌ Bad request (chat may be closed): {e}")
                    return None
                elif e.resp.status in [403, 401]:
                    logger.error(f"❌ Authentication error: {e}")
                    return None
                else:
                    logger.error(f"HTTP error fetching messages (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    return None
                
            except OSError as e:
                logger.warning(f"🔴 Network error fetching messages (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error("❌ Network error persisted after all retries")
                    return None
                
            except Exception as e:
                logger.error(f"❌ Unexpected error fetching messages (attempt {attempt + 1}/{max_retries}): {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    return None
        
        logger.error("❌ All fetch attempts failed")
        return None
    
    async def _process_message(self, message: YouTubeMessage) -> None:
        """
        Procesa un mensaje nuevo.
        
        Args:
            message: Mensaje a procesar
        """
        # Llamar a todos los handlers registrados
        for handler in self._message_handlers:
            try:
                # Si el handler es async
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.exception(f"Error in message handler {handler.__name__}: {e}")
    
    def _persist_user_handler(self, message: YouTubeMessage) -> None:
        """
        Handler interno: Persiste el usuario de YouTube en BD.
        Se registra automáticamente si enable_user_persistence=True.
        
        Args:
            message: Mensaje con información del usuario
        """
        if not UserPackager.should_persist(message):
            return
        
        try:
            # Empaquetar datos del usuario
            packed_data = UserPackager.pack_youtube(message)
            
            # Persistir en BD
            user_id, is_new = UserPackager.persist_youtube_user(packed_data, client=None)
            
            if not user_id:
                logger.warning(f"Failed to persist user from message")
                return
            
            # Log de nuevo usuario
            if is_new:
                logger.info(
                    f"✨ NEW YouTube user persisted: {packed_data['youtube_username']} "
                    f"(ID: {user_id}, Type: {packed_data['user_type']})"
                )
            
        except Exception as e:
            logger.error(f"Error persisting user: {type(e).__name__}: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del listener.
        
        Returns:
            Diccionario con estadísticas
        """
        return {
            "is_running": self.is_running,
            "live_chat_id": self.live_chat_id,
            "poll_interval_ms": self.poll_interval_ms,
            "processed_messages_count": len(self._processed_messages),
            "registered_handlers": len(self._message_handlers),
        }


# ============================================================================
# HANDLERS DE EJEMPLO
# ============================================================================

def console_message_handler(message: YouTubeMessage) -> None:
    """
    Handler de ejemplo que imprime mensajes en consola con Rich.
    """
    try:
        from backend.core import get_console
        console = get_console()
        
        # Iconos según privilegios
        icon = ""
        if message.is_owner:
            icon = "👑"
        elif message.is_moderator:
            icon = "🛡️"
        elif message.is_sponsor:
            icon = "💎"
        
        # Estilo según privilegios
        style = "bold red" if message.is_owner else "bold yellow" if message.is_moderator else "cyan"
        
        # Imprimir con formato
        console.print(
            f"[{style}]{icon} {message.author_name}[/{style}]: {message.message}"
        )
        
    except Exception as e:
        # Fallback a print simple
        print(f"{message.author_name}: {message.message}")


async def command_processor_handler(
    message: YouTubeMessage,
    client: Optional[YouTubeClient] = None,
    live_chat_id: Optional[str] = None,
) -> None:
    """
    Handler para procesar comandos del chat.
    """
    # Verificar si el mensaje comienza con un prefijo de comando
    if message.message.startswith("!"):
        command_text = message.message[1:].strip()
        parts = command_text.split()
        
        if not parts:
            return
        
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        logger.info(f"Command detected: {command} with args: {args} from {message.author_name}")

        if not client or not live_chat_id:
            logger.warning("No client/live_chat_id provided for command processing")
            return

        try:
            from .chat_commands.general_cmds import process_general_command
            await process_general_command(command, args, message, client, live_chat_id)
        except Exception as exc:
            logger.error(f"Error procesando comando de chat: {exc}")
