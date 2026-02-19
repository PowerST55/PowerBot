"""
HTTP Adapter personalizado usando requests para reemplazar httplib2.
Proporciona mejor manejo de SSL y evita memory corruption en VPS.
"""

import logging
import ssl
import certifi
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.ssl_ import create_urllib3_context

logger = logging.getLogger(__name__)


class CustomSSLContext(HTTPAdapter):
    """
    HTTPAdapter con contexto SSL personalizado para mejor manejo de errores.
    Evita problemas de memory corruption causados por interacciones con httplib2.
    """

    def init_poolmanager(self, *args, **kwargs):
        """Inicializa el pool manager con contexto SSL mejorado."""
        ctx = create_urllib3_context()
        
        # Configurar contexto SSL para mejor compatibilidad
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        
        # Usar certificados de confianza de certifi
        ctx.load_verify_locations(certifi.where())
        
        # Permitir versiones TLS modernas
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


def create_requests_session(
    retries: int = 3,
    backoff_factor: float = 0.5,
    timeout: float = 10.0,
    verify_ssl: bool = True,
) -> requests.Session:
    """
    Crea una sesión de requests con reintentos y mejor manejo de SSL.
    
    Args:
        retries: Número de reintentos
        backoff_factor: Factor de backoff exponencial
        timeout: Timeout por defecto en segundos
        verify_ssl: Si se debe verificar SSL (False solo para dev/testing)
    
    Returns:
        Sesión configurada de requests
    """
    session = requests.Session()
    
    # Configurar reintentos con backoff exponencial
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["GET", "POST", "PUT", "DELETE", "HEAD"],
        raise_on_status=False,
    )
    
    # Usar adapter personalizado con SSL mejorado
    adapter = CustomSSLContext(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    # Configurar certificados
    if verify_ssl:
        session.verify = certifi.where()
    else:
        session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Headers por defecto
    session.headers.update({
        "User-Agent": "PowerBot/1.0 (requests)",
    })
    
    return session


class RequestsHTTPAdapter:
    """
    Adaptador que proporciona una interfaz compatible con google-api-python-client
    usando requests en lugar de httplib2. Esto evita memory corruption en VPS.
    """

    def __init__(
        self,
        timeout: float = 10.0,
        retries: int = 3,
        verify_ssl: bool = True,
    ):
        """
        Inicializa el adaptador.
        
        Args:
            timeout: Timeout por defecto para solicitudes
            retries: Número de reintentos
            verify_ssl: Si se debe verificar SSL
        """
        self.session = create_requests_session(
            retries=retries,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )
        self.timeout = timeout
        self.verify_ssl = verify_ssl

    def request(
        self,
        method: str,
        url: str,
        body: Optional[str] = None,
        headers: Optional[dict] = None,
        **kwargs
    ) -> Tuple[dict, bytes]:
        """
        Realiza una solicitud HTTP compatible con httplib2.
        
        Args:
            method: Método HTTP (GET, POST, etc.)
            url: URL de la solicitud
            body: Cuerpo de la solicitud
            headers: Headers de la solicitud
            **kwargs: Argumentos adicionales
        
        Returns:
            Tupla (headers_dict, content_bytes)
        
        Raises:
            OSError: Si hay error de SSL o conexión
        """
        try:
            # Realizar la solicitud
            response = self.session.request(
                method=method,
                url=url,
                data=body,
                headers=headers or {},
                timeout=self.timeout,
                **kwargs
            )

            # Convertir a formato compatible con httplib2
            response_headers = dict(response.headers)
            response_headers["status"] = str(response.status_code)

            return response_headers, response.content

        except requests.exceptions.SSLError as e:
            logger.warning(f"SSL error in request: {e}")
            # Re-lanzar como ssl.SSLError para compatibilidad
            raise ssl.SSLError(f"SSL error: {e}") from e
        except requests.exceptions.Timeout as e:
            logger.warning(f"Timeout in request: {e}")
            raise OSError(f"Timeout: {e}") from e
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connection error in request: {e}")
            raise OSError(f"Connection error: {e}") from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            raise OSError(f"Request error: {e}") from e

    def close(self):
        """Cierra la sesión."""
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# Exportar para uso en youtube_core
__all__ = [
    "RequestsHTTPAdapter",
    "create_requests_session",
    "CustomSSLContext",
]
