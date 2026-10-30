"""Pydantic schemas for API request and response data models."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HazardLevel(str, Enum):
    """Hazard severity classification."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MaintenanceCategory(str, Enum):
    """Domain trade or conversational category."""

    WASHING_MACHINE = "WASHING_MACHINE"
    REFRIGERATOR = "REFRIGERATOR"
    ELECTRICAL = "ELECTRICAL"
    GAS_AND_PLUMBING = "GAS_AND_PLUMBING"
    PAINTING = "PAINTING"
    GENERAL_MAINTENANCE = "GENERAL_MAINTENANCE"
    GENERAL_CONVERSATION = "GENERAL_CONVERSATION"


class BookingPathway(str, Enum):
    """Sana'a platform technician booking pathways."""

    NONE = "NONE"                                    # General chat, non-maintenance, or suppressed during acute emergency
    DIY = "DIY"                                      # Customer can solve safely with chatbot guidance
    STANDARD = "STANDARD"                            # Standard scheduled maintenance visit
    EMERGENCY_MAINTENANCE = "EMERGENCY_MAINTENANCE"  # Urgent same-day technician dispatch


class EmergencyContacts(BaseModel):
    """Verified official emergency civil services relevant to active hazard."""

    gas: Optional[str] = Field(None, description="Natural gas emergency hotline")
    electricity: Optional[str] = Field(None, description="Electricity emergency hotline")
    fire: Optional[str] = Field(None, description="Fire & civil defense emergency hotline")
    ambulance: Optional[str] = Field(None, description="Medical ambulance emergency hotline")


class SourceCitation(BaseModel):
    """Citation to a technical document or manual."""

    document: str = Field(..., description="Document or manual name")
    section: Optional[str] = Field(None, description="Section or chapter name")
    page: Optional[int] = Field(None, description="Page number in manual")


class EscalationDetails(BaseModel):
    """Machine-readable metadata for future Sana'a technician booking integration."""

    required: bool = Field(
        ...,
        description="Whether professional technician intervention is recommended",
    )
    escalation_reason: Optional[str] = Field(
        None,
        description="Clear technical explanation for escalation",
    )
    hazard_level: HazardLevel = Field(
        HazardLevel.LOW,
        description="Assessed physical hazard level",
    )
    category: MaintenanceCategory = Field(
        MaintenanceCategory.GENERAL_CONVERSATION,
        description="Identified trade or conversational domain",
    )
    reported_symptoms: List[str] = Field(
        default_factory=list,
        description="Extracted problem symptoms",
    )
    recommended_specialist: Optional[str] = Field(
        None,
        description="Recommended trade specialist title (e.g., فني صيانة غسالات معتمد)",
    )
    is_emergency: bool = Field(
        False,
        description="Backward-compatible emergency flag",
    )
    appliance_brand: Optional[str] = Field(
        None,
        description="Confirmed appliance brand, or None if unknown",
    )
    appliance_model: Optional[str] = Field(
        None,
        description="Confirmed appliance model, or None if unknown",
    )
    missing_information: List[str] = Field(
        default_factory=list,
        description="Crucial diagnostic parameters not yet provided by user",
    )
    booking_pathway: BookingPathway = Field(
        BookingPathway.NONE,
        description="Selected booking pathway: NONE, DIY, STANDARD, or EMERGENCY_MAINTENANCE",
    )
    booking_urgency_reason: Optional[str] = Field(
        None,
        description="Technical justification for booking urgency level",
    )
    life_threatening_emergency: bool = Field(
        False,
        description="True ONLY if acute life-threat hazard is active (civil defense priority)",
    )
    emergency_contacts: Optional[EmergencyContacts] = Field(
        None,
        description="Relevant official hotlines populated only during active life-threatening emergencies",
    )


class ChatRequest(BaseModel):
    """Incoming user chat message."""

    session_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Unique session identifier for multi-turn conversation",
        examples=["user-sess-1001"],
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User query in Egyptian Arabic, MSA, English, or mixed",
        examples=["الغسالة بتنزل مية من تحت ومش بتعصر"],
    )
    language: Optional[str] = Field(
        "auto",
        description="Preferred response language ('ar', 'en', or 'auto')",
    )


class ChatResponse(BaseModel):
    """Structured response returned by Sana'a AI."""

    session_id: str = Field(..., description="Active session ID")
    reply: str = Field(..., description="Conversational reply in user's language and dialect")
    language: str = Field(..., description="Detected or matched language")
    suggested_actions: List[str] = Field(
        default_factory=list,
        description="Safe, preliminary troubleshooting bullet points",
    )
    safety_warning: Optional[str] = Field(
        None,
        description="Crucial safety warning if any risk is identified",
    )
    escalate_to_technician: bool = Field(
        False,
        description="True if problem requires certified technician intervention",
    )
    hazard_level: HazardLevel = Field(
        HazardLevel.LOW,
        description="Hazard evaluation: LOW, MEDIUM, HIGH, or CRITICAL",
    )
    escalation_details: Optional[EscalationDetails] = Field(
        None,
        description="Structured escalation payload for Sana'a booking integration",
    )
    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Citations from manuals (empty until RAG is added in Milestone 3)",
    )


class HealthResponse(BaseModel):
    """Service health status response."""

    status: str = "healthy"
    version: str = "0.2.0"
    llm_provider: str
    model: str
    api_key_configured: bool


class ResetSessionRequest(BaseModel):
    """Request to clear a conversation history."""

    session_id: str


class ResetSessionResponse(BaseModel):
    """Response after clearing conversation history."""

    session_id: str
    message: str = "Conversation history cleared successfully."
