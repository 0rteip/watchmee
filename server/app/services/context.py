"""
Context management service - handles sliding window and state.
"""
import json
import logging
import aiofiles
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from app.models import (
    ContextWindow, ContextEntry, Persona, TodoItem,
    MediaStatus, UserStatus
)
from app.config import get_settings

logger = logging.getLogger(__name__)


class ContextManager:
    """Manages the sliding context window and user data."""
    
    def __init__(self):
        self.settings = get_settings()
        self.context_window = ContextWindow(max_size=self.settings.context_window_size)
        self.personas: List[Persona] = []
        self.active_persona: Optional[Persona] = None
        self.todo_items: List[TodoItem] = []
        self.capture_count: int = 0
        self.captures_before_feedback: int = self.settings.captures_before_feedback
        
    async def initialize(self) -> None:
        """Load personas and todo items on startup."""
        await self.load_personas()
        await self.load_todos()
    
    async def load_personas(self) -> None:
        """Load personas from JSON file."""
        personas_path = Path(self.settings.personas_file_path)
        
        if not personas_path.exists():
            logger.warning(f"Personas file not found: {personas_path}")
            self._set_default_persona()
            return
        
        try:
            async with aiofiles.open(personas_path, 'r') as f:
                content = await f.read()
                data = json.loads(content)
                
            self.personas = [Persona(**p) for p in data.get("personas", [])]
            
            # Set active persona (first one or default)
            default_name = data.get("default", "")
            self.active_persona = next(
                (p for p in self.personas if p.name == default_name),
                self.personas[0] if self.personas else None
            )
            
            if not self.active_persona:
                self._set_default_persona()
                
            logger.info(f"Loaded {len(self.personas)} personas, active: {self.active_persona.name}")
            
        except Exception as e:
            logger.error(f"Error loading personas: {e}")
            self._set_default_persona()
    
    def _set_default_persona(self) -> None:
        """Set a default persona if none loaded."""
        self.active_persona = Persona(
            name="Assistant",
            description="A helpful productivity assistant",
            tone="friendly",
            focus_areas=["productivity", "focus"],
            prompt_template="You are a helpful, friendly productivity assistant. Your goal is to help the user stay focused and productive without being intrusive."
        )
        self.personas = [self.active_persona]
    
    async def load_todos(self) -> None:
        """Load todos from todo.txt file (todo.txt format)."""
        todo_path = Path(self.settings.todo_file_path)
        
        if not todo_path.exists():
            logger.warning(f"Todo file not found: {todo_path}")
            self.todo_items = []
            return
        
        try:
            async with aiofiles.open(todo_path, 'r') as f:
                content = await f.read()
            
            self.todo_items = []
            for line in content.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                completed = line.startswith('x ')
                if completed:
                    line = line[2:]
                
                # Check for priority (A), (B), etc.
                priority = None
                if line.startswith('(') and len(line) > 2 and line[2] == ')':
                    priority = line[1]
                    line = line[4:].strip()
                
                self.todo_items.append(TodoItem(
                    text=line,
                    completed=completed,
                    priority=priority
                ))
            
            logger.info(f"Loaded {len(self.todo_items)} todo items")
            
        except Exception as e:
            logger.error(f"Error loading todos: {e}")
            self.todo_items = []
    
    def get_todos_text(self) -> str:
        """Get formatted todo list as text."""
        if not self.todo_items:
            return "No todos defined."
        
        lines = []
        for item in self.todo_items:
            if item.completed:
                continue
            prefix = f"({item.priority}) " if item.priority else ""
            lines.append(f"- {prefix}{item.text}")
        
        return "\n".join(lines) if lines else "All todos completed!"
    
    def add_context_entry(
        self,
        window_title: str,
        class_name: str,
        media_status: MediaStatus,
        user_status: UserStatus,
        vision_summary: Optional[str] = None,
    ) -> None:
        """Add a new entry to the context window."""
        entry = ContextEntry(
            timestamp=datetime.utcnow(),
            window_title=window_title,
            class_name=class_name,
            media_status=media_status,
            user_status=user_status,
            vision_summary=vision_summary
        )
        self.context_window.add_entry(entry)
        self.capture_count += 1
        logger.debug(f"Added context entry: {window_title} (capture {self.capture_count})")
    
    def should_generate_feedback(self) -> bool:
        """Check if enough captures have accumulated to generate feedback."""
        return self.capture_count >= self.captures_before_feedback
    
    def reset_capture_count(self) -> None:
        """Reset capture counter after generating feedback."""
        self.capture_count = 0
    
    def get_context_summary(self) -> str:
        """Get summary of recent context."""
        return self.context_window.get_summary()
    
    def get_persona_prompt(self) -> str:
        """Get the active persona's prompt template."""
        if self.active_persona:
            return self.active_persona.prompt_template
        return "You are a helpful assistant."
    
    def set_active_persona(self, name: str) -> bool:
        """Set active persona by name."""
        persona = next((p for p in self.personas if p.name == name), None)
        if persona:
            self.active_persona = persona
            logger.info(f"Switched to persona: {name}")
            return True
        return False
    
    def get_personas_list(self) -> List[str]:
        """Get list of available persona names."""
        return [p.name for p in self.personas]


# Singleton instance
_context_manager: Optional[ContextManager] = None


async def get_context_manager() -> ContextManager:
    """Get or create context manager instance."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
        await _context_manager.initialize()
    return _context_manager
