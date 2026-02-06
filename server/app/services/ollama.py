"""
Ollama integration service for vision and reasoning.
"""

import httpx
import base64
import logging
from typing import Optional, List
from app.config import get_settings

logger = logging.getLogger(__name__)


class OllamaService:
    """Service for interacting with Ollama API."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.ollama_base_url
        self.vision_model = self.settings.vision_model
        self.reasoning_model = self.settings.reasoning_model
        self.timeout = self.settings.request_timeout

    async def check_connection(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama connection check failed: {e}")
            return False

    async def list_models(self) -> List[str]:
        """List available models in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return [model["name"] for model in data.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
        return []

    async def analyze_image(
        self, image_base64: str, context: str = ""
    ) -> Optional[str]:
        """
        Analyze an image using the vision model (moondream).

        Args:
            image_base64: Base64 encoded image
            context: Additional context about what to look for

        Returns:
            Description of the image content
        """
    
        prompt = f"""
        Describe the CONTENT inside the active {context}.
        - Are there lines of code, a video, a chat, a document, or what?
        - Describe the visual mood: is it static, dynamic, colorful, dark, etc.?
        - Does it look like work or leisure?
        Describe in 1-2 sentences, be concise and specific.
        """

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.vision_model,
                        "prompt": prompt,
                        "images": [image_base64],
                        "stream": False,
                        "options": {
                            "temperature": 0.1,  # Lower = more focused
                            "num_predict": 100,
                        },
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    return result.get("response", "").strip()
                else:
                    logger.error(f"Vision analysis failed: {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"Image analysis error: {e}")
            return None

    async def generate_feedback(
        self,
        vision_summary: str,
        context_summary: str,
        todo_list: str,
        persona_prompt: str,
        user_status: str,
        app_name: str = "",
    ) -> Optional[str]:
        """
        Generate contextual feedback using the reasoning model.

        Args:
            vision_summary: What was seen on screen
            context_summary: Recent activity history
            todo_list: User's current todo items
            persona_prompt: The AI persona's prompt template
            user_status: Current user status (active, in_meeting, etc.)

        Returns:
            Generated feedback text
        """

        system_prompt = f"""
                {persona_prompt}
                
                OPERATIONAL RULES:
                1. You have the exact App Name:{app_name} and a Visual Description (see below). Use both.
                2. IF App Name says "Spotify" and Visual says "Code", they are just listening to music while working. That is fine.
                3. Keep it under 2 sentences.
                """

        user_prompt = f"""
        --- REAL-TIME METADATA ---
        VISUAL CONTENT: {vision_summary}
        USER STATUS: {user_status}
        
        --- GOALS (IF ANY) ---
        TODO LIST: 
        {todo_list if todo_list else ""}
        
        --- CONTEXT ---
        HISTORY: {context_summary}
        
        RESPONSE (Should be In Character):
        """

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"Generating feedback with {self.reasoning_model}...")
                logger.debug(
                    f"Vision summary: {vision_summary[:100] if vision_summary else 'None'}..."
                )

                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.reasoning_model,
                        "prompt": user_prompt,
                        "system": system_prompt,
                        "stream": False,
                        "options": {"temperature": 0.7, "num_predict": 100},
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    feedback = result.get("response", "").strip()
                    logger.info(
                        f"Feedback generated: {feedback[:80] if feedback else 'EMPTY'}..."
                    )
                    return feedback if feedback else None
                else:
                    logger.error(
                        f"Feedback generation failed: {response.status_code} - {response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Feedback generation error: {e}")
            return None


# Singleton instance
_ollama_service: Optional[OllamaService] = None


def get_ollama_service() -> OllamaService:
    """Get or create Ollama service instance."""
    global _ollama_service
    if _ollama_service is None:
        _ollama_service = OllamaService()
    return _ollama_service
