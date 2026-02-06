"""
Security utilities - API key authentication.
"""
import secrets
import logging
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from app.config import get_settings

logger = logging.getLogger(__name__)

# API Key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Verify the API key from request header.
    
    Args:
        api_key: API key from X-API-Key header
        
    Returns:
        The validated API key
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not api_key:
        logger.warning("Missing API key in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "API-Key"}
        )
    
    settings = get_settings()
    
    # Use secrets.compare_digest to prevent timing attacks
    if not secrets.compare_digest(api_key, settings.api_key):
        logger.warning("Invalid API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "API-Key"}
        )
    
    return api_key


def generate_api_key(length: int = 32) -> str:
    """Generate a secure random API key."""
    return secrets.token_urlsafe(length)
