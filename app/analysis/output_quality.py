"""Post-processing guards for LLM recommendation output."""

from __future__ import annotations

from typing import Any

from app.models.analysis import RecommendationCategory, SignalSeverity
from app.utils.text import normalize_whitespace

COPIED_CATEGORY_SEPARATOR = "|"
MAX_CONFIDENCE_WITHOUT_EVIDENCE = 0.75

IMPROVEMENT_REQUIRED_FIELDS = ("issue", "suggested_change", "reason")
MISSING_REQUIRED_FIELDS = ("missing_content", "suggestion_or_outline", "reason")

POSITIVE_NO_ISSUE_PHRASES = (
    "is clear",
    "is already clear",
    "is grammatically correct",
    "follows a logical structure",
    "no issue",
    "no changes needed",
    "works well",
    "is effective",
)

GENERIC_IMPROVEMENT_ISSUES = (
    "missing content that should be added to this page or section",
    "the current content is insufficient for the user's needs",
)

GENERIC_MISSING_CONTENT = (
    "missing content that should be added to this page or section",
    "the text is cluttered and hard to read",
)

CATEGORY_KEYWORDS: tuple[tuple[RecommendationCategory, tuple[str, ...]], ...] = (
    (
        RecommendationCategory.GRAMMAR,
        ("grammar", "grammatical", "spelling", "typo", "punctuation"),
    ),
    (
        RecommendationCategory.CTA,
        ("call to action", "cta", "button", "next step", "sign up", "contact"),
    ),
    (
        RecommendationCategory.STRUCTURE,
        ("heading", "section", "organize", "structure", "paragraph", "substructure"),
    ),
    (
        RecommendationCategory.DUPLICATION,
        ("repeat", "repeated", "duplicate", "duplication", "overlap", "repetitive"),
    ),
    (
        RecommendationCategory.TRUST,
        (
            "trust",
            "proof",
            "testimonial",
            "credibility",
            "guarantee",
            "certification",
            "social proof",
        ),
    ),
    (
        RecommendationCategory.ENGAGEMENT,
        ("engage", "engagement", "reader", "compelling", "interest"),
    ),
    (RecommendationCategory.TONE, ("tone", "voice", "consistent")),
    (
        RecommendationCategory.READABILITY,
        ("readability", "readable", "scan", "dense", "jargon", "long paragraph"),
    ),
    (
        RecommendationCategory.MISSING_CONTEXT,
        ("context", "explain", "detail", "background", "introduction"),
    ),
    (RecommendationCategory.CLARITY, ("clear", "clarity", "vague", "specific")),
)


def clean_improvement_payload(
    item: dict[str, Any],
    *,
    warnings: list[str],
) -> dict[str, Any] | None:
    """Normalize and filter one improvement recommendation payload."""

    cleaned = _normalize_string_fields(item)
    if _missing_required_text(cleaned, IMPROVEMENT_REQUIRED_FIELDS):
        warnings.append("dropped_improvement_missing_required_text")
        return None

    issue = str(cleaned["issue"])
    suggested_change = str(cleaned["suggested_change"])
    reason = str(cleaned["reason"])
    quality_text = " ".join([issue, suggested_change, reason]).lower()

    if _contains_any(issue.lower(), POSITIVE_NO_ISSUE_PHRASES):
        warnings.append("dropped_improvement_without_clear_issue")
        return None
    if _contains_any(issue.lower(), GENERIC_IMPROVEMENT_ISSUES):
        warnings.append("dropped_generic_improvement")
        return None

    category, normalized_from_copied_list = normalize_recommendation_category(
        cleaned.get("category"),
        fallback_text=quality_text,
    )
    cleaned["category"] = category.value
    if normalized_from_copied_list:
        warnings.append("normalized_copied_category_list")

    cleaned["confidence"] = _clean_confidence(cleaned.get("confidence"), default=0.6)
    evidence = normalize_whitespace(str(cleaned.get("evidence_snippet") or ""))
    cleaned["evidence_snippet"] = evidence or None
    if cleaned["evidence_snippet"] is None:
        cleaned["confidence"] = min(
            cleaned["confidence"],
            MAX_CONFIDENCE_WITHOUT_EVIDENCE,
        )

    cleaned["example_text"] = _clean_optional_text(cleaned.get("example_text"))
    cleaned["severity"] = _clean_severity(
        cleaned.get("severity"),
        default=SignalSeverity.MEDIUM,
    ).value
    return cleaned


def clean_missing_content_payload(
    item: dict[str, Any],
    *,
    warnings: list[str],
) -> dict[str, Any] | None:
    """Normalize and filter one missing-content recommendation payload."""

    cleaned = _normalize_string_fields(item)
    if _missing_required_text(cleaned, MISSING_REQUIRED_FIELDS):
        warnings.append("dropped_missing_content_missing_required_text")
        return None

    missing_content = str(cleaned["missing_content"])
    suggestion = str(cleaned["suggestion_or_outline"])
    if _contains_any(missing_content.lower(), GENERIC_MISSING_CONTENT):
        warnings.append("dropped_generic_missing_content")
        return None
    if missing_content.lower() == suggestion.lower():
        warnings.append("dropped_missing_content_duplicate_suggestion")
        return None

    cleaned["confidence"] = _clean_confidence(cleaned.get("confidence"), default=0.6)
    cleaned["recommended_location"] = _clean_optional_text(
        cleaned.get("recommended_location")
    )
    cleaned["priority"] = _clean_severity(
        cleaned.get("priority"),
        default=SignalSeverity.MEDIUM,
    ).value
    return cleaned


def normalize_recommendation_category(
    raw_category: object,
    *,
    fallback_text: str,
) -> tuple[RecommendationCategory, bool]:
    """Return a valid category and whether a copied category list was detected."""

    if isinstance(raw_category, RecommendationCategory):
        return raw_category, False

    normalized = normalize_whitespace(str(raw_category or "")).lower()
    copied_category_list = COPIED_CATEGORY_SEPARATOR in normalized
    try:
        return RecommendationCategory(normalized), copied_category_list
    except ValueError:
        inferred = infer_recommendation_category(fallback_text)
        return inferred, copied_category_list


def infer_recommendation_category(text: str) -> RecommendationCategory:
    """Infer a recommendation category from issue/change/reason text."""

    haystack = normalize_whitespace(text).lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return RecommendationCategory.OTHER


def _normalize_string_fields(item: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(item)
    for key, value in list(cleaned.items()):
        if isinstance(value, str):
            cleaned[key] = normalize_whitespace(value)
    return cleaned


def _missing_required_text(
    item: dict[str, Any],
    required_fields: tuple[str, ...],
) -> bool:
    return any(
        not normalize_whitespace(str(item.get(field) or ""))
        for field in required_fields
    )


def _clean_confidence(value: object, *, default: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(confidence, 1.0))


def _clean_severity(value: object, *, default: SignalSeverity) -> SignalSeverity:
    normalized = normalize_whitespace(str(value or "")).lower()
    try:
        return SignalSeverity(normalized)
    except ValueError:
        return default


def _clean_optional_text(value: object) -> str | None:
    cleaned = normalize_whitespace(str(value or ""))
    return cleaned or None


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)
