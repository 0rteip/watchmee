"""
Client configuration using Pydantic Settings.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from pathlib import Path


class ClientSettings(BaseSettings):
    """Client configuration settings."""
    
    # Server connection
    server_url: str = Field(
        default="https://localhost:8443",
        description="Server URL (HTTPS)"
    )
    api_key: str = Field(..., description="API key for server authentication")
    
    # SSL/TLS
    verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificate (set False for self-signed)"
    )
    ca_cert_path: str = Field(
        default="",
        description="Path to CA certificate for self-signed certs"
    )
    
    # Capture settings
    capture_interval: int = Field(
        default=60,
        description="Seconds between captures"
    )
    max_image_width: int = Field(
        default=1024,
        description="Maximum image width (for compression)"
    )
    jpeg_quality: int = Field(
        default=75,
        description="JPEG compression quality (1-100)"
    )
    
    # Behavior
    idle_threshold: int = Field(
        default=300,
        description="Seconds of inactivity before pausing captures"
    )
    suppress_when_meeting: bool = Field(
        default=True,
        description="Suppress notifications when mic is unmuted"
    )
    
    # Notifications
    show_notifications: bool = Field(
        default=True,
        description="Show desktop notifications"
    )
    notification_timeout: int = Field(
        default=5000,
        description="Notification timeout in milliseconds"
    )
    
    # Request timeout (for slow CPU inference)
    request_timeout: int = Field(
        default=300,
        description="HTTP request timeout in seconds"
    )
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: str = Field(default="", description="Log file path (empty for stdout)")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "COMPANION_"
        case_sensitive = False


@lru_cache()
def get_client_settings() -> ClientSettings:
    """Get cached client settings instance."""
    return ClientSettings()
