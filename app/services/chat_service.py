"""Chat Orchestration Service.

Coordinates conversation memory, context-aware safety evaluation,
LLM generation, output sanitization, and structured technician escalation.
"""

import logging
from typing import Optional

from app.api.schemas import BookingPathway, ChatRequest, ChatResponse, HazardLevel
from app.config import Settings, get_settings
from app.core.escalation import EscalationEngine
from app.core.memory import BaseSessionStorage, get_session_storage
from app.core.prompts import SYSTEM_PROMPT
from app.core.safety import SafetyClassifier, SafetySanitizer
from app.services.llm_service import BaseLLMService, get_llm_service, RateLimitExceededError

logger = logging.getLogger(__name__)


class ChatService:
    """Orchestrator for multi-turn conversational troubleshooting and trade support."""

    def __init__(
        self,
        llm_service: Optional[BaseLLMService] = None,
        session_storage: Optional[BaseSessionStorage] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.llm_service = llm_service or get_llm_service(self.settings)
        self.session_storage = session_storage or get_session_storage(self.settings.MAX_HISTORY_TURNS)

    def process_message(self, request: ChatRequest) -> ChatResponse:
        """Process an incoming user message through the verified execution order:

        1. Load conversation history.
        2. Evaluate physical safety with current message taking priority.
        3. Intercept active emergencies immediately (bypassing LLM).
        4. Call LLM for non-emergency queries.
        5. Sanitize output to guarantee zero dangerous physical instructions.
        6. Construct un-hallucinated escalation details.
        7. Persist conversation turn in memory.
        """
        user_text = request.message.strip()
        session_id = request.session_id

        # -------------------------------------------------------------------
        # 1. Load Conversation Context First
        # -------------------------------------------------------------------
        history = self.session_storage.get_history(session_id)

        # -------------------------------------------------------------------
        # 2. Context-Aware Safety Classification (Current message has priority)
        # -------------------------------------------------------------------
        safety_eval = SafetyClassifier.evaluate(
            current_message=user_text,
            history=history,
        )

        # -------------------------------------------------------------------
        # 3. Emergency Intercept Protocol (Bypasses LLM generation)
        # -------------------------------------------------------------------
        if safety_eval.is_emergency and safety_eval.override_reply:
            logger.warning(f"Immediate safety emergency triggered for session {session_id}")

            # Build structured escalation payload
            escalation_details = EscalationEngine.build_escalation(
                safety_eval=safety_eval,
                current_message=user_text,
                history=history,
                llm_escalation_flag=False,
            )

            # Record turn in session memory
            self.session_storage.add_turn(
                session_id=session_id,
                user_message=user_text,
                assistant_reply=safety_eval.override_reply,
            )

            return ChatResponse(
                session_id=session_id,
                reply=safety_eval.override_reply,
                language=request.language or "ar",
                suggested_actions=[
                    "الابتعاد عن مكان الخطر فوراً وإخلاء المنطقة إذا لزم الأمر",
                    "عدم لمس أي أجهزة أو مفاتيح كهربائية في منطقة الخطر",
                    "التواصل مع خدمات الطوارئ الرسمية المعتمدة من مكان آمن",
                ],
                safety_warning=safety_eval.safety_warning,
                escalate_to_technician=False,  # Commercial booking strictly suppressed during active life-threat
                hazard_level=safety_eval.hazard_level,
                escalation_details=escalation_details,
                sources=[],
            )

        # -------------------------------------------------------------------
        # 4. Prepare Context & Call LLM Provider
        # -------------------------------------------------------------------
        current_context = list(history)
        current_context.append({"role": "user", "content": user_text})

        try:
            llm_result = self.llm_service.generate_chat_response(
                messages=current_context,
                system_instruction=SYSTEM_PROMPT,
            )
        except RateLimitExceededError as e:
            escalation_details = EscalationEngine.build_escalation(
                safety_eval=safety_eval,
                current_message=user_text,
                history=history,
                llm_escalation_flag=False,
            )
            return ChatResponse(
                session_id=session_id,
                reply=str(e),
                language="ar",
                suggested_actions=["إعادة المحاولة بعد 10 ثوانٍ"],
                safety_warning=safety_eval.safety_warning,
                escalate_to_technician=False,
                hazard_level=safety_eval.hazard_level,
                escalation_details=escalation_details,
                sources=[],
            )
        except Exception as e:
            logger.error(f"Error invoking LLM service: {e}")
            escalation_details = EscalationEngine.build_escalation(
                safety_eval=safety_eval,
                current_message=user_text,
                history=history,
                llm_escalation_flag=False,
            )
            return ChatResponse(
                session_id=session_id,
                reply="عذراً، حدث خطأ مؤقت أثناء معالجة طلبك. يرجى إعادة المحاولة.",
                language="ar",
                suggested_actions=["إعادة المحاولة"],
                safety_warning=safety_eval.safety_warning,
                escalate_to_technician=False,
                hazard_level=safety_eval.hazard_level,
                escalation_details=escalation_details,
                sources=[],
            )

        # -------------------------------------------------------------------
        # 5. Post-LLM Safety Sanitization
        # -------------------------------------------------------------------
        raw_reply = llm_result.get("reply", "")
        raw_actions = llm_result.get("suggested_actions", [])
        raw_escalate = (
            llm_result.get("escalate_to_technician", False)
            or safety_eval.escalate_to_technician
        )

        sanitized_reply, sanitized_actions, final_escalate, auto_warning = SafetySanitizer.sanitize(
            reply=raw_reply,
            suggested_actions=raw_actions,
            escalate_to_technician=raw_escalate,
        )

        final_warning = (
            safety_eval.safety_warning
            or auto_warning
            or llm_result.get("safety_warning")
        )

        # Parse final hazard level enum safely
        raw_hazard_str = str(llm_result.get("hazard_level", "LOW")).upper()
        if safety_eval.hazard_level != HazardLevel.LOW:
            final_hazard = safety_eval.hazard_level
        else:
            try:
                final_hazard = HazardLevel(raw_hazard_str)
            except ValueError:
                final_hazard = HazardLevel.LOW

        # -------------------------------------------------------------------
        # 6. Build Structured Technician Escalation Details
        # -------------------------------------------------------------------
        escalation_details = EscalationEngine.build_escalation(
            safety_eval=safety_eval,
            current_message=user_text,
            history=history,
            llm_escalation_flag=final_escalate,
        )

        # Commercial technician booking is true only for STANDARD or EMERGENCY_MAINTENANCE
        commercial_escalate = (
            escalation_details.booking_pathway in [
                BookingPathway.STANDARD,
                BookingPathway.EMERGENCY_MAINTENANCE,
            ]
            if escalation_details
            else False
        )

        # -------------------------------------------------------------------
        # 7. Persist Turn in Session Storage
        # -------------------------------------------------------------------
        self.session_storage.add_turn(
            session_id=session_id,
            user_message=user_text,
            assistant_reply=sanitized_reply,
        )

        return ChatResponse(
            session_id=session_id,
            reply=sanitized_reply,
            language=request.language or "ar",
            suggested_actions=sanitized_actions,
            safety_warning=final_warning,
            escalate_to_technician=commercial_escalate,
            hazard_level=final_hazard,
            escalation_details=escalation_details,
            sources=[],  # Preserved empty for Milestone 3 (RAG)
        )
