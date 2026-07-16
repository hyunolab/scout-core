import hashlib
import json

from app.services.ai_fact_parser import validate_evidence_sentence
from app.services.fact_constants import ALLOWED_FACT_TYPES, ALLOWED_STATUSES
from app.services.fact_extraction import normalize_text

AI_EXTRACTION_VERSION = "ai-schema-v1"


def _canonical_candidate_payload(article_id, recommended_source, facts, model_name=None):
    return {
        "article_id": article_id,
        "recommended_source": recommended_source,
        "facts": facts,
        "extraction_version": AI_EXTRACTION_VERSION,
        "model_name": model_name,
    }


def generate_candidate_id(article_id, recommended_source, facts, model_name=None):
    payload = _canonical_candidate_payload(
        article_id,
        recommended_source,
        facts,
        model_name=model_name,
    )
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:24]
    return f"ai-candidate-{article_id}-{digest}"


def build_commit_candidate(article_id, recommended_source, facts, model_name=None):
    return {
        "candidate_id": generate_candidate_id(
            article_id,
            recommended_source,
            facts,
            model_name=model_name,
        ),
        "recommended_source": recommended_source,
        "facts": facts,
        "extraction_version": AI_EXTRACTION_VERSION,
        "model_name": model_name,
    }


def verify_candidate_id(article_id, candidate):
    expected = generate_candidate_id(
        article_id,
        candidate.get("recommended_source"),
        candidate.get("facts", []),
        model_name=candidate.get("model_name"),
    )
    return candidate.get("candidate_id") == expected


def validate_commit_fact(article, fact, allow_warning=False):
    errors = []
    warnings = []

    for field in ["subject", "action", "object", "summary", "evidence_sentence"]:
        if not normalize_text(fact.get(field)):
            errors.append(f"missing_{field}")

    fact_type = str(fact.get("fact_type", "")).strip().lower()
    if fact_type not in ALLOWED_FACT_TYPES:
        errors.append("invalid_fact_type")

    status = str(fact.get("status", "")).strip().lower()
    if status not in ALLOWED_STATUSES:
        errors.append("invalid_status")

    confidence = fact.get("confidence", 0)
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        errors.append("invalid_confidence")

    importance = fact.get("importance", 0)
    if not isinstance(importance, int) or importance < 1 or importance > 5:
        errors.append("invalid_importance")

    evidence_result = validate_evidence_sentence(
        article,
        fact.get("evidence_sentence", ""),
    )
    validation_status = evidence_result["status"]
    validation_errors = list(evidence_result["errors"])

    if validation_status == "invalid":
        errors.extend(validation_errors)
    if validation_status == "warning":
        warnings.extend(validation_errors)
        if not allow_warning:
            errors.append("warning_evidence_not_allowed")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "validation_status": validation_status,
        "validation_errors": validation_errors,
    }

