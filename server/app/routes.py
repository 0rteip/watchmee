"""
API routes for the companion server.
"""

import base64
import logging
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException

from app.models import ClientMetadata, FeedbackResponse, HealthResponse, UserStatus
from app.security import verify_api_key
from app.services.ollama import get_ollama_service
from app.services.context import get_context_manager
from app import __version__

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint - no authentication required.
    Returns server status and Ollama connectivity.
    """
    ollama = get_ollama_service()
    connected = await ollama.check_connection()
    models = await ollama.list_models() if connected else []

    return HealthResponse(
        status="healthy" if connected else "degraded",
        version=__version__,
        ollama_connected=connected,
        models_available=models,
    )


@router.post("/analyze", response_model=FeedbackResponse)
async def analyze_activity(
    metadata: str = Form(..., description="JSON-encoded ClientMetadata"),
    image: UploadFile = File(None, description="Screenshot image (optional)"),
    _: str = Depends(verify_api_key),
):
    """
    Main endpoint for analyzing user activity.

    Accepts a screenshot and metadata, analyzes with vision model,
    maintains context window, and generates feedback.
    """
    import json

    # Parse metadata
    try:
        meta_dict = json.loads(metadata)
        client_metadata = ClientMetadata(**meta_dict)
    except Exception as e:
        logger.error(f"Invalid metadata: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid metadata: {str(e)}")

    # Get services
    ollama = get_ollama_service()
    context_mgr = await get_context_manager()

    # Determine if we should suppress notifications
    suppress_notification = client_metadata.user_status == UserStatus.IN_MEETING

    # Process image if provided
    vision_summary = None
    if image and image.size > 0:
        try:
            image_data = await image.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # Analyze with vision model
            vision_summary = await ollama.analyze_image(
                image_base64,
                context=f"window: {client_metadata.window_title}, whose application name is {client_metadata.class_name}",
            )
            logger.info(
                f"Vision analysis complete: {vision_summary if vision_summary else 'None'}..."
            )
        except Exception as e:
            logger.error(f"Image processing error: {e}")
            vision_summary = f"Could not analyze image: {str(e)}"
    else:
        vision_summary = f"User is in: {client_metadata.window_title}"

    # Add to context window
    context_mgr.add_context_entry(
        window_title=client_metadata.window_title,
        class_name=client_metadata.class_name,
        media_status=client_metadata.media_status,
        user_status=client_metadata.user_status,
        vision_summary=vision_summary,
    )

    # Get context and todos
    context_summary = context_mgr.get_context_summary()
    todo_text = context_mgr.get_todos_text()
    persona_prompt = context_mgr.get_persona_prompt()

    # Generate feedback only after enough captures (or if in meeting, suppress)
    feedback = ""
    should_generate = context_mgr.should_generate_feedback()

    if suppress_notification:
        feedback = "[Notification suppressed - user in meeting]"
    elif not should_generate:
        # Not enough context yet, return empty feedback
        remaining = context_mgr.captures_before_feedback - context_mgr.capture_count
        feedback = ""
        logger.info(f"Accumulating context... {remaining} captures until feedback")
    else:
        # Generate feedback and reset counter
        feedback = (
            await ollama.generate_feedback(
                vision_summary=vision_summary or "No visual data",
                context_summary=context_summary,
                todo_list=todo_text,
                persona_prompt=persona_prompt,
                user_status=client_metadata.user_status.value,
                app_name=f"{client_metadata.class_name} ({client_metadata.window_title})",
            )
            or "Keep up the good work!"
        )
        context_mgr.reset_capture_count()

    return FeedbackResponse(
        feedback=feedback,
        persona_used=context_mgr.active_persona.name
        if context_mgr.active_persona
        else "Default",
        context_summary=context_summary,
        user_status=client_metadata.user_status,
        suppress_notification=suppress_notification or not should_generate,
    )


@router.get("/context")
async def get_current_context(_: str = Depends(verify_api_key)):
    """Get the current context window contents."""
    context_mgr = await get_context_manager()

    return {
        "entries": [
            {
                "timestamp": e.timestamp.isoformat(),
                "window_title": e.window_title,
                "class_name": e.class_name,
                "media_status": e.media_status.value,
                "user_status": e.user_status.value,
                "vision_summary": e.vision_summary,
            }
            for e in context_mgr.context_window.entries
        ],
        "capture_count": context_mgr.capture_count,
        "captures_before_feedback": context_mgr.captures_before_feedback,
        "captures_remaining": max(
            0, context_mgr.captures_before_feedback - context_mgr.capture_count
        ),
        "todos": context_mgr.get_todos_text(),
        "active_persona": context_mgr.active_persona.name
        if context_mgr.active_persona
        else None,
    }


@router.get("/personas")
async def list_personas(_: str = Depends(verify_api_key)):
    """List available personas."""
    context_mgr = await get_context_manager()

    return {
        "personas": [
            {
                "name": p.name,
                "short": p.short or p.name[:6],
                "icon": p.icon or "󰚩",
                "description": p.description,
                "tone": p.tone,
                "focus_areas": p.focus_areas,
            }
            for p in context_mgr.personas
        ],
        "active": context_mgr.active_persona.name
        if context_mgr.active_persona
        else None,
    }


@router.post("/personas/{name}/activate")
async def activate_persona(name: str, _: str = Depends(verify_api_key)):
    """Activate a specific persona."""
    context_mgr = await get_context_manager()

    if context_mgr.set_active_persona(name):
        return {"status": "success", "active_persona": name}
    else:
        raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")


@router.post("/todos/reload")
async def reload_todos(_: str = Depends(verify_api_key)):
    """Reload the todo.txt file."""
    context_mgr = await get_context_manager()
    await context_mgr.load_todos()

    return {
        "status": "success",
        "todos_count": len(context_mgr.todo_items),
        "todos": context_mgr.get_todos_text(),
    }
