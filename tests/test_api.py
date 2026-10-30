"""API and Endpoint Logic Tests (Synchronous, deterministic unit tests)."""

import pytest
from app.api.routes import health_check, chat_endpoint, get_session_history, reset_session
from app.api.schemas import ChatRequest, ResetSessionRequest
from app.config import Settings
from app.core.memory import InMemorySessionStorage
from app.services.chat_service import ChatService
from app.services.llm_service import BaseLLMService


class MockLLMService(BaseLLMService):
    """Mock LLM to test conversational flow without requiring an external API key."""

    def generate_chat_response(self, messages, system_instruction):
        return {
            "reply": "أهلاً بك! يرجى التأكد من توصيل خرطوم المياه جيداً وفحص الفلتر.",
            "suggested_actions": ["فحص الخرطوم", "تنظيف الفلتر"],
            "safety_warning": "افصل الكهرباء قبل فحص الفلتر",
            "escalate_to_technician": False,
            "hazard_level": "SAFE",
        }


def test_health_endpoint_direct():
    """Verify health check returns expected status and fields."""
    settings = Settings(GEMINI_API_KEY="")
    response = health_check(settings=settings)
    assert response.status == "healthy"
    assert "0." in response.version
    assert response.llm_provider == "gemini"
    assert response.api_key_configured is False


def test_chat_critical_safety_escalation():
    """Verify that an emergency message triggers immediate safety override and suppresses commercial booking."""
    storage = InMemorySessionStorage(max_turns=5)
    service = ChatService(llm_service=MockLLMService(), session_storage=storage)

    request = ChatRequest(
        session_id="test-safety-sess-1",
        message="الغسالة بتكهرب المية وجسمها بيطلع شرز",
    )
    response = chat_endpoint(request=request, service=service)
    assert response.escalate_to_technician is False  # Commercial booking strictly suppressed
    assert response.hazard_level == "CRITICAL"
    assert response.safety_warning is not None
    assert response.escalation_details is not None
    assert response.escalation_details.required is True
    assert response.escalation_details.is_emergency is True
    assert response.escalation_details.life_threatening_emergency is True
    assert response.escalation_details.booking_pathway == "NONE"
    assert response.escalation_details.emergency_contacts is not None
    assert response.escalation_details.emergency_contacts.electricity == "121"
    assert len(response.suggested_actions) > 0


def test_chat_flow_and_session_memory():
    """Test full multi-turn conversation cycle with mock LLM service."""
    storage = InMemorySessionStorage(max_turns=5)
    service = ChatService(llm_service=MockLLMService(), session_storage=storage)

    # First turn
    request = ChatRequest(
        session_id="test-chat-sess-2",
        message="الغسالة مش بتسحب مية خالص",
    )
    response = chat_endpoint(request=request, service=service)
    assert response.session_id == "test-chat-sess-2"
    assert "أهلاً بك" in response.reply
    assert response.escalate_to_technician is False

    # Verify history recorded
    history = get_session_history(session_id="test-chat-sess-2", storage=storage)
    assert len(history) == 2  # 1 user + 1 assistant turn
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "model"

    # Second turn in the same session
    request_followup = ChatRequest(
        session_id="test-chat-sess-2",
        message="عملت كده وبرضه مش بتسحب",
    )
    response_followup = chat_endpoint(request=request_followup, service=service)
    assert response_followup.session_id == "test-chat-sess-2"

    history_after_followup = get_session_history(session_id="test-chat-sess-2", storage=storage)
    assert len(history_after_followup) == 4  # 2 turns = 4 messages

    # Verify session reset
    reset_resp = reset_session(
        request=ResetSessionRequest(session_id="test-chat-sess-2"),
        storage=storage,
    )
    assert reset_resp.session_id == "test-chat-sess-2"
    cleared_history = get_session_history(session_id="test-chat-sess-2", storage=storage)
    assert len(cleared_history) == 0


def test_frontend_routes_served_successfully():
    """Verify that frontend HTML, CSS, and JS endpoints return 200 OK with Figma elements."""
    from app.main import serve_chat_ui, serve_css, serve_js

    html_res = serve_chat_ui()
    assert html_res.status_code == 200
    html_text = html_res.body.decode("utf-8")
    assert "صَنعة" in html_text
    assert "المساعد الذكي" in html_text
    assert "مساعد حل المشكلة" in html_text

    css_res = serve_css()
    assert css_res.status_code == 200
    assert "Cairo" in css_res.body.decode("utf-8")

    js_res = serve_js()
    assert js_res.status_code == 200
    assert "/api/v1/chat" in js_res.body.decode("utf-8")
