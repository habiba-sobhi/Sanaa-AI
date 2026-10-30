"""Unit tests for the independent Safety Engine."""

import pytest
from app.core.safety import SafetyEngine


def test_electric_shock_emergency_triggers_override():
    """Verify that electric shock messages trigger immediate emergency response."""
    result = SafetyEngine.evaluate_input("الغسالة بتكهرب لما بلمس جسمها الخارجي")
    assert result.is_emergency is True
    assert result.hazard_level == "CRITICAL"
    assert result.escalate_to_technician is True
    assert result.override_reply is not None
    assert "لا تلمس" in result.safety_warning or "افصل" in result.override_reply


def test_smoke_burning_smell_triggers_critical():
    """Verify smoke and burning smells are treated as critical emergencies."""
    result = SafetyEngine.evaluate_input("الماتور بيطلع ريحة شياط ودخان")
    assert result.is_emergency is True
    assert result.hazard_level == "CRITICAL"
    assert result.escalate_to_technician is True
    assert result.override_reply is not None


def test_gas_leak_emergency_triggers_critical():
    """Verify gas leak queries trigger critical warnings and verified emergency contacts."""
    result = SafetyEngine.evaluate_input("شامم ريحة غاز قوية جنب السخان")
    assert result.is_emergency is True
    assert result.hazard_level == "CRITICAL"
    assert result.escalate_to_technician is True
    assert "الغاز" in result.override_reply
    assert "129" in result.override_reply


def test_dangerous_diy_freon_triggers_caution():
    """Verify dangerous DIY actions trigger HIGH hazard and technician escalation."""
    result = SafetyEngine.evaluate_input("عايز طريقة شحن فريون للتلاجة في البيت")
    assert result.is_emergency is False
    assert result.hazard_level in ["HIGH", "CAUTION"]
    assert result.escalate_to_technician is True
    assert "سلامة" in result.safety_warning


def test_safe_query_passes_normally():
    """Verify standard queries are evaluated as LOW/SAFE."""
    result = SafetyEngine.evaluate_input("الغسالة مش بتسحب مية")
    assert result.is_emergency is False
    assert result.hazard_level in ["LOW", "SAFE"]
    assert result.escalate_to_technician is False
    assert result.override_reply is None


def test_sanitize_output_injects_power_warning():
    """Verify that opening covers requires power disconnection as step 1."""
    reply, actions, escalate, warning = SafetyEngine.sanitize_output(
        reply="قم بفك الغطاء الخلفي للتأكد من السير",
        suggested_actions=["فك الغطاء الخلفي", "فحص السير المطاطي"],
        escalate_to_technician=False,
    )
    assert "افصل القابس الكهربائي" in actions[0]
    assert warning is not None
