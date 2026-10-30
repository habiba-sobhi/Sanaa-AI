"""Comprehensive Safety and Hazard Classification Engine.

Implements multi-stage safety evaluation:
1. Contextual pre-filtering & negation masking.
2. Multilingual deterministic hazard rules (Egyptian Arabic, MSA, English, code-switching).
3. Conservative ambiguity handling (never defaulting ambiguous hazards to LOW).
4. Strict emergency safety protocols (distance/evacuation first, no dangerous switch operations).
5. Post-generation safety sanitization.
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from app.api.schemas import HazardLevel, MaintenanceCategory
from app.config import get_settings


@dataclass
class SafetyEvaluation:
    """Detailed outcome of safety classification."""

    hazard_level: HazardLevel
    category: MaintenanceCategory
    is_emergency: bool
    escalate_to_technician: bool
    safety_warning: Optional[str] = None
    override_reply: Optional[str] = None
    escalation_reason: Optional[str] = None
    detected_symptoms: List[str] = field(default_factory=list)
    life_threatening_emergency: bool = False
    emergency_type: Optional[str] = None


# ---------------------------------------------------------------------------
# Pre-filter Regex Patterns (Negation, Past/Resolved, and Hypotheticals)
# ---------------------------------------------------------------------------

NEGATION_PATTERNS = [
    # Arabic negation (Egyptian & MSA)
    r"(مش|مفيش|ما في|غير|لا يوجد|ليس|بدون)\s+(بتكهرب|بيكهرب|كهربا|شرز|شرار|ريحة شياط|ريحة حريق|ريحة غاز|دخان|تسريب|ماس)",
    r"(الحمد لله|اطمنت)\s+.*(مفيش|مش)",
    # English negation
    r"\b(no|not|doesn't|does not|without|no longer|neither)\s+(shock|shocks|spark|sparks|smoke|fire|burning|gas leak|leak|electrical)\b",
]

RESOLVED_HAZARD_PATTERNS = [
    # Arabic resolved past indicators
    r"(كانت|كان)\s+(بتكهرب|بتشرز|بيطلع دخان|في ريحة شياط|في تسريب)\s+.*(وصلحنا|واتصلحت|والمشكلة اتحلت|وغيرنا|وخلاص|زمان|من فترة)",
    r"(صلحنا|غيرنا|حلينا)\s+.*(الماس|الشرز|العطل|التسريب)",
    # English resolved past indicators
    r"\b(used to|was|were|previously)\s+(spark|smoke|shock|leak)\b.*(fixed|repaired|resolved|replaced|now fine)\b",
    r"\b(already fixed|already repaired|problem is solved)\b",
]

# Patterns where customer only closed valve but hazard CANNOT be assumed resolved without clearance
VALVE_CLOSED_UNCONFIRMED_PATTERNS = [
    r"(قفلنا|قفلت|غلقت|غلقنا)\s+.*(المحبس|الاسطوانة|أسطوانة|محبس الغاز)",
    r"\b(closed|shut off)\s+.*(valve|gas valve)\b",
]

# Confirmed professional clearance or verified safe resolution
CONFIRMED_SAFETY_CLEARANCE_PATTERNS = [
    r"(طوارئ الغاز|شركة الغاز|الفني|الدفاع المدني|المطافئ)\s+.*(شيكت|عاينت|فحصت|أمنت|اطمنت|قالت|صلحت|خلصت|غيرت)",
    r"(هوينا المكان|الريحة راحت|مفيش ريحة غاز|المشكلة اتحلت|اتصلح التسريب|صلحنا السلك خلاص|اتصلح خلاص)",
    r"\b(gas company|fire department|technician|cleared|inspected|fixed the leak|no more smell|problem is solved)\b",
]

HYPOTHETICAL_PATTERNS = [
    r"^(هل|لو|ممكن|ازاي أعرف لو)\s+.*(يسرب|يكهرب|يولع|يتحرق)\s*\??$",
    r"^(can|could|would|what if|how do i know if)\s+.*(leak|shock|catch fire|explode)\s*\??$",
]


# ---------------------------------------------------------------------------
# Active Critical Emergencies Patterns
# ---------------------------------------------------------------------------

CRITICAL_ELECTRICAL_PATTERNS = [
    r"(بتكهرب|بيكهرب|بتلسع كهربا|ماس كهربائ|كهربا في (المية|المياه|الحلة|الجسم))",
    r"\b(electric shock|chassis.*shock|shocks me|live electricity|electrified)\b",
    r"(بيطلع شرز|شرار|بتشرز|بيشرز|شرارة كهربا|sparks?|sparking|arcing)",
]

CRITICAL_FIRE_SMOKE_PATTERNS = [
    r"(ريحة (شياط|حريق|دخان)|طالع منها دخان|بتطلع دخان|شايف دخان|ريحة سلك بيتحرق)",
    r"\b(smoke|burning plastic|catching fire|spotted flames)\b",
]

CRITICAL_GAS_PATTERNS = [
    r"(ريحة غاز|شامم غاز|صوت تنفيس غاز|تسريب غاز|تنسيم غاز)",
    r"(ريحة|شامم|تنسيم|تسريب|تنفيس)\s+.*(غاز)",
    r"(غاز)\s+.*(ريحة|تسريب|تنسيم|تنفيس|بيسرب|بيهرب)",
    r"\b(smell of gas|gas odor|gas leak|hissing gas|gas.*leak|smell.*gas)\b",
]

CRITICAL_WATER_ELECTRICAL_PATTERNS = [
    r"(مية (غرقت|دخلت|وصلت|بتنزل على|جت على)\s+(ال)?(فيشة|بريزة|لوحة|مقبس|عداد|كبس))",
    r"\b(water (flooding|leaking into|running over)\s+(the\s+)?(socket|outlet|breaker|electrical panel))\b",
]


# ---------------------------------------------------------------------------
# High-Risk DIY Patterns (Prohibited physical disassembly / tampering)
# ---------------------------------------------------------------------------

DANGEROUS_DIY_PATTERNS = [
    (
        r"(شحن (فريون|الفريون)|تعبئة فريون|recharge freon|fill freon)",
        "شحن غاز الفريون يتطلب معدات ضغط وتفريغ متخصصة ولا يمكن إجراؤه منزلياً بأمان",
        MaintenanceCategory.REFRIGERATOR,
    ),
    (
        r"((أ|ا)?فك|(أ|ا)?غير|تغيير)\s+.*(الكومبروسر|الضاغط|الموتور|الكباس)|replace compressor",
        "فك الضاغط أو موتور التبريد يتطلب لحام وتفريغ شحنة الغاز وأدوات فنية معتمدة",
        MaintenanceCategory.REFRIGERATOR,
    ),
    (
        r"((أ|ا)?فك|(أ|ا)?غير|تغيير|لمس)\s+.*(مكثف|الكاباستور|كاباستور|المكثفات|capacitor)",
        "مكثفات المحركات تخزن شحنات كهربائية عالية قاتلة حتى بعد فصل الكهرباء",
        MaintenanceCategory.ELECTRICAL,
    ),
    (
        r"(تعديل (الفيوز|القاطع)|تجاوز القاطع|كباريل فيوز|bypass (fuse|breaker))",
        "تجاوز قواطع الحماية يلغي أمان الدائرة ويؤدي لاحتراق التوصيلات فوراً",
        MaintenanceCategory.ELECTRICAL,
    ),
]


# ---------------------------------------------------------------------------
# Ambiguous Situation Patterns (Popping, sudden bangs, unknown burning)
# ---------------------------------------------------------------------------

AMBIGUOUS_HAZARD_PATTERNS = [
    r"(صوت فرقعة|فرقعت فجأة|سمعت صوت بوب|طقت فجأة|loud (pop|bang|explosion sound))",
    r"(فصلت نور الشقة|نزلت القاطع ومرفوعش|tripped main breaker and won't reset)",
]


class SafetyClassifier:
    """Evaluates incoming text and conversation context to classify physical safety risks."""

    @classmethod
    def evaluate(
        cls,
        current_message: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> SafetyEvaluation:
        """Classify safety severity and category.

        Current message takes priority over historical context.
        """
        text = current_message.strip()
        lower_text = text.lower()
        settings = get_settings()

        # Retrieve verified emergency numbers from configuration
        region = getattr(settings, "DEFAULT_REGION", "EG")
        numbers = settings.VERIFIED_EMERGENCY_NUMBERS.get(
            region,
            settings.VERIFIED_EMERGENCY_NUMBERS.get("EG", {}),
        )

        gas_num = numbers.get("GAS", "129")
        elec_num = numbers.get("ELECTRICITY", "121")
        fire_num = numbers.get("FIRE", "180")

        # -------------------------------------------------------------------
        # Stage 1: Contextual Pre-Filter (Check resolved past or pure hypothetical)
        # -------------------------------------------------------------------
        # Check if customer merely closed a valve without professional clearance or confirmed ventilation
        valve_only = any(re.search(p, lower_text, re.IGNORECASE) for p in VALVE_CLOSED_UNCONFIRMED_PATTERNS)
        confirmed_clearance = any(re.search(p, lower_text, re.IGNORECASE) for p in CONFIRMED_SAFETY_CLEARANCE_PATTERNS)

        # If gas is involved, closing valve alone is NOT enough to resolve the hazard
        has_gas_mention = bool(re.search(r"(غاز|gas)", lower_text, re.IGNORECASE))
        if has_gas_mention and valve_only and not confirmed_clearance:
            # Cannot assume resolved: closing a valve alone is unconfirmed
            is_resolved = False
        else:
            is_resolved = any(re.search(p, lower_text, re.IGNORECASE) for p in RESOLVED_HAZARD_PATTERNS) or confirmed_clearance

        is_hypothetical = any(re.search(p, lower_text, re.IGNORECASE) for p in HYPOTHETICAL_PATTERNS)

        if is_resolved:
            cat = cls._detect_category(lower_text)
            needs_repair = any(w in lower_text for w in ["فني", "صلح", "تغيير", "غير", "صيانة", "technician", "repair", "replace", "وصلة"])
            if needs_repair:
                # Reevaluate: after verified safety clearance, user requires technical repair
                high_risk_trade = cat in [MaintenanceCategory.GAS_AND_PLUMBING, MaintenanceCategory.ELECTRICAL]
                level = HazardLevel.HIGH if high_risk_trade else HazardLevel.MEDIUM
                return SafetyEvaluation(
                    hazard_level=level,
                    category=cat,
                    is_emergency=False,
                    life_threatening_emergency=False,
                    escalate_to_technician=True,
                    safety_warning="تأكد من استمرار غلق المحبس أو فصل التيار لحين وصول الفني المعتمد.",
                    override_reply=None,
                    escalation_reason=f"طلب صيانة وإصلاح بعد تأمين العطل السابق في نطاق {cat.value}",
                    detected_symptoms=["طلب صيانة بعد تأمين العطل السابق"],
                )
            else:
                return SafetyEvaluation(
                    hazard_level=HazardLevel.LOW,
                    category=cat,
                    is_emergency=False,
                    life_threatening_emergency=False,
                    escalate_to_technician=False,
                    safety_warning=None,
                    override_reply=None,
                    escalation_reason="سياق استفسار عن عطل سابق تم حله أو سؤال نظري",
                    detected_symptoms=[],
                )

        if is_hypothetical:
            cat = cls._detect_category(lower_text)
            return SafetyEvaluation(
                hazard_level=HazardLevel.LOW,
                category=cat,
                is_emergency=False,
                life_threatening_emergency=False,
                escalate_to_technician=False,
                safety_warning=None,
                override_reply=None,
                escalation_reason="سؤال نظري أو افتراضي",
                detected_symptoms=[],
            )

        # -------------------------------------------------------------------
        # Stage 1.5: Mask Negated Hazard Phrases
        # Replace negated phrases (e.g. 'مش بتكهرب', 'no smoke') so they don't trigger active checks
        # -------------------------------------------------------------------
        active_scan_text = lower_text
        for pattern in NEGATION_PATTERNS:
            active_scan_text = re.sub(pattern, "[negated_phrase]", active_scan_text, flags=re.IGNORECASE)

        # -------------------------------------------------------------------
        # Stage 2: Active Critical Emergencies (Life-Threat Protocol)
        # -------------------------------------------------------------------

        # 1. Gas Leak Emergency
        if any(re.search(p, active_scan_text, re.IGNORECASE) for p in CRITICAL_GAS_PATTERNS):
            reply = (
                "طوارئ تسريب غاز - تحذير أمان عاجل:\n"
                "1. ابتعد عن المكان وأخلِ المنطقة فوراً أنت ومن معك.\n"
                "2. تحذير شديد: لا تلمس أي مفاتيح إضاءة أو أجهزة كهربائية، ولا تشغل شفاطات، ولا تشعل أي نيران لتجنب حدوث شرر.\n"
                "3. افتح النوافذ فقط إذا كانت قريبة منك وأنت في طريقك للخروج دون تأخير.\n"
                f"4. اتصل فوراً بطوارئ الغاز على الرقم المعتمد ({gas_num}) أو المطافئ ({fire_num}) من مكان آمن تماماً خارج المنزل."
            )
            return SafetyEvaluation(
                hazard_level=HazardLevel.CRITICAL,
                category=MaintenanceCategory.GAS_AND_PLUMBING,
                is_emergency=True,
                life_threatening_emergency=True,
                emergency_type="GAS",
                escalate_to_technician=True,
                safety_warning="خطر تسريب غاز فوري: ابتعد عن المكان، لا تضغط أي مفاتيح كهرباء، واتصل بطوارئ الغاز.",
                override_reply=reply,
                escalation_reason="اشتباه في تسريب غاز طبيعي يهدد السلامة العامة",
                detected_symptoms=["تسريب غاز", "رائحة غاز نشطة"],
            )

        # 2. Electric Shock / Live Chassis / Sparks
        if any(re.search(p, active_scan_text, re.IGNORECASE) for p in CRITICAL_ELECTRICAL_PATTERNS):
            appliance_cat = cls._detect_category(active_scan_text)
            assigned_cat = (
                appliance_cat
                if appliance_cat in [MaintenanceCategory.WASHING_MACHINE, MaintenanceCategory.REFRIGERATOR]
                else MaintenanceCategory.ELECTRICAL
            )
            reply = (
                "خطر صعق كهربائي - تحذير أمان عاجل:\n"
                "1. ابتعد فوراً عن الجهاز ولا تلمسه نهائياً، ولا تلمس أي أسطح أو مياه محيطة به.\n"
                "2. افصل القاطع العام للكهرباء فقط إذا كانت لوحة القواطع في مكان جاف وآمن تماماً بعيداً عن الجهاز. إذا كانت اللوحة قريبة أو غير آمنة، لا تقترب.\n"
                f"3. اتصل فوراً بطوارئ الكهرباء ({elec_num}) أو اطلب فني معتمد لفحص الجهاز قبل إعادة استخدامه."
            )
            return SafetyEvaluation(
                hazard_level=HazardLevel.CRITICAL,
                category=assigned_cat,
                is_emergency=True,
                life_threatening_emergency=True,
                emergency_type="ELECTRICAL",
                escalate_to_technician=True,
                safety_warning="خطر صعق كهربائي: لا تلمس الجهاز أو المياه المحيطة به.",
                override_reply=reply,
                escalation_reason="تسريب كهربائي أو ماس في جسم الجهاز يهدد بالصعق",
                detected_symptoms=["ماس كهربائي", "كهرباء في جسم الجهاز أو شرر نشط"],
            )

        # 3. Fire / Active Smoke / Burning Smell
        if any(re.search(p, active_scan_text, re.IGNORECASE) for p in CRITICAL_FIRE_SMOKE_PATTERNS):
            reply = (
                "خطر حريق أو احتراق داخلي - تحذير أمان عاجل:\n"
                "1. ابتعد عن الجهاز فوراً وتأكد من سلامة المتواجدين في المكان.\n"
                "2. إذا كانت لوحة القواطع الرئيسية في مكان آمن وجاف، افصل قاطع الدائرة العام دون الاقتراب من الدخان.\n"
                f"3. في حالة تصاعد ألسنة لهب أو دخان كثيف، أخلِ المكان فوراً واتصل بقوات الإطفاء ({fire_num}).\n"
                "4. لا تحاول تشغيل الجهاز نهائياً لحين فحصه المتخصص."
            )
            return SafetyEvaluation(
                hazard_level=HazardLevel.CRITICAL,
                category=MaintenanceCategory.ELECTRICAL,
                is_emergency=True,
                life_threatening_emergency=True,
                emergency_type="FIRE",
                escalate_to_technician=True,
                safety_warning="خطر حريق: تصاعد دخان أو رائحة احتراق تتطلب إخلاء وفصل الأمان.",
                override_reply=reply,
                escalation_reason="تصاعد دخان أو روائح حريق تشير لاحتراق مكونات داخلية",
                detected_symptoms=["دخان", "رائحة شياط أو حريق"],
            )

        # 4. Water Flooding onto Live Electrical Outlets
        if any(re.search(p, active_scan_text, re.IGNORECASE) for p in CRITICAL_WATER_ELECTRICAL_PATTERNS):
            reply = (
                "خطر صعق حاد - وصول المياه لمصادر الكهرباء:\n"
                "1. تحذير شديد: لا تخطُ في المياه المتراكمة ولا تلمس المقبس أو القابس المبلل إطلاقاً.\n"
                "2. توجه فوراً إلى لوحة التوزيع الرئيسية (في مكان جاف) وافصل القاطع العمومي للكهرباء عن المنطقة بالكامل.\n"
                f"3. إذا كان الوصول للوحة التوزيع غير آمن أو مبلل، ابتعد فوراً واطلب طوارئ الكهرباء ({elec_num}) للمساعدة."
            )
            return SafetyEvaluation(
                hazard_level=HazardLevel.CRITICAL,
                category=MaintenanceCategory.ELECTRICAL,
                is_emergency=True,
                life_threatening_emergency=True,
                emergency_type="WATER_ELECTRICAL",
                escalate_to_technician=True,
                safety_warning="خطر صعق كهربائي: مياه متصلة بمصادر كهرباء حية.",
                override_reply=reply,
                escalation_reason="غمر مائي للمنافذ الكهربائية يمثل خطراً حرجاً",
                detected_symptoms=["مياه على المقابس أو اللوحة"],
            )

        # -------------------------------------------------------------------
        # Stage 3: Dangerous DIY Actions (HIGH Hazard)
        # -------------------------------------------------------------------
        for pattern, warning_reason, cat in DANGEROUS_DIY_PATTERNS:
            if re.search(pattern, active_scan_text, re.IGNORECASE):
                return SafetyEvaluation(
                    hazard_level=HazardLevel.HIGH,
                    category=cat,
                    is_emergency=False,
                    escalate_to_technician=True,
                    safety_warning=f"تنبيه سلامة: {warning_reason}.",
                    override_reply=None,
                    escalation_reason=warning_reason,
                    detected_symptoms=["طلب إجراء صيانة غير آمنة منزلياً"],
                )

        # -------------------------------------------------------------------
        # Stage 4: Ambiguous But Potentially Dangerous Situations
        # -------------------------------------------------------------------
        for pattern in AMBIGUOUS_HAZARD_PATTERNS:
            if re.search(pattern, active_scan_text, re.IGNORECASE):
                cat = cls._detect_category(active_scan_text)
                return SafetyEvaluation(
                    hazard_level=HazardLevel.MEDIUM,
                    category=cat,
                    is_emergency=False,
                    escalate_to_technician=False,
                    safety_warning="تنبيه حذر: حدوث أصوات فرقعة مفاجئة أو هبوط القاطع يتطلب الحذر وعدم ملامسة التوصيلات مباشرة.",
                    override_reply=None,
                    escalation_reason="صوت فرقعة أو فصل مفاجئ للقاطع يتطلب فحص احترازي",
                    detected_symptoms=["فرقعة مفاجئة أو انقطاع تيار"],
                )

        # -------------------------------------------------------------------
        # Stage 5: Normal Maintenance or General Conversation (LOW Hazard)
        # -------------------------------------------------------------------
        cat = cls._detect_category(active_scan_text)
        return SafetyEvaluation(
            hazard_level=HazardLevel.LOW,
            category=cat,
            is_emergency=False,
            escalate_to_technician=False,
            safety_warning=None,
            override_reply=None,
            escalation_reason=None,
            detected_symptoms=[],
        )

    @classmethod
    def _detect_category(cls, lower_text: str) -> MaintenanceCategory:
        """Detect trade or conversational domain from text."""
        # Washing machine keywords
        if any(w in lower_text for w in ["غسال", "عصر", "طرد", "حلة", "washing machine", "washer", "dryer", "spin"]):
            return MaintenanceCategory.WASHING_MACHINE

        # Refrigerator keywords
        if any(w in lower_text for w in ["تلاج", "فريزر", "تبريد", "ثلج", "ثلاجة", "refrigerator", "fridge", "freezer"]):
            return MaintenanceCategory.REFRIGERATOR

        # Painting keywords
        if any(w in lower_text for w in ["دهان", "بياض", "نقاش", "معجون", "رول", "فرشة", "حيط", "paint", "roller", "wall"]):
            return MaintenanceCategory.PAINTING

        # Electrical keywords
        if any(w in lower_text for w in ["سلك", "فيشة", "بريزة", "لمبة", "مفتاح كهربا", "نجفة", "قاطع", "wire", "plug", "socket"]):
            return MaintenanceCategory.ELECTRICAL

        # Gas / Plumbing keywords
        if any(w in lower_text for w in ["سخان", "محبس", "ماسورة", "حنفية", "سباك", "غاز", "plumb", "heater", "faucet", "pipe"]):
            return MaintenanceCategory.GAS_AND_PLUMBING

        # Check for general maintenance words
        if any(w in lower_text for w in ["صيانة", "عطل", "تصليح", "باظت", "مش شغالة", "repair", "fix", "broken"]):
            return MaintenanceCategory.GENERAL_MAINTENANCE

        # Otherwise: General conversation
        return MaintenanceCategory.GENERAL_CONVERSATION


class SafetySanitizer:
    """Verifies that generated model output complies with physical safety constraints."""

    @classmethod
    def sanitize(
        cls,
        reply: str,
        suggested_actions: List[str],
        escalate_to_technician: bool,
    ) -> Tuple[str, List[str], bool, Optional[str]]:
        """Sanitizes text and actions to prevent unsafe physical DIY instructions."""
        dangerous_phrases = [
            "اشحن الفريون بنفسك",
            "المس المكثف",
            "تجاوز الفيوز",
            "فك الضاغط باللحام",
            "touch the live wire",
            "bypass the safety switch",
        ]

        lower_reply = reply.lower()
        for phrase in dangerous_phrases:
            if phrase in lower_reply:
                return (
                    "تنبيه أمان: تم حجب هذه الخطوة لأن هذا الإجراء يتطلب فحصاً احترافياً وأدوات سلامة معتمدة لحمايتك وحماية الجهاز. يرجى الاستعانة بفني متخصص.",
                    ["فصل الجهاز عن الكهرباء", "طلب فني صيانة معتمد عبر التطبيق"],
                    True,
                    "إجراء غير آمن للاستخدام المنزلي.",
                )

        # Ensure that if any action involves opening or unscrewing, power disconnection is mandatory
        disassembly_keywords = ["فك", "افتح الغطاء", "مسامير", "remove cover", "unscrew", "open panel"]
        power_keywords = ["افصل الفيشة", "افصل الكهرباء", "انزع القابس", "unplug", "disconnect power"]

        needs_power_warning = any(
            any(w in act.lower() for w in disassembly_keywords) for act in suggested_actions
        )
        has_power_warning = any(
            any(w in act.lower() for w in power_keywords) for act in suggested_actions
        )

        final_actions = list(suggested_actions)
        safety_warning = None

        if needs_power_warning and not has_power_warning:
            final_actions.insert(0, "افصل القابس الكهربائي عن الجهاز تماماً قبل لمس أي أجزاء داخلية")
            safety_warning = "تحذير أمان: لا تقم بفك أي أغطية أو مسامير قبل فصل الكهرباء تماماً."

        return reply, final_actions, escalate_to_technician, safety_warning


class SafetyEngine:
    """Backward-compatibility facade for Milestone 1 interfaces."""

    @classmethod
    def evaluate_input(cls, user_message: str) -> SafetyEvaluation:
        return SafetyClassifier.evaluate(current_message=user_message)

    @classmethod
    def sanitize_output(
        cls,
        reply: str,
        suggested_actions: List[str],
        escalate_to_technician: bool,
    ) -> Tuple[str, List[str], bool, Optional[str]]:
        return SafetySanitizer.sanitize(
            reply=reply,
            suggested_actions=suggested_actions,
            escalate_to_technician=escalate_to_technician,
        )
