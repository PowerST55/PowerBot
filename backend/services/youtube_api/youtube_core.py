"""
YouTube API Core Module
Manages authentication and provides a clean client interface for YouTube interactions.
SSL configuration handled by ssl_fix.py to avoid OpenSSL 3.x compatibility issues.
"""

import os
import json
import logging
import ssl
from pathlib import Path
from typing import Optional

# FIX: Apply SSL patches for OpenSSL 3.x compatibility BEFORE any other imports
from . import ssl_fix  # noqa: F401

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# Configure logging
logger = logging.getLogger(__name__)


class YouTubeConfig:
    """Configuration for YouTube API connections."""

    SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

    def __init__(self, keys_dir: Optional[str] = None):
        """
        Initialize YouTube configuration.

        Args:
            keys_dir: Path to keys directory. Defaults to backend/keys relative to this file.
        """
        if keys_dir is None:
            # Get the backend directory relative to this file
            current_dir = Path(__file__).parent.parent.parent
            keys_dir = current_dir / "keys"
        else:
            keys_dir = Path(keys_dir)

        self.keys_dir = keys_dir
        self.credentials_path = keys_dir / "credentials.json"
        self.token_path = keys_dir / "ytkey.json"

    def validate(self) -> bool:
        """Validate that required files exist."""
        if not self.keys_dir.exists():
            logger.error(f"Keys directory not found: {self.keys_dir}")
            return False

        if not self.credentials_path.exists():
            logger.error(f"Credentials file not found: {self.credentials_path}")
            return False

        return True


class YouTubeAuthenticator:
    """Handles YouTube API authentication."""

    def __init__(self, config: YouTubeConfig):
        """
        Initialize authenticator with configuration.

        Args:
            config: YouTubeConfig instance.
        """
        self.config = config

    def authenticate(self) -> Optional[Credentials]:
        """
        Authenticate with YouTube API.

        Returns:
            Credentials object or None if authentication fails.
        """
        try:
            creds = None

            # Try to load existing token
            if self.config.token_path.exists():
                creds = Credentials.from_authorized_user_file(
                    str(self.config.token_path), self.config.SCOPES
                )
                logger.info("Loaded existing YouTube credentials from token file")

            # Check if credentials are valid or need refresh
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    logger.info("Refreshed YouTube credentials")
                else:
                    # Perform OAuth flow
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.config.credentials_path), self.config.SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                    logger.info("Completed YouTube OAuth flow")

                # Save the token for future use
                self._save_token(creds)

            return creds

        except FileNotFoundError as e:
            logger.error(f"Credentials file not found: {e}")
            return None
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None

    def _save_token(self, creds: Credentials) -> None:
        """
        Save credentials token to file.

        Args:
            creds: Credentials object to save.
        """
        try:
            with open(self.config.token_path, "w") as token_file:
                token_file.write(creds.to_json())
            logger.info(f"Saved YouTube token to {self.config.token_path}")
        except Exception as e:
            logger.error(f"Error saving token: {e}")


class YouTubeClient:
    """Clean interface for YouTube API interactions."""

    def __init__(self, credentials: Credentials):
        """
        Initialize YouTube client with credentials.

        Args:
            credentials: Authenticated Credentials object.
        """
        self.credentials = credentials
        
        # FIX: SSL configuration is handled by ssl_fix.py
        # The googleapiclient.discovery.build() will use the patched SSL context
        self.service = build("youtube", "v3", credentials=credentials)
        logger.info("YouTube API client initialized successfully")

    def get_active_live_chat_id(self) -> Optional[str]:
        """
        Get the live chat ID from the active broadcast.

        Returns:
            Live chat ID or None if no active broadcast found.
        """
        try:
            request = self.service.liveBroadcasts().list(
                part="snippet", broadcastStatus="active"
            )
            response = request.execute()

            if response.get("items") and response["items"][0].get("snippet"):
                live_chat_id = response["items"][0]["snippet"].get("liveChatId")
                logger.debug("Found active live chat ID")
                return live_chat_id

            logger.warning("No active broadcast found")
            return None

        except HttpError as e:
            logger.error(f"HTTP error getting live chat ID: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting live chat ID: {e}")
            return None

    def send_message(self, live_chat_id: str, message: str) -> Optional[dict]:
        """
        Send a message to a live chat (single attempt, no retries).
        Retries are handled at a higher level in send_message.py.

        Args:
            live_chat_id: The live chat ID.
            message: The message text to send.

        Returns:
            Response dict with message ID if successful, or error info dict.
        """
        try:
            response = self.service.liveChatMessages().insert(
                part="snippet",
                body={
                    "snippet": {
                        "liveChatId": live_chat_id,
                        "type": "textMessageEvent",
                        "textMessageDetails": {"messageText": message},
                    }
                },
            ).execute()

            if response and response.get("id"):
                logger.debug("✅ Message sent to live chat")
                return response
            logger.warning("Message send returned empty response")
            return {"empty_response": True}

        except ssl.SSLError as e:
            # SSL error: don't retry here, let higher level handle it
            logger.warning(f"🔴 SSL error in send_message: {e}")
            return {"ssl_error": True, "message": str(e)}
            
        except HttpError as e:
            if "quotaExceeded" in str(e):
                logger.warning("⚠️  YouTube API quota exceeded")
                return {"quota_error": True}
            elif "403" in str(e):
                logger.error(f"❌ Access forbidden - check permissions: {e}")
                return {"permission_error": True}
            else:
                logger.error(f"❌ HTTP error sending message: {e}")
                return {"http_error": True}
        except OSError as e:
            # Network errors
            logger.warning(f"🔴 Network error sending message: {e}")
            return {"network_error": True, "message": str(e)}
        except Exception as e:
            logger.error(f"❌ Unexpected error sending message: {type(e).__name__}: {e}")
            return {"unexpected_error": True}


class YouTubeAPI:
    """Main interface for YouTube API functionality."""

    def __init__(self, keys_dir: Optional[str] = None):
        """
        Initialize YouTube API with credentials management.

        Args:
            keys_dir: Path to keys directory. Defaults to backend/keys.

        Raises:
            ValueError: If configuration is invalid.
        """
        self.config = YouTubeConfig(keys_dir)

        if not self.config.validate():
            raise ValueError("Invalid YouTube API configuration")

        self.authenticator = YouTubeAuthenticator(self.config)
        self.client: Optional[YouTubeClient] = None

    def connect(self) -> bool:
        """
        Authenticate and establish connection to YouTube API.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            credentials = self.authenticator.authenticate()
            if credentials is None:
                logger.error("Failed to authenticate with YouTube API")
                return False

            self.client = YouTubeClient(credentials)
            logger.info("Successfully connected to YouTube API")
            return True

        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def is_connected(self) -> bool:
        """Check if connected to YouTube API."""
        return self.client is not None

    def disconnect(self) -> None:
        """Disconnect from YouTube API."""
        self.client = None
        logger.info("Disconnected from YouTube API")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False


# Convenience functions for simple use cases

_api_instance: Optional[YouTubeAPI] = None


def initialize_youtube_api(keys_dir: Optional[str] = None) -> YouTubeAPI:
    """
    Initialize and connect to YouTube API (singleton pattern).

    Args:
        keys_dir: Path to keys directory.

    Returns:
        Connected YouTubeAPI instance.
    """
    global _api_instance
    _api_instance = YouTubeAPI(keys_dir)
    _api_instance.connect()
    return _api_instance


def get_youtube_api() -> Optional[YouTubeAPI]:
    """Get the global YouTube API instance."""
    return _api_instance


if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.INFO)
    
    print("✓ YouTube API Core module loaded successfully")
    print("\nUsage:")
    print("  from backend.services.youtube_api import YouTubeAPI")
    print("  with YouTubeAPI() as youtube:")
    print("      live_chat_id = youtube.client.get_active_live_chat_id()")
    print("      youtube.client.send_message(live_chat_id, 'Message')")
