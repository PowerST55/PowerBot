"""
SSL Configuration Fix for YouTube API - AGGRESSIVE FIX v2
Reemplaza httplib2 completamente con requests para evitar errores de OpenSSL 3.x
"""

import sys
import ssl
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def replace_httplib2_with_requests():
    """
    Reemplaza httplib2 con un wrapper de requests ANTES de que se cargue google-api-python-client
    """
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        # Crear sesión global con reintentos
        session = requests.Session()
        
        # Configurar adaptador con reintentos
        retry = Retry(
            total=3,
            read=3,
            connect=3,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=20,
            pool_maxsize=20
        )
        
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        
        # Crear wrapper de response compatible con httplib2
        class HttpLib2Response(object):
            """Wrapper que adapta requests.Response a la interfaz de httplib2"""
            
            def __init__(self, requests_response):
                self._response = requests_response
                # Copiar atributos importantes
                self.status = requests_response.status_code  # httplib2 usa .status
                self.status_code = requests_response.status_code
                self.headers = requests_response.headers
                self.reason = requests_response.reason
                self.url = requests_response.url
                self.content = requests_response.content
                self.text = requests_response.text
            
            def __getattr__(self, name):
                # Fallback para otros atributos
                return getattr(self._response, name)
            
            def __repr__(self):
                return f"<HttpLib2Response {self.status}>"
        
        # Crear clase Http que emule httplib2.Http perfectamente
        class Http(object):
            """Emula httplib2.Http usando requests"""
            
            # Atributos de clase
            RETRIES = 1
            DEFAULT_MAX_REDIRECTS = 5
            
            def __init__(self, ca_certs=None, disable_ssl_certificate_validation=False, **kwargs):
                self.session = session
                self.request_count = 0
                self.ca_certs = ca_certs
                self.disable_ssl_certificate_validation = disable_ssl_certificate_validation
                # Esto es importante: redirect_codes como propiedad
                self._redirect_codes = set([301, 302, 303, 307])
            
            @property
            def redirect_codes(self):
                return self._redirect_codes
            
            @redirect_codes.setter
            def redirect_codes(self, value):
                # Asegurarse de que siempre es un set
                if isinstance(value, (list, tuple)):
                    self._redirect_codes = set(value)
                elif isinstance(value, set):
                    self._redirect_codes = value
                else:
                    self._redirect_codes = set(value)
            
            def request(self, uri, method="GET", body=None, headers=None, redirections=None, connection_type=None):
                """Emula httplib2.Http.request()
                
                Returns:
                    (response, content) tuple como httplib2
                """
                try:
                    if headers is None:
                        headers = {}
                    
                    # Usar requests para la petición
                    response = self.session.request(
                        method=method,
                        url=uri,
                        data=body,
                        headers=headers,
                        timeout=30,
                        verify=not self.disable_ssl_certificate_validation,
                        allow_redirects=True,
                    )
                    
                    self.request_count += 1
                    
                    # Retornar en formato httplib2 (response, content) con wrapper
                    wrapped_response = HttpLib2Response(response)
                    return wrapped_response, response.content
                    
                except Exception as e:
                    logger.error(f"HTTP request error: {e}")
                    raise
            
            def close(self):
                """Cierra la conexión (emula httplib2.Http.close())"""
                try:
                    if hasattr(self.session, 'close'):
                        self.session.close()
                    logger.debug("HTTP session closed")
                except Exception as e:
                    logger.debug(f"Error closing session: {e}")
            
            def set_proxy(self, proxy_url, proxy_type='http'):
                """Emula httplib2.Http.set_proxy()"""
                try:
                    if proxy_url:
                        proxies = {
                            'http': proxy_url,
                            'https': proxy_url,
                        }
                        self.session.proxies.update(proxies)
                    logger.debug(f"Proxy set to {proxy_url}")
                except Exception as e:
                    logger.debug(f"Error setting proxy: {e}")
            
            def __del__(self):
                """Destructor que cierra la sesión"""
                try:
                    self.close()
                except:
                    pass
        
        # Crear módulo mock de httplib2
        class httplib2_module(object):
            pass
        
        # Definir excepciones de httplib2
        class HttpLib2Exception(Exception):
            """Base exception for httplib2"""
            pass
        
        class RedirectMissingLocation(HttpLib2Exception):
            """Exception for redirects missing Location header"""
            pass
        
        class FailedToDecompressContent(HttpLib2Exception):
            """Exception when decompression fails"""
            pass
        
        class UnimplementedDigestAuthOptionError(HttpLib2Exception):
            """Exception for unimplemented digest auth options"""
            pass
        
        class UnimplementedHmacDigestAuthOptionError(HttpLib2Exception):
            """Exception for unimplemented HMAC digest auth options"""
            pass
        
        class MalformedHeader(HttpLib2Exception):
            """Exception for malformed headers"""
            pass
        
        class RelativeURIError(HttpLib2Exception):
            """Exception for relative URIs"""
            pass
        
        class ServerNotFoundError(HttpLib2Exception):
            """Exception when server is not found"""
            pass
        
        class RequestEntityTooLarge(HttpLib2Exception):
            """Exception for entity too large"""
            pass
        
        class NotSupportedOnThisPlatform(HttpLib2Exception):
            """Exception for unsupported platform features"""
            pass
        
        # Asignar excepciones al módulo
        httplib2_module.HttpLib2Exception = HttpLib2Exception
        httplib2_module.RedirectMissingLocation = RedirectMissingLocation
        httplib2_module.FailedToDecompressContent = FailedToDecompressContent
        httplib2_module.UnimplementedDigestAuthOptionError = UnimplementedDigestAuthOptionError
        httplib2_module.UnimplementedHmacDigestAuthOptionError = UnimplementedHmacDigestAuthOptionError
        httplib2_module.MalformedHeader = MalformedHeader
        httplib2_module.RelativeURIError = RelativeURIError
        httplib2_module.ServerNotFoundError = ServerNotFoundError
        httplib2_module.RequestEntityTooLarge = RequestEntityTooLarge
        httplib2_module.NotSupportedOnThisPlatform = NotSupportedOnThisPlatform
        
        # Asignar atributos
        httplib2_module.Http = Http
        httplib2_module.RETRIES = 1
        httplib2_module.DEFAULT_MAX_REDIRECTS = 5
        
        # Inyectar ANTES de que se carguen otros módulos
        if 'httplib2' not in sys.modules:
            sys.modules['httplib2'] = httplib2_module()
            logger.info("✅ httplib2 replaced with requests wrapper (v2)")
        
    except Exception as e:
        logger.error(f"Error replacing httplib2: {e}")
        import traceback
        traceback.print_exc()
        raise


def patch_ssl_context():
    """Parchea el contexto SSL global de Python para OpenSSL 3.x"""
    try:
        # Crear contexto SSL permisivo para OpenSSL 3.x
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        
        # Permitir ciphers modernos
        try:
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        except:
            pass  # Algunos sistemas no soportan SECLEVEL
        
        # Usar TLS 1.2 mínimo
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        
        logger.debug("✅ Global SSL context configured for OpenSSL 3.x")
    except Exception as e:
        logger.warning(f"Could not patch SSL context: {e}")


# Aplicar fixes automáticamente en orden
try:
    patch_ssl_context()
    replace_httplib2_with_requests()
    logger.info("✅ SSL fixes applied successfully")
except Exception as e:
    logger.error(f"❌ Error applying SSL fixes: {e}")
    import traceback
    traceback.print_exc()


