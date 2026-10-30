"""Unit and Orchestration Tests for Sana'a AI Conversational Personality.

Tests:
1. General conversation outside maintenance.
2. Egyptian Arabic, MSA, English, and mixed code-switching.
3. Language matching and switching.
4. Multi-turn context memory and continuity.
5. Diagnostic clarification behavior.
"""

import pytest
from app.api.schemas import ChatRequest, HazardLevel, MaintenanceCategory
from app.core.memory import InMemorySessionStorage
from app.services.chat_service import ChatService
from app.services.llm_service import BaseLLMService


class AdaptiveMockLLMService(BaseLLMService):
    """Mock LLM simulating intelligent multilingual responses and dialect mirroring."""

    def generate_chat_response(self, messages, system_instruction):
        last_msg = messages[-1]["content"].lower()

        # 1. English General Knowledge
        if "capital of egypt" in last_msg or "what is" in last_msg:
            return {
                "reply": "Cairo is the vibrant capital of Egypt, known for its rich history and ancient heritage!",
                "suggested_actions": ["Ask another general question", "Ask about home maintenance"],
                "safety_warning": None,
                "escalate_to_technician": False,
                "hazard_level": "LOW",
            }

        # 2. Egyptian Arabic Casual Greeting
        if any(w in last_msg for w in ["ازيك", "عامل ايه", "صباح الفل"]):
            return {
                "reply": "صباح الفل والجمال يا فندم! الحمد لله كله تمام، يا رب تكون بخير. أقدر أساعدك في إيه النهاردة في البيت أو الأجهزة؟",
                "suggested_actions": ["صيانة غسالات", "صيانة ثلاجات", "نصائح منزلية"],
                "safety_warning": None,
                "escalate_to_technician": False,
                "hazard_level": "LOW",
            }

        # 3. Modern Standard Arabic (MSA) Maintenance
        if any(w in last_msg for w in ["أود معرفة", "لماذا لا تبرد", "كيف يمكنني"]):
            return {
                "reply": "مرحباً بك. لتشخيص سبب عدم تبريد الثلاجة بدقة، يرجى التأكد أولاً من عمل مروحة الفريزر وسماع صوت دوران الضاغط.",
                "suggested_actions": ["التأكد من إغلاق الباب بإحكام", "فحص مؤشر ضبط التبريد"],
                "safety_warning": "يرجى فصل التيار الكهربائي قبل فحص المكونات الخلفية.",
                "escalate_to_technician": False,
                "hazard_level": "MEDIUM",
            }

        # 4. Mixed Language Code-Switching
        if "spin" in last_msg or "vibration" in last_msg:
            return {
                "reply": "أهلاً بحضرتك. مشكلة الـ vibration العالي وقت الـ spin غالباً سببها عدم اتزان أرجل الغسالة أو زيادة حمولة الغسيل.",
                "suggested_actions": ["ضبط اتزان القواعد السفلية بميزان مياه", "توزيع الملابس بانتظام داخل الحلة"],
                "safety_warning": "لا تفتح باب الغسالة وهي في وضع الدوران السريع.",
                "escalate_to_technician": False,
                "hazard_level": "MEDIUM",
            }

        # 5. Diagnostic Clarification Loop (when brand is missing)
        if "بتخبط" in last_msg and not any(b in last_msg for b in ["توشيبا", "زانوسي", "lg"]):
            return {
                "reply": "أهلاً بك يا فندم. عشان نقدر نحدد السبب بالظبط، ممكن توضحلي ماركة الغسالة إيه؟ وهل الخبط بيحصل أول ما تبدأ تلف ولا في مرحلة العصر فقط؟",
                "suggested_actions": ["تحديد ماركة وموديل الغسالة", "ملاحظة وقت حدوث صوت الخبط"],
                "safety_warning": None,
                "escalate_to_technician": False,
                "hazard_level": "LOW",
            }

        # Default fallback
        return {
            "reply": "أهلاً بحضرتك في صَنعة! تحت أمرك لمساعدتك في أي استفسار.",
            "suggested_actions": ["استفسار صيانة", "سؤال عام"],
            "safety_warning": None,
            "escalate_to_technician": False,
            "hazard_level": "LOW",
        }


def test_general_conversation_egyptian_arabic():
    """Verify casual greetings in Egyptian Arabic return natural friendly response without forced maintenance."""
    storage = InMemorySessionStorage(max_turns=5)
    service = ChatService(llm_service=AdaptiveMockLLMService(), session_storage=storage)

    req = ChatRequest(session_id="chat-test-1", message="صباح الفل يا صَنعة، ازيك عامل ايه؟")
    resp = service.process_message(req)

    assert "صباح الفل" in resp.reply
    assert resp.hazard_level == HazardLevel.LOW
    assert resp.escalate_to_technician is False
    assert resp.escalation_details.category == MaintenanceCategory.GENERAL_CONVERSATION


def test_general_knowledge_english():
    """Verify general questions in English are answered naturally without rejection."""
    storage = InMemorySessionStorage(max_turns=5)
    service = ChatService(llm_service=AdaptiveMockLLMService(), session_storage=storage)

    req = ChatRequest(session_id="chat-test-2", message="What is the capital of Egypt?")
    resp = service.process_message(req)

    assert "Cairo" in resp.reply
    assert resp.hazard_level == HazardLevel.LOW
    assert resp.escalate_to_technician is False


def test_msa_language_matching():
    """Verify Modern Standard Arabic input receives formal Arabic response."""
    storage = InMemorySessionStorage(max_turns=5)
    service = ChatService(llm_service=AdaptiveMockLLMService(), session_storage=storage)

    req = ChatRequest(session_id="chat-test-3", message="أود معرفة أسباب عدم تبريد الثلاجة من الأسفل؟")
    resp = service.process_message(req)

    assert "مرحباً بك" in resp.reply
    assert "الثلاجة" in resp.reply
    assert resp.escalation_details.category == MaintenanceCategory.REFRIGERATOR


def test_mixed_code_switching_handling():
    """Verify mixed Arabic/English terms (Franco-technical) are handled smoothly."""
    storage = InMemorySessionStorage(max_turns=5)
    service = ChatService(llm_service=AdaptiveMockLLMService(), session_storage=storage)

    req = ChatRequest(session_id="chat-test-4", message="عندي مشكلة في الغسالة بتعمل vibration جامد في الـ spin")
    resp = service.process_message(req)

    assert "vibration" in resp.reply or "spin" in resp.reply
    assert resp.escalation_details.category == MaintenanceCategory.WASHING_MACHINE


def test_multi_turn_context_continuity_and_brand_memory():
    """Verify multi-turn conversation remembers brand from turn 1 into turn 2."""
    storage = InMemorySessionStorage(max_turns=5)
    service = ChatService(llm_service=AdaptiveMockLLMService(), session_storage=storage)

    # Turn 1: User mentions brand
    req1 = ChatRequest(session_id="multi-turn-sess-1", message="عندي غسالة توشيبا فوق أوتوماتيك")
    resp1 = service.process_message(req1)
    assert resp1.escalation_details.appliance_brand == "Toshiba"

    # Turn 2: User provides short symptom without repeating brand
    req2 = ChatRequest(session_id="multi-turn-sess-1", message="بتخبط في مرحلة العصر")
    resp2 = service.process_message(req2)

    # Context continuity check: Escalation engine still remembers Toshiba from session history
    assert resp2.escalation_details.appliance_brand == "Toshiba"
    assert "Top Load" in resp2.escalation_details.appliance_model or "فوق أوتوماتيك" in resp2.escalation_details.appliance_model


def test_diagnostic_clarification_when_brand_missing():
    """Verify Sana'a asks clarifying questions when diagnostic details are missing."""
    storage = InMemorySessionStorage(max_turns=5)
    service = ChatService(llm_service=AdaptiveMockLLMService(), session_storage=storage)

    req = ChatRequest(session_id="clarify-sess-1", message="الغسالة بتخبط ومش عارف ليه")
    resp = service.process_message(req)

    # Bot should politely ask for brand or timing
    assert "ماركة" in resp.reply or "موديل" in resp.reply
    assert "appliance_brand" in resp.escalation_details.missing_information
