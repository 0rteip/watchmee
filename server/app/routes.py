"""
API routes for the companion server.
"""

import base64
import json
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException

from app.models import ClientMetadata, FeedbackResponse, HealthResponse, UserStatus, ModelsResponse, SwitchModelRequest, SwitchModelResponse
from app.config import get_settings
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


@router.get("/models", response_model=ModelsResponse)
async def get_models(_: str = Depends(verify_api_key)):
    """
    Get current model configuration and available options.
    """
    ollama = get_ollama_service()
    
    # Load model profiles
    profiles_path = Path("/app/config/model-profiles.json")
    profiles_data = {}
    if profiles_path.exists():
        with open(profiles_path) as f:
            data = json.load(f)
            profiles_data = data.get("profiles", {})
    
    # Get installed models
    installed = await ollama.list_models()
    
    # Read current models from the service instance (not cached settings)
    return ModelsResponse(
        current_vision=ollama.vision_model,
        current_reasoning=ollama.reasoning_model,
        available_profiles=profiles_data,
        installed_models=installed,
    )


@router.post("/models/switch", response_model=SwitchModelResponse)
async def switch_models(
    request: SwitchModelRequest,
    _: str = Depends(verify_api_key)
):
    """
    Switch models at runtime without restarting the server.
    Can switch by profile or specify individual models.
    """
    ollama = get_ollama_service()
    new_vision = None
    new_reasoning = None
    
    # Validate: must specify either a profile or at least one model
    if not request.profile and not request.vision_model and not request.reasoning_model:
        raise HTTPException(
            status_code=400,
            detail="Must specify 'profile' or at least one of 'vision_model'/'reasoning_model'"
        )
    
    try:
        # If profile specified, load from config
        if request.profile:
            profiles_path = Path("/app/config/model-profiles.json")
            if not profiles_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail="Model profiles configuration not found"
                )
            
            with open(profiles_path) as f:
                data = json.load(f)
                profiles = data.get("profiles", {})
                
                if request.profile not in profiles:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Profile '{request.profile}' not found"
                    )
                
                profile = profiles[request.profile]
                new_vision = profile["vision_model"]
                new_reasoning = profile["reasoning_model"]
        else:
            # Use individual model specifications
            new_vision = request.vision_model
            new_reasoning = request.reasoning_model
        
        # Apply changes using hot-reload
        result = await ollama.reload_models(
            vision_model=new_vision,
            reasoning_model=new_reasoning
        )
        
        if result:
            return SwitchModelResponse(
                success=True,
                message="Models switched successfully",
                new_vision=new_vision or ollama.vision_model,
                new_reasoning=new_reasoning or ollama.reasoning_model,
            )
        else:
            return SwitchModelResponse(
                success=False,
                message="Failed to switch models - check if models are installed",
                new_vision=ollama.vision_model,
                new_reasoning=ollama.reasoning_model,
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching models: {e}")
        return SwitchModelResponse(
            success=False,
            message=f"Error: {str(e)}",
            new_vision=ollama.vision_model,
            new_reasoning=ollama.reasoning_model,
        )


@router.post("/models/pull/{model_name}")
async def pull_model(model_name: str, _: str = Depends(verify_api_key)):
    """
    Trigger pulling a model from Ollama registry.
    This is async and may take a while depending on model size.
    """
    settings = get_settings()
    
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/pull",
                json={"name": model_name, "stream": False}
            )
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "message": f"Model '{model_name}' pulled successfully"
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to pull model: {response.text}"
                }
    except Exception as e:
        logger.error(f"Error pulling model: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error pulling model: {str(e)}"
        )
