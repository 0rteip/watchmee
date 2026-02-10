"""
Ollama integration service for vision and reasoning.
"""

import httpx
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

    def _model_exists(self, model: str, available: List[str]) -> bool:
        """Check if model exists, handling tag variations like moondream vs moondream:latest."""
        # Exact match
        if model in available:
            return True
        
        model_base = model.split(':')[0]
        model_tag = model.split(':')[1] if ':' in model else None
        
        for avail in available:
            avail_base = avail.split(':')[0]
            avail_tag = avail.split(':')[1] if ':' in avail else None
            
            if model_base != avail_base:
                continue
            
            # Same base name: only match if one side has no tag
            # (e.g., "moondream" matches "moondream:latest")
            # Do NOT match different tags (e.g., "llama3.2:3b" vs "llama3.2:1b")
            if model_tag is None or avail_tag is None:
                return True
            if model_tag == avail_tag:
                return True
        
        return False

    async def reload_models(
        self,
        vision_model: Optional[str] = None,
        reasoning_model: Optional[str] = None
    ) -> bool:
        """
        Hot-reload models without restarting the server.
        
        Args:
            vision_model: New vision model name (None to keep current)
            reasoning_model: New reasoning model name (None to keep current)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate models exist
            available = await self.list_models()
            logger.info(f"Available models: {available}")
            
            if vision_model:
                if not self._model_exists(vision_model, available):
                    logger.warning(f"Vision model '{vision_model}' not installed")
                    logger.info(f"Available models: {', '.join(available)}")
                    return False
            
            if reasoning_model:
                if not self._model_exists(reasoning_model, available):
                    logger.warning(f"Reasoning model '{reasoning_model}' not installed")
                    logger.info(f"Available models: {', '.join(available)}")
                    return False
            
            # Update models
            if vision_model:
                old_vision = self.vision_model
                self.vision_model = vision_model
                logger.info(f"✓ Switched vision model: {old_vision} → {vision_model}")
            
            if reasoning_model:
                old_reasoning = self.reasoning_model
                self.reasoning_model = reasoning_model
                logger.info(f"✓ Switched reasoning model: {old_reasoning} → {reasoning_model}")
            
            return True
        
        except Exception as e:
            logger.error(f"Error reloading models: {e}")
            return False

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
