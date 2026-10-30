"""Technician Escalation Engine.

Extracts confirmed appliance metadata without hallucination, maps
categories to certified specialist titles, and produces structured
EscalationDetails for future Sana'a booking integration.
"""

import re
from typing import Dict, List, Optional, Tuple

from app.api.schemas import (
    BookingPathway,
    EmergencyContacts,
    EscalationDetails,
    HazardLevel,
    MaintenanceCategory,
)
from app.config import get_settings
from app.core.safety import SafetyEvaluation


# Known appliance brands in Egyptian and regional markets
KNOWN_BRANDS = [
    # Arabic and English brand names
    ("توشيبا", "Toshiba"),
    ("زانوسي", "Zanussi"),
    ("كريازي", "Kiriazi"),
    ("إل جي", "LG"),
    ("ال جي", "LG"),
    ("سامسونج", "Samsung"),
    ("شارب", "Sharp"),
    ("بيكو", "Beko"),
    ("كارير", "Carrier"),
    ("وايت ويل", "White Whale"),
    ("أريستون", "Ariston"),
    ("اريستون", "Ariston"),
    ("إيديال", "Ideal"),
    ("ايديال", "Ideal"),
    ("تورنيدو", "Tornado"),
    ("يونيون اير", "Unionaire"),
    ("فريش", "Fresh"),
    ("الكتروستار", "Electrostar"),
    ("إندست", "Indesit"),
    ("بوش", "Bosch"),
    ("هاير", "Haier"),
    ("دايو", "Daewoo"),
]

# Common model qualifiers mentioned by users
MODEL_INDICATORS = [
    (r"(فوق أوتوماتيك|فوق اوتوماتيك|top load|top-load)", "Top Load / فوق أوتوماتيك"),
    (r"(فول أوتوماتيك|أوتوماتيك كامل|front load|front-load)", "Front Load / تحميل أمامي"),
    (r"(نو فروست|نوفروست|no frost|nofrost)", "No-Frost / نو فروست"),
    (r"(ديفروست|defrost)", "Defrost / ديفروست"),
    (r"(انفرتر|إنفرتر|inverter)", "Inverter / إنفرتر"),
    (r"(ديجيتال|digital)", "Digital / ديجيتال"),
    (r"(\d+\s*قدم)", lambda m: m.group(0)),
    (r"(\d+\s*كيلو|\d+\s*kg)", lambda m: m.group(0)),
]

SPECIALIST_MAP = {
    MaintenanceCategory.WASHING_MACHINE: "فني صيانة غسالات وأجهزة منزلية معتمد",
    MaintenanceCategory.REFRIGERATOR: "فني تبريد وتكييف وصيانة ثلاجات معتمد",
    MaintenanceCategory.ELECTRICAL: "فني كهرباء منازل وتجهيزات معتمد",
    MaintenanceCategory.GAS_AND_PLUMBING: "فني سباكة وتجهيزات صحية معتمد",
    MaintenanceCategory.PAINTING: "فني دهانات وتشطيبات ديكورية",
    MaintenanceCategory.GENERAL_MAINTENANCE: "فني صيانة منزلية عامة معتمد",
    MaintenanceCategory.GENERAL_CONVERSATION: None,
}


class EscalationEngine:
    """Orchestrates metadata extraction and specialist escalation generation."""

    @classmethod
    def build_escalation(
        cls,
        safety_eval: SafetyEvaluation,
        current_message: str,
        history: Optional[List[Dict[str, str]]] = None,
        llm_escalation_flag: bool = False,
    ) -> EscalationDetails:
        """Constructs accurate, un-hallucinated escalation details and booking pathways."""
        all_text = cls._combine_conversation_text(current_message, history)

        # 1. Extract confirmed Brand (Never hallucinated)
        brand = cls._extract_brand(all_text)

        # 2. Extract confirmed Model / Type (Never hallucinated)
        model = cls._extract_model(all_text)

        # 3. Determine booking pathway, urgency justification, and required status
        emergency_contacts = cls._filter_emergency_contacts(safety_eval)

        initial_required = (
            safety_eval.escalate_to_technician
            or llm_escalation_flag
            or safety_eval.hazard_level in [HazardLevel.HIGH, HazardLevel.CRITICAL]
        )

        if safety_eval.life_threatening_emergency:
            booking_pathway = BookingPathway.NONE
            urgency_reason = "تم تعليق حجز الصيانة التجارية مؤقتاً؛ الأولوية القصوى لإخلاء الموقع والتواصل الفوري مع طوارئ المرافق العامة/الدفاع المدني."
            is_required = True
        elif safety_eval.category == MaintenanceCategory.GENERAL_CONVERSATION:
            booking_pathway = BookingPathway.NONE
            urgency_reason = None
            is_required = False
        elif (
            safety_eval.hazard_level == HazardLevel.HIGH
            or (safety_eval.category == MaintenanceCategory.GAS_AND_PLUMBING and any(w in all_text.lower() for w in ["انفجار", "انكسار", "غرق", "burst", "flood", "سخان غاز"]))
            or (safety_eval.category == MaintenanceCategory.REFRIGERATOR and any(w in all_text.lower() for w in ["أدوية", "انسولين", "فاصلة تماماً", "توقف مفاجئ", "total failure", "medicine"]))
        ):
            booking_pathway = BookingPathway.EMERGENCY_MAINTENANCE
            urgency_reason = (
                "انقطاع كامل لمرفق مائي حيوي أو تلف مائي حاد يتطلب تدخلاً سريعاً في نفس اليوم"
                if safety_eval.category == MaintenanceCategory.GAS_AND_PLUMBING
                else "عطل فني حرج غير قابل للتأجيل يتطلب وصول فني طوارئ صيانة معتمد في أسرع وقت"
            )
            is_required = True
        elif initial_required:
            booking_pathway = BookingPathway.STANDARD
            urgency_reason = "العطل ميكانيكي أو تقني مستقر؛ يمكن جدولة زيارة الفني المعتمد في الموعد الأنسب للعميل"
            is_required = True
        else:
            booking_pathway = BookingPathway.DIY
            urgency_reason = None
            is_required = False

        # 4. Identify missing diagnostic parameters
        missing = []
        if safety_eval.category in [MaintenanceCategory.WASHING_MACHINE, MaintenanceCategory.REFRIGERATOR]:
            if not brand:
                missing.append("appliance_brand")
            if not model:
                missing.append("appliance_model")

        # 5. Select recommended specialist with strict plumbing vs gas separation
        specialist = cls._resolve_specialist(safety_eval, all_text, is_required)

        # 6. Format clear escalation reason
        reason = safety_eval.escalation_reason
        if not reason and is_required:
            reason = f"العطل يقع ضمن نطاق {safety_eval.category.value} ويتطلب تدخل فني متخصص"

        return EscalationDetails(
            required=is_required,
            escalation_reason=reason if is_required else None,
            hazard_level=safety_eval.hazard_level,
            category=safety_eval.category,
            reported_symptoms=safety_eval.detected_symptoms,
            recommended_specialist=specialist if is_required else None,
            is_emergency=safety_eval.is_emergency,
            appliance_brand=brand,
            appliance_model=model,
            missing_information=missing,
            booking_pathway=booking_pathway,
            booking_urgency_reason=urgency_reason,
            life_threatening_emergency=safety_eval.life_threatening_emergency,
            emergency_contacts=emergency_contacts,
        )

    @classmethod
    def _resolve_specialist(
        cls,
        safety_eval: SafetyEvaluation,
        all_text: str,
        is_required: bool,
    ) -> Optional[str]:
        """Resolves accurate specialist title differentiating gas vs plumbing and civil emergency."""
        if not is_required:
            return None

        # Critical civil emergencies map to official emergency public entities
        if safety_eval.life_threatening_emergency or safety_eval.hazard_level == HazardLevel.CRITICAL:
            if safety_eval.category == MaintenanceCategory.GAS_AND_PLUMBING or safety_eval.emergency_type == "GAS":
                return "طوارئ شركة الغاز الطبيعي (129) والدفاع المدني (180)"
            elif safety_eval.category == MaintenanceCategory.WASHING_MACHINE:
                return "طوارئ الكهرباء (121) وفني صيانة غسالات معتمد"
            elif safety_eval.category == MaintenanceCategory.REFRIGERATOR:
                return "طوارئ الكهرباء (121) وفني تبريد وتكييف معتمد"
            elif safety_eval.emergency_type in ["ELECTRICAL", "WATER_ELECTRICAL"]:
                return "طوارئ الكهرباء (121) وفني كهربائي معتمد"
            elif safety_eval.emergency_type == "FIRE":
                return "قوات الإطفاء والدفاع المدني (180)"
            return "خدمات الطوارئ الرسمية المختصة"

        # Trade differentiation within GAS_AND_PLUMBING
        if safety_eval.category == MaintenanceCategory.GAS_AND_PLUMBING:
            lower = all_text.lower()
            gas_keywords = ["غاز", "سخان غاز", "بوتاجاز", "بلت ان", "أنبوبة", "اسطوانة", "gas"]
            if any(w in lower for w in gas_keywords):
                return "فني صيانة وتركيبات شبكات غاز معتمد"
            return "فني سباكة وتجهيزات صحية معتمد"

        return SPECIALIST_MAP.get(safety_eval.category)

    @classmethod
    def _filter_emergency_contacts(cls, safety_eval: SafetyEvaluation) -> Optional[EmergencyContacts]:
        """Populates only official emergency hotlines relevant to active hazard."""
        if not safety_eval.life_threatening_emergency:
            return None

        settings = get_settings()
        region = getattr(settings, "DEFAULT_REGION", "EG")
        numbers = settings.VERIFIED_EMERGENCY_NUMBERS.get(
            region,
            settings.VERIFIED_EMERGENCY_NUMBERS.get("EG", {})
        )

        gas_num = None
        elec_num = None
        fire_num = None
        amb_num = None

        if safety_eval.emergency_type == "GAS":
            gas_num = numbers.get("GAS", "129")
            fire_num = numbers.get("FIRE", "180")
        elif safety_eval.emergency_type in ["ELECTRICAL", "WATER_ELECTRICAL"]:
            elec_num = numbers.get("ELECTRICITY", "121")
            if safety_eval.emergency_type == "WATER_ELECTRICAL":
                fire_num = numbers.get("FIRE", "180")
            else:
                amb_num = numbers.get("AMBULANCE", "123")
        elif safety_eval.emergency_type == "FIRE":
            fire_num = numbers.get("FIRE", "180")
            amb_num = numbers.get("AMBULANCE", "123")
            elec_num = numbers.get("ELECTRICITY", "121")
        else:
            fire_num = numbers.get("FIRE", "180")

        return EmergencyContacts(
            gas=gas_num,
            electricity=elec_num,
            fire=fire_num,
            ambulance=amb_num,
        )

    @classmethod
    def _extract_brand(cls, text: str) -> Optional[str]:
        """Detects if a recognized brand name was explicitly mentioned."""
        lower = text.lower()
        for ar_name, en_name in KNOWN_BRANDS:
            if ar_name in lower or en_name.lower() in lower:
                return en_name
        return None

    @classmethod
    def _extract_model(cls, text: str) -> Optional[str]:
        """Detects if model details were explicitly mentioned."""
        lower = text.lower()
        for pattern, label in MODEL_INDICATORS:
            match = re.search(pattern, lower, re.IGNORECASE)
            if match:
                if callable(label):
                    return label(match)
                return label
        return None

    @classmethod
    def _combine_conversation_text(
        cls,
        current_message: str,
        history: Optional[List[Dict[str, str]]],
    ) -> str:
        """Combines current message and recent user turns to maintain context."""
        parts = []
        if history:
            for turn in history:
                if turn.get("role") == "user":
                    parts.append(turn.get("content", ""))
        parts.append(current_message)
        return " ".join(parts)
