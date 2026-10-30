"""Comprehensive Unit and Integration Tests for Sana'a Booking Pathways and Safety Architecture.

Tests cover:
1. Pathway A: DIY Guidance Appropriate
2. Pathway B: Standard Technician Booking Recommended
3. Pathway C: Emergency Maintenance Booking Recommended (Non-Life-Threat)
4. Pathway D: Active Life-Threatening Emergency (Commercial Booking Suppressed)
5. Multi-turn Transition: Active Emergency -> Confirmed Safety Clearance -> Professional Maintenance
6. Multi-turn Unconfirmed Gas Valve: Closing valve alone does not resolve danger without clearance
7. Specialist Differentiation: Plumbing vs Natural Gas Trade Separation
8. Non-Hallucination: Brand and Model strictly extracted or left None with missing_information
9. Legacy Client Protection: escalate_to_technician is strictly False during acute life-threats
10. Hazard-Specific Emergency Contact Filtering
"""

import pytest
from app.api.schemas import (
    BookingPathway,
    ChatRequest,
    HazardLevel,
    MaintenanceCategory,
)
from app.api.routes import chat_endpoint
from app.core.escalation import EscalationEngine
from app.core.memory import InMemorySessionStorage
from app.core.safety import SafetyClassifier
from app.services.chat_service import ChatService
from app.services.llm_service import BaseLLMService


class MockDiagnosticLLMService(BaseLLMService):
    """Mock LLM for testing multi-turn booking flows without network calls."""

    def __init__(self, reply_text="سأساعدك في هذا الأمر.", escalate=False, hazard="LOW"):
        self.reply_text = reply_text
        self.escalate = escalate
        self.hazard = hazard

    def generate_chat_response(self, messages, system_instruction):
        return {
            "reply": self.reply_text,
            "suggested_actions": ["فحص مبدئي", "تأكيد الأمان"],
            "safety_warning": None,
            "escalate_to_technician": self.escalate,
            "hazard_level": self.hazard,
        }


# ===========================================================================
# 1. Pathway A: DIY Guidance Appropriate
# ===========================================================================

def test_pathway_a_diy_guidance_clean_filter():
    """Verify safe troubleshooting maps to DIY without commercial booking."""
    safety_eval = SafetyClassifier.evaluate("إزاي أفك وأنضف فلتر طرد الغسالة بنفسي؟")
    details = EscalationEngine.build_escalation(
        safety_eval=safety_eval,
        current_message="إزاي أفك وأنضف فلتر طرد الغسالة بنفسي؟",
    )

    assert details.booking_pathway == BookingPathway.DIY
    assert details.required is False
    assert details.is_emergency is False
    assert details.life_threatening_emergency is False
    assert details.emergency_contacts is None
    assert details.appliance_brand is None
    assert details.appliance_model is None
    # Brand and model not provided, correctly registered as missing
    assert "appliance_brand" in details.missing_information
    assert "appliance_model" in details.missing_information


# ===========================================================================
# 2. Pathway B: Standard Technician Booking Recommended
# ===========================================================================

def test_pathway_b_standard_booking_mechanical_issue():
    """Verify mechanical degradation without immediate danger maps to STANDARD booking."""
    safety_eval = SafetyClassifier.evaluate("صوت خبط عالي في الغسالة أثناء العصر وتأكدت أن الملابس متزنة والأرض مستوية")
    details = EscalationEngine.build_escalation(
        safety_eval=safety_eval,
        current_message="صوت خبط عالي في الغسالة أثناء العصر وتأكدت أن الملابس متزنة والأرض مستوية",
        llm_escalation_flag=True,  # LLM recommends professional inspection
    )

    assert details.booking_pathway == BookingPathway.STANDARD
    assert details.required is True
    assert details.is_emergency is False
    assert details.life_threatening_emergency is False
    assert details.emergency_contacts is None
    assert details.recommended_specialist == "فني صيانة غسالات وأجهزة منزلية معتمد"
    assert details.booking_urgency_reason is not None


# ===========================================================================
# 3. Pathway C: Emergency Maintenance Booking (Non-Life-Threat Urgent)
# ===========================================================================

def test_pathway_c_emergency_maintenance_water_pipe_burst():
    """Verify urgent non-life-threatening failure maps to EMERGENCY_MAINTENANCE with plumbing specialist."""
    # Main valve was shut so no drowning/shock, but pipe is burst flooding bathroom
    msg = "ماسورة المياه الرئيسية في الحمام انفجرت وغرقت الأرضية وقفلنا المحبس العمومي للشقة"
    safety_eval = SafetyClassifier.evaluate(msg)
    details = EscalationEngine.build_escalation(
        safety_eval=safety_eval,
        current_message=msg,
    )

    assert details.booking_pathway == BookingPathway.EMERGENCY_MAINTENANCE
    assert details.required is True
    assert details.life_threatening_emergency is False
    assert details.is_emergency is False
    assert details.emergency_contacts is None
    # Specialist must strictly be plumber, not gas!
    assert details.recommended_specialist == "فني سباكة وتجهيزات صحية معتمد"
    assert "غاز" not in details.recommended_specialist


def test_pathway_c_emergency_maintenance_fridge_medicine():
    """Verify critical food/medicine refrigeration breakdown triggers urgent maintenance."""
    msg = "الثلاجة توقف مفاجئ للموتور وفيها أدوية وإنسولين ومحتاج صيانة سريعة"
    safety_eval = SafetyClassifier.evaluate(msg)
    details = EscalationEngine.build_escalation(
        safety_eval=safety_eval,
        current_message=msg,
        llm_escalation_flag=True,
    )

    assert details.booking_pathway == BookingPathway.EMERGENCY_MAINTENANCE
    assert details.required is True
    assert details.life_threatening_emergency is False
    assert "تبريد" in details.recommended_specialist


# ===========================================================================
# 4. Pathway D: Active Life-Threatening Emergency (Booking Suppressed)
# ===========================================================================

def test_pathway_d_active_gas_leak_suppresses_commercial_booking():
    """Verify active gas leak sets booking_pathway=NONE, life_threat=True, and filters contacts."""
    storage = InMemorySessionStorage(max_turns=5)
    service = ChatService(llm_service=MockDiagnosticLLMService(), session_storage=storage)

    req = ChatRequest(
        session_id="test-gas-threat-1",
        message="الحقني في ريحة غاز قوية جداً جنب السخان في الحمام ومش عارفين نعمل ايه!",
    )
    resp = chat_endpoint(request=req, service=service)

    # Legacy commercial booking flag must be FALSE
    assert resp.escalate_to_technician is False
    assert resp.hazard_level == HazardLevel.CRITICAL
    assert resp.escalation_details is not None
    assert resp.escalation_details.booking_pathway == BookingPathway.NONE
    assert resp.escalation_details.life_threatening_emergency is True
    assert resp.escalation_details.is_emergency is True
    assert resp.escalation_details.required is True

    # Filtered emergency contacts: Gas (129) and Fire (180), NOT electricity
    contacts = resp.escalation_details.emergency_contacts
    assert contacts is not None
    assert contacts.gas == "129"
    assert contacts.fire == "180"
    assert contacts.electricity is None


def test_pathway_d_active_electrical_shock_filtered_contacts():
    """Verify active electric shock provides 121 and 123, NOT gas."""
    safety_eval = SafetyClassifier.evaluate("جسم الغسالة بيكهرب جامد وفي شرار طالع")
    details = EscalationEngine.build_escalation(
        safety_eval=safety_eval,
        current_message="جسم الغسالة بيكهرب جامد وفي شرار طالع",
    )

    assert details.booking_pathway == BookingPathway.NONE
    assert details.life_threatening_emergency is True
    assert details.emergency_contacts is not None
    assert details.emergency_contacts.electricity == "121"
    assert details.emergency_contacts.ambulance == "123"
    assert details.emergency_contacts.gas is None


# ===========================================================================
# 5. Multi-Turn Transition: Emergency -> Verified Safety Clearance -> Booking
# ===========================================================================

def test_multi_turn_emergency_to_safe_repair_transition():
    """Verify full multi-turn cycle from acute life-threat to post-safety maintenance booking."""
    storage = InMemorySessionStorage(max_turns=5)
    service = ChatService(
        llm_service=MockDiagnosticLLMService(
            reply_text="الحمد لله على سلامتكم. يمكننا الآن حجز فني صيانة غاز معتمد لفحص واستبدال وصلة السخان بأمان.",
            escalate=True,
            hazard="HIGH",
        ),
        session_storage=storage,
    )

    session_id = "test-multi-turn-threat-flow"

    # Turn 1: Acute life-threatening gas leak
    turn1_req = ChatRequest(
        session_id=session_id,
        message="في ريحة غاز قوية جداً جنب السخان في المطبخ!",
    )
    turn1_resp = chat_endpoint(request=turn1_req, service=service)

    assert turn1_resp.escalate_to_technician is False
    assert turn1_resp.escalation_details.life_threatening_emergency is True
    assert turn1_resp.escalation_details.booking_pathway == BookingPathway.NONE
    assert "129" in turn1_resp.reply

    # Turn 2: Verified safety clearance by emergency crew + request for repair
    turn2_req = ChatRequest(
        session_id=session_id,
        message="الحمد لله طوارئ الغاز جت شيكت وأمنت المكان وقالت العيب في وصلة السخان ومحتاجين فني يغيرها",
    )
    turn2_resp = chat_endpoint(request=turn2_req, service=service)

    # Now the immediate danger has been handled, commercial booking is allowed!
    assert turn2_resp.escalation_details.life_threatening_emergency is False
    assert turn2_resp.escalation_details.is_emergency is False
    assert turn2_resp.escalate_to_technician is True
    assert turn2_resp.escalation_details.booking_pathway in [
        BookingPathway.EMERGENCY_MAINTENANCE,
        BookingPathway.STANDARD,
    ]
    assert "غاز" in turn2_resp.escalation_details.recommended_specialist


# ===========================================================================
# 6. Gas Valve Only: Closing valve alone does NOT resolve hazard
# ===========================================================================

def test_gas_valve_only_without_clearance_remains_active_threat():
    """Verify closing valve alone without clearance does not clear life-threatening emergency."""
    # Customer closed valve but still mentions active gas leak/smell
    msg = "قفلنا المحبس والريحة لسه قوية جداً ومش عارفين نعمل ايه مع الغاز"
    safety_eval = SafetyClassifier.evaluate(msg)

    assert safety_eval.is_emergency is True
    assert safety_eval.life_threatening_emergency is True
    assert safety_eval.hazard_level == HazardLevel.CRITICAL
    assert "129" in safety_eval.override_reply


# ===========================================================================
# 7. Specialist Differentiation: Plumbing vs Gas
# ===========================================================================

def test_specialist_differentiation_plumbing_vs_gas():
    """Verify water leaks map to plumbing and gas appliances map to gas specialist."""
    # Water leak
    water_eval = SafetyClassifier.evaluate("حنفية المطبخ بتسرب مية جامد ومحتاج سباك يصلحها")
    water_details = EscalationEngine.build_escalation(
        safety_eval=water_eval,
        current_message="حنفية المطبخ بتسرب مية جامد ومحتاج سباك يصلحها",
        llm_escalation_flag=True,
    )
    assert water_details.recommended_specialist == "فني سباكة وتجهيزات صحية معتمد"
    assert "غاز" not in water_details.recommended_specialist

    # Gas appliance (non-emergency)
    gas_eval = SafetyClassifier.evaluate("عايز فني يركب وصلة بوتاجاز غاز طبيعي في المطبخ")
    gas_details = EscalationEngine.build_escalation(
        safety_eval=gas_eval,
        current_message="عايز فني يركب وصلة بوتاجاز غاز طبيعي في المطبخ",
        llm_escalation_flag=True,
    )
    assert gas_details.recommended_specialist == "فني صيانة وتركيبات شبكات غاز معتمد"


# ===========================================================================
# 8. Non-Hallucination: Brand and Model strictly extracted or None
# ===========================================================================

def test_brand_model_never_fabricated():
    """Verify brand and model are strictly None when unmentioned and captured when mentioned."""
    # Case A: No brand or model
    eval_a = SafetyClassifier.evaluate("الغسالة بتنزل مية من تحت")
    details_a = EscalationEngine.build_escalation(
        safety_eval=eval_a,
        current_message="الغسالة بتنزل مية من تحت",
    )
    assert details_a.appliance_brand is None
    assert details_a.appliance_model is None
    assert "appliance_brand" in details_a.missing_information
    assert "appliance_model" in details_a.missing_information

    # Case B: Explicit brand and model
    eval_b = SafetyClassifier.evaluate("عندي ثلاجة شارب نو فروست بتعمل صوت تكتكة")
    details_b = EscalationEngine.build_escalation(
        safety_eval=eval_b,
        current_message="عندي ثلاجة شارب نو فروست بتعمل صوت تكتكة",
    )
    assert details_b.appliance_brand == "Sharp"
    assert "No-Frost" in details_b.appliance_model or "نو فروست" in details_b.appliance_model
    assert "appliance_brand" not in details_b.missing_information
    assert "appliance_model" not in details_b.missing_information


# ===========================================================================
# 9. General Conversation Pathway NONE
# ===========================================================================

def test_general_conversation_pathway_none():
    """Verify general conversation produces BookingPathway.NONE and no escalation."""
    safety_eval = SafetyClassifier.evaluate("صباح الخير يا صَنعة، الجو عامل إيه النهاردة؟")
    details = EscalationEngine.build_escalation(
        safety_eval=safety_eval,
        current_message="صباح الخير يا صَنعة، الجو عامل إيه النهاردة؟",
    )
    assert details.booking_pathway == BookingPathway.NONE
    assert details.required is False
    assert details.recommended_specialist is None
    assert details.life_threatening_emergency is False


# ===========================================================================
# 10. Legacy Client Protection: Strict Commercial Booking Suppression
# ===========================================================================

def test_legacy_client_commercial_booking_suppression_on_emergency():
    """Verify legacy clients relying only on escalate_to_technician receive False during life-threat."""
    storage = InMemorySessionStorage(max_turns=5)
    service = ChatService(llm_service=MockDiagnosticLLMService(), session_storage=storage)

    req = ChatRequest(
        session_id="legacy-client-threat-check",
        message="الفيشة غرقت مية وبتطلع شرار ودخان!",
    )
    resp = chat_endpoint(request=req, service=service)

    # A legacy frontend client evaluating `if (resp.escalate_to_technician) showBookingButton()`
    # will safely receive False, preventing commercial booking during a dangerous incident.
    assert resp.escalate_to_technician is False
    assert resp.escalation_details.life_threatening_emergency is True
    assert resp.escalation_details.booking_pathway == BookingPathway.NONE
    assert resp.escalation_details.required is True
    assert resp.escalation_details.emergency_contacts is not None
    assert resp.escalation_details.emergency_contacts.electricity == "121"
