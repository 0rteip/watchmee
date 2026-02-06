"""
Pydantic models for API request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MicrophoneStatus(str, Enum):
    """Microphone status enum."""
    MUTED = "muted"
    UNMUTED = "unmuted"
    UNKNOWN = "unknown"


class MediaStatus(str, Enum):
    """Media playback status enum."""
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class UserStatus(str, Enum):
    """Inferred user status."""
    ACTIVE = "active"
    IN_MEETING = "in_meeting"
    IDLE = "idle"
    AWAY = "away"


class ClientMetadata(BaseModel):
    """Metadata sent with each client update."""
    window_title: str = Field(..., description="Active window title")
    class_name: str = Field(..., description="Active window class name (application name)")
    media_status: MediaStatus = Field(default=MediaStatus.UNKNOWN)
    media_info: Optional[str] = Field(default=None, description="e.g., 'Spotify - Song Name'")
    microphone_status: MicrophoneStatus = Field(default=MicrophoneStatus.UNKNOWN)
    user_status: UserStatus = Field(default=UserStatus.ACTIVE)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    compositor: Optional[str] = Field(default=None, description="Wayland compositor name")


class ContextEntry(BaseModel):
    """Single entry in the context sliding window."""
    timestamp: datetime
    window_title: str
    class_name: str
    media_status: MediaStatus
    user_status: UserStatus
    vision_summary: Optional[str] = None
    

class ContextWindow(BaseModel):
    """Sliding window of recent context."""
    entries: List[ContextEntry] = Field(default_factory=list)
    max_size: int = Field(default=10)
    
    def add_entry(self, entry: ContextEntry) -> None:
        """Add entry to window, removing oldest if full."""
        self.entries.append(entry)
        if len(self.entries) > self.max_size:
            self.entries.pop(0)
    
    def get_summary(self) -> str:
        """Get a text summary of recent context."""
        if not self.entries:
            return "No recent activity recorded."
        
        summaries = []
        for entry in self.entries[-5:]:  # Last 5 entries
            time_str = entry.timestamp.strftime("%H:%M")
            summaries.append(f"[{time_str}] {entry.class_name}-{entry.window_title}: {entry.vision_summary or 'No visual summary'}")
        
        return "\n".join(summaries)


class Persona(BaseModel):
    """AI persona configuration."""
    name: str
    short: str = Field(default="", description="Short display name for UI")
    icon: str = Field(default="󰚩", description="Nerd Font icon for UI")
    description: str
    tone: str = Field(default="helpful")
    focus_areas: List[str] = Field(default_factory=list)
    prompt_template: str


class TodoItem(BaseModel):
    """Single todo item."""
    text: str
    completed: bool = False
    priority: Optional[str] = None  # A, B, C, etc.


class FeedbackRequest(BaseModel):
    """Request model for generating feedback."""
    metadata: ClientMetadata
    image_base64: Optional[str] = Field(default=None, description="Base64 encoded image")


class FeedbackResponse(BaseModel):
    """Response model with AI feedback."""
    feedback: str
    persona_used: str
    context_summary: str
    user_status: UserStatus
    suppress_notification: bool = Field(default=False)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    ollama_connected: bool
    models_available: List[str]
