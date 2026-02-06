"""
Server configuration using Pydantic Settings.
Loads from environment variables and .env file.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8443, description="Server port")
    debug: bool = Field(default=False, description="Debug mode")
    
    # Security
    api_key: str = Field(..., description="API key for authentication")
    ssl_certfile: str = Field(default="/app/certs/server.crt", description="SSL certificate path")
    ssl_keyfile: str = Field(default="/app/certs/server.key", description="SSL private key path")
    
    # Ollama
    ollama_base_url: str = Field(default="http://ollama:11434", description="Ollama API base URL")
    vision_model: str = Field(default="moondream", description="Vision model for image analysis")
    reasoning_model: str = Field(default="llama3", description="Reasoning model for feedback")
    
    # Context
    context_window_size: int = Field(default=10, description="Sliding window size for context")
    captures_before_feedback: int = Field(default=5, description="Number of captures before generating feedback")
    todo_file_path: str = Field(default="/app/config/todo.txt", description="Path to todo.txt file")
    personas_file_path: str = Field(default="/app/config/personas.json", description="Path to personas.json")
    
    # Performance
    max_image_width: int = Field(default=1024, description="Maximum image width")
    request_timeout: float = Field(default=180.0, description="Request timeout in seconds")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
