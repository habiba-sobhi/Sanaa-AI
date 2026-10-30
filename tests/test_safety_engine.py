"""Comprehensive Unit Tests for Safety Engine, Classification & Escalation."""

import pytest
from app.api.schemas import HazardLevel, MaintenanceCategory
from app.core.safety import SafetyClassifier, SafetySanitizer
from app.core.escalation import EscalationEngine


# ===========================================================================
# 1. Active Critical Emergencies & Emergency Safety Protocols
# ===========================================================================

def test_gas_leak_emergency_evacuation_and_verified_hotline():
    """Verify gas leak triggers evacuation, prohibits switch operations, and provides verified 129 hotline."""
    eval_res = SafetyClassifier.evaluate("شامم ريحة غاز قوية جداً جنب السخان")
    assert eval_res.is_emergency is True
    assert eval_res.hazard_level == HazardLevel.CRITICAL
    assert eval_res.category == MaintenanceCategory.GAS_AND_PLUMBING
    assert eval_res.escalate_to_technician is True

    # Critical safety protocol checks:
    # 1. Must advise distance / evacuation
    assert "ابتعد" in eval_res.override_reply or "أخلِ" in eval_res.override_reply
    # 2. Must strictly prohibit touching electrical switches
    assert "لا تلمس أي مفاتيح إضاءة" in eval_res.override_reply
    # 3. Must provide verified Egyptian gas emergency hotline (129)
    assert "129" in eval_res.override_reply


def test_electric_shock_emergency_prohibits_touching_hazard():
    """Verify electric shock prioritizes distance, never tells user to touch live appliance, provides 121."""
    eval_res = SafetyClassifier.evaluate("جسم الغسالة بيكهرب ومفيش حد عارف يلمسها")
    assert eval_res.is_emergency is True
    assert eval_res.hazard_level == HazardLevel.CRITICAL
    assert eval_res.category in [MaintenanceCategory.WASHING_MACHINE, MaintenanceCategory.ELECTRICAL]
    assert "لا تلمسه نهائياً" in eval_res.override_reply
    assert "121" in eval_res.override_reply


def test_fire_and_smoke_emergency_hotline():
    """Verify active burning smell and smoke triggers fire emergency hotline 180."""
    eval_res = SafetyClassifier.evaluate("في دخان وريحة شياط جامدة طالعة من ظهر التلاجة")
    assert eval_res.is_emergency is True
    assert eval_res.hazard_level == HazardLevel.CRITICAL
    assert "180" in eval_res.override_reply


def test_water_on_electrical_outlet_safety():
    """Verify water flooding onto outlets warns against stepping in water."""
    eval_res = SafetyClassifier.evaluate("المية غرقت فيشة الكهرباء والبريزة في المطبخ")
    assert eval_res.is_emergency is True
    assert eval_res.hazard_level == HazardLevel.CRITICAL
    assert "لا تخطُ في المياه" in eval_res.override_reply


# ===========================================================================
# 2. Multilingual Support: English and Mixed Code-Switching Hazards
# ===========================================================================

def test_english_critical_hazard():
    """Verify English emergency triggers critical safety protocol."""
    eval_res = SafetyClassifier.evaluate("Smoke is coming out of my washing machine and it shocks me!")
    assert eval_res.is_emergency is True
    assert eval_res.hazard_level == HazardLevel.CRITICAL
    assert eval_res.escalate_to_technician is True


def test_mixed_language_code_switching_hazard():
    """Verify mixed Franco/Arabic technical hazard is caught."""
    eval_res = SafetyClassifier.evaluate("الـ socket بتطلع sparks وريحة burning بلاستيك")
    assert eval_res.is_emergency is True
    assert eval_res.hazard_level == HazardLevel.CRITICAL


# ===========================================================================
# 3. Negation & Resolved Past Hazards vs Active Current Hazards
# ===========================================================================

def test_negation_in_arabic_is_not_emergency():
    """Verify that 'مش بتكهرب الحمد لله' is not classified as an active emergency."""
    eval_res = SafetyClassifier.evaluate("الغسالة بتلف كويس ومش بتكهرب الحمد لله، بس صوتها عالي شوية")
    assert eval_res.is_emergency is False
    assert eval_res.hazard_level == HazardLevel.LOW


def test_negation_in_english_is_not_emergency():
    """Verify English negation 'no smoke and no burning smell' is not an emergency."""
    eval_res = SafetyClassifier.evaluate("The fridge makes a hum but there is no smoke and no burning smell.")
    assert eval_res.is_emergency is False
    assert eval_res.hazard_level == HazardLevel.LOW


def test_resolved_past_hazard_is_not_active_emergency():
    """Verify that past resolved hazards do not trigger emergency overrides."""
    eval_res = SafetyClassifier.evaluate("الغسالة كانت بتطلع شرز زمان وصلحناها خلاص، دلوقتي بس عايز أعرف إزاي أنضف الدرج")
    assert eval_res.is_emergency is False
    assert eval_res.hazard_level == HazardLevel.LOW


def test_conflicting_history_current_hazard_takes_absolute_priority():
    """Verify that if past turns were resolved, but current message reports active smoke, it triggers immediately."""
    history = [
        {"role": "user", "content": "صلحنا ماس السلك زمان وخلاص"},
        {"role": "model", "content": "الحمد لله على السلامة."},
    ]
    # Current message reports active danger
    current_msg = "الحقني، دلوقتي طالع دخان وريحة شياط حقيقية!"
    eval_res = SafetyClassifier.evaluate(current_message=current_msg, history=history)
    assert eval_res.is_emergency is True
    assert eval_res.hazard_level == HazardLevel.CRITICAL


# ===========================================================================
# 4. Dangerous DIY Actions (HIGH Hazard)
# ===========================================================================

def test_dangerous_diy_freon_prohibition():
    """Verify Freon recharging is strictly prohibited and marked HIGH hazard."""
    eval_res = SafetyClassifier.evaluate("عايز خطوات شحن الفريون بنفسي للتلاجة")
    assert eval_res.is_emergency is False
    assert eval_res.hazard_level == HazardLevel.HIGH
    assert eval_res.escalate_to_technician is True
    assert "فريون" in eval_res.safety_warning


def test_dangerous_diy_capacitor_tampering():
    """Verify touching or replacing motor capacitor is prohibited."""
    eval_res = SafetyClassifier.evaluate("إزاي أفك كاباستور الماتور وأغيره في البيت؟")
    assert eval_res.hazard_level == HazardLevel.HIGH
    assert eval_res.escalate_to_technician is True
    assert "مكثف" in eval_res.safety_warning or "كاباستور" in eval_res.safety_warning


# ===========================================================================
# 5. Ambiguity Handling (Never defaulting to LOW)
# ===========================================================================

def test_ambiguous_sudden_bang_never_defaults_to_low():
    """Verify an ambiguous loud pop/bang elevates conservatively to MEDIUM, not LOW."""
    eval_res = SafetyClassifier.evaluate("سمعت صوت فرقعة مفاجئة جوا الغسالة ونور اللوحة طفى")
    assert eval_res.is_emergency is False
    assert eval_res.hazard_level in [HazardLevel.MEDIUM, HazardLevel.HIGH]
    assert eval_res.hazard_level != HazardLevel.LOW


# ===========================================================================
# 6. Structured Escalation Data Integrity (No Hallucinated Brands/Models)
# ===========================================================================

def test_escalation_extracts_explicit_brand_and_model():
    """Verify brand and model are captured accurately when explicitly given."""
    safety_eval = SafetyClassifier.evaluate("غسالة زانوسي فوق أوتوماتيك بتطلع صوت عالي وبتشرز")
    details = EscalationEngine.build_escalation(
        safety_eval=safety_eval,
        current_message="غسالة زانوسي فوق أوتوماتيك بتطلع صوت عالي وبتشرز",
    )
    assert details.required is True
    assert details.appliance_brand == "Zanussi"
    assert "فوق أوتوماتيك" in details.appliance_model or "Top Load" in details.appliance_model
    assert details.recommended_specialist is not None
    assert "غسالات" in details.recommended_specialist


def test_escalation_does_not_fabricate_missing_brand():
    """Verify missing brand is kept as None and noted in missing_information."""
    safety_eval = SafetyClassifier.evaluate("الغسالة بتطلع صوت تكتكة ومش بتعصر خالص")
    details = EscalationEngine.build_escalation(
        safety_eval=safety_eval,
        current_message="الغسالة بتطلع صوت تكتكة ومش بتعصر خالص",
    )
    assert details.appliance_brand is None
    assert "appliance_brand" in details.missing_information
