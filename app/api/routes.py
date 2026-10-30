"""API Router Definitions for Sana'a AI."""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ResetSessionRequest,
    ResetSessionResponse,
)
from app.config import Settings, get_settings
from app.core.memory import BaseSessionStorage, get_session_storage
from app.services.chat_service import ChatService
from app.services.llm_service import GeminiLLMService, get_llm_service

router = APIRouter()


def get_chat_service(
    settings: Settings = Depends(get_settings),
    storage: BaseSessionStorage = Depends(get_session_storage),
) -> ChatService:
    """Dependency injection provider for ChatService."""
    llm = get_llm_service(settings)
    return ChatService(llm_service=llm, session_storage=storage, settings=settings)


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health and configuration check",
)
def health_check(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Check service health and whether the LLM API key is configured."""
    llm = get_llm_service(settings)
    is_configured = getattr(llm, "is_configured", False)

    return HealthResponse(
        status="healthy",
        version="0.1.0",
        llm_provider=settings.LLM_PROVIDER,
        model=settings.GEMINI_MODEL,
        api_key_configured=is_configured,
    )


@router.post(
    "/api/v1/chat",
    response_model=ChatResponse,
    tags=["Chat"],
    summary="Send a message to the Sana'a AI assistant",
)
def chat_endpoint(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """Send user troubleshooting queries and receive structured guidance."""
    try:
        return service.process_message(request)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while processing the chat request: {str(e)}",
        )


@router.get(
    "/api/v1/chat/history/{session_id}",
    response_model=List[Dict[str, str]],
    tags=["Chat"],
    summary="Get conversation history for a session",
)
def get_session_history(
    session_id: str,
    storage: BaseSessionStorage = Depends(get_session_storage),
) -> List[Dict[str, str]]:
    """Retrieve all turns for an active session."""
    return storage.get_history(session_id)


@router.post(
    "/api/v1/chat/reset",
    response_model=ResetSessionResponse,
    tags=["Chat"],
    summary="Reset conversation history for a session",
)
def reset_session(
    request: ResetSessionRequest,
    storage: BaseSessionStorage = Depends(get_session_storage),
) -> ResetSessionResponse:
    """Clear history for a specific session."""
    storage.clear_history(request.session_id)
    return ResetSessionResponse(session_id=request.session_id)
