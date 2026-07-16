import json
import re

from pydantic import ValidationError

from app.services.ai_fact_schema import AIFactExtraction
from app.services.fact_extraction import normalize_for_match, normalize_text


def _strip_json_code_block(raw_response):
    text = raw_response.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def _join_unique(values):
    unique = []
    for value in values:
        clean_value = normalize_text(value)
        if clean_value and clean_value not in unique:
            unique.append(clean_value)
    return "; ".join(unique) if unique else "unknown"


def validate_evidence_sentence(article, evidence_sentence):
    if not evidence_sentence or not evidence_sentence.strip():
        return {
            "status": "invalid",
            "errors": ["missing_evidence_sentence"],
        }

    evidence = normalize_text(evidence_sentence)
    article_text = normalize_text(
        " ".join(
            [
                article.get("title") or "",
                article.get("analysis", {}).get("summary") or "",
                article.get("content_preview") or article.get("content") or "",
            ]
        )
    )

    if normalize_for_match(evidence) in normalize_for_match(article_text):
        return {
            "status": "valid",
            "errors": [],
        }

    evidence_tokens = {
        token
        for token in normalize_for_match(evidence).split()
        if len(token) > 3
    }
    article_tokens = {
        token
        for token in normalize_for_match(article_text).split()
        if len(token) > 3
    }

    if not evidence_tokens:
        return {
            "status": "invalid",
            "errors": ["empty_evidence_tokens"],
        }

    overlap = len(evidence_tokens & article_tokens) / len(evidence_tokens)
    if overlap >= 0.6:
        return {
            "status": "warning",
            "errors": ["evidence_sentence_not_exact_match"],
        }

    return {
        "status": "invalid",
        "errors": ["evidence_sentence_not_supported"],
    }


def _normalize_fact(fact, article):
    evidence_result = validate_evidence_sentence(
        article,
        fact.evidence_sentence,
    )
    errors = list(evidence_result["errors"])

    return {
        "subject": fact.subject.strip(),
        "action": fact.action.strip().lower().replace(" ", "_"),
        "object": fact.object.strip(),
        "fact_type": fact.fact_type,
        "status": fact.status,
        "country": fact.country.strip() if fact.country else "unknown",
        "technology": _join_unique(fact.technology),
        "organization": _join_unique(fact.organization),
        "category": fact.category.strip(),
        "importance": fact.importance,
        "confidence": round(fact.confidence, 2),
        "summary": fact.summary.strip(),
        "evidence_sentence": fact.evidence_sentence.strip(),
        "validation_status": evidence_result["status"],
        "validation_errors": errors,
    }


def parse_ai_fact_response(raw_response, article):
    result = {
        "valid_facts": [],
        "warnings": [],
        "errors": [],
        "raw_payload": None,
    }

    try:
        payload = json.loads(_strip_json_code_block(raw_response))
    except json.JSONDecodeError as error:
        result["errors"].append(f"json_parse_error: {error}")
        return result

    result["raw_payload"] = payload

    try:
        extraction = AIFactExtraction.model_validate(payload)
    except ValidationError as error:
        result["errors"].append(error.errors())
        return result

    seen_keys = set()
    for fact in extraction.facts:
        normalized_fact = _normalize_fact(fact, article)
        unique_key = (
            normalized_fact["subject"],
            normalized_fact["action"],
            normalized_fact["object"],
            normalized_fact["technology"],
            normalized_fact["country"],
        )
        if unique_key in seen_keys:
            result["warnings"].append("duplicate_ai_fact_removed")
            continue
        seen_keys.add(unique_key)

        if normalized_fact["validation_status"] == "invalid":
            result["errors"].append(
                {
                    "fact": normalized_fact,
                    "errors": normalized_fact["validation_errors"],
                }
            )
            continue
        if normalized_fact["validation_status"] == "warning":
            result["warnings"].append(
                {
                    "fact": normalized_fact,
                    "warnings": normalized_fact["validation_errors"],
                }
            )

        result["valid_facts"].append(normalized_fact)

    return result

