import logging
import json

from fastapi import APIRouter, Body, HTTPException

from app.database.fact_repository import (
    backfill_facts_from_articles,
    generate_fact_key,
    get_article_for_fact_preview,
    get_active_fact_by_id,
    get_all_active_facts,
    get_candidate_facts_for_dedup,
    get_fact_by_id,
    get_fact_evidence_summary,
    get_facts,
    find_fact_by_key,
    link_article_fact,
    rebuild_facts_from_articles,
    update_article_fact_metadata,
    upsert_fact,
)
from app.services.ai_fact_client import extract_facts_with_ai
from app.services.ai_fact_commit import (
    AI_EXTRACTION_VERSION,
    build_commit_candidate,
    validate_commit_fact,
    verify_candidate_id,
)
from app.services.ai_fact_parser import parse_ai_fact_response
from app.services.ai_fact_prompt import build_ai_fact_prompt
from app.services.fact_extraction import build_candidate_fact
from app.services.fact_deduplication import (
    build_dedup_preview,
    classify_duplicate_candidate,
    scan_all_duplicate_candidates,
)
from app.services.fact_normalization import build_canonical_fact_signature
from app.services.fact_quality import (
    evaluate_rule_fact_quality,
    should_use_ai_extraction,
)
from app.services.fact_result_comparison import compare_rule_and_ai_facts
from app.services.fact_merge import (
    build_merge_preview,
    commit_fact_merge,
    get_merge_audit,
    list_merge_audits,
    rollback_fact_merge,
)

router = APIRouter(
    prefix="/api/v1/facts",
    tags=["Facts"],
)

logger = logging.getLogger(__name__)


@router.get("")
def list_facts(
    limit: int = 50,
    technology: str = None,
    country: str = None,
    organization: str = None,
    fact_type: str = None,
    status: str = None,
    include_orphans: bool = False,
    include_merged: bool = False,
):
    try:
        return get_facts(
            limit=limit,
            technology=technology,
            country=country,
            organization=organization,
            fact_type=fact_type,
            status=status,
            include_orphans=include_orphans,
            include_merged=include_merged,
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load facts: {error}",
        ) from error


@router.post("/ai-preview/{article_id}")
def preview_ai_fact_extraction(
    article_id: int,
    use_mock: bool = False,
    force_ai: bool = False,
):
    return _build_ai_preview(
        article_id=article_id,
        use_mock=use_mock,
        force_ai=force_ai,
    )


def _build_ai_preview(article_id, use_mock=False, force_ai=False):
    article = get_article_for_fact_preview(article_id)
    if article is None:
        raise HTTPException(
            status_code=404,
            detail=f"Article {article_id} not found",
        )

    rule_fact = build_candidate_fact(article)
    rule_fact["fact_key"] = generate_fact_key(rule_fact)
    rule_quality = evaluate_rule_fact_quality(rule_fact)
    ai_decision = should_use_ai_extraction(article, [rule_fact])
    prompt = build_ai_fact_prompt(article)

    should_call_ai = force_ai or use_mock or ai_decision["use_ai"]
    if should_call_ai:
        ai_response = extract_facts_with_ai(
            article,
            dry_run=True,
            use_mock=use_mock,
        )
    else:
        ai_response = {
            "enabled": False,
            "status": "not_needed",
            "message": "Rule extraction quality is sufficient.",
            "model_name": None,
            "usage": None,
            "raw_response": None,
        }

    ai_facts = []
    parser_result = {
        "valid_facts": [],
        "warnings": [],
        "errors": [],
        "raw_payload": None,
    }
    if ai_response.get("raw_response"):
        parser_result = parse_ai_fact_response(
            ai_response["raw_response"],
            article,
        )
        ai_facts = parser_result["valid_facts"]

    comparison = compare_rule_and_ai_facts([rule_fact], ai_facts)
    recommended_facts = comparison["recommended_facts"]
    commit_candidate = build_commit_candidate(
        article_id,
        comparison["recommended_source"],
        recommended_facts,
        model_name=ai_response.get("model_name"),
    )

    logger.info(
        "AI fact preview article_id=%s use_ai=%s validation_errors=%s",
        article_id,
        ai_decision["use_ai"],
        len(parser_result["errors"]),
    )

    return {
        "article_id": article_id,
        "rule_result": {
            "facts": [rule_fact],
            "quality_score": rule_quality["score"],
            "quality_reasons": rule_quality["reasons"],
        },
        "ai_decision": ai_decision,
        "ai_result": {
            "status": ai_response["status"],
            "enabled": ai_response["enabled"],
            "message": ai_response["message"],
            "model_name": ai_response.get("model_name"),
            "usage": ai_response.get("usage"),
            "facts": ai_facts,
            "warnings": parser_result["warnings"],
            "errors": parser_result["errors"],
        },
        "comparison": comparison,
        "commit_candidate": commit_candidate,
        "prompt": {
            "designed": True,
            "length": len(prompt),
            "max_content_chars": 10000,
        },
        "database_modified": False,
    }


@router.post("/ai-preview-batch")
def preview_ai_fact_extraction_batch(payload: dict = Body(...)):
    article_ids = payload.get("article_ids", [])
    if len(article_ids) > 5:
        raise HTTPException(
            status_code=400,
            detail="Batch preview supports at most 5 articles.",
        )

    results = []
    for article_id in article_ids:
        try:
            results.append(
                {
                    "article_id": article_id,
                    "status": "ok",
                    "result": _build_ai_preview(
                        article_id=article_id,
                        use_mock=payload.get("use_mock", False),
                        force_ai=payload.get("force_ai", False),
                    ),
                }
            )
        except HTTPException as error:
            results.append(
                {
                    "article_id": article_id,
                    "status": "error",
                    "detail": error.detail,
                }
            )

    return {
        "count": len(results),
        "database_modified": False,
        "results": results,
    }


@router.get("/dedup-preview/{fact_id}")
def preview_fact_deduplication(
    fact_id: int,
    limit: int = 20,
    min_score: float = 0.5,
    include_different: bool = False,
):
    base_fact = get_active_fact_by_id(fact_id)
    if base_fact is None:
        raise HTTPException(
            status_code=404,
            detail=f"Active fact {fact_id} not found",
        )

    candidate_facts = get_candidate_facts_for_dedup(
        base_fact,
        limit=limit,
        include_orphans=False,
    )
    preview = build_dedup_preview(
        base_fact,
        candidate_facts,
        min_score=min_score,
        include_different=include_different,
    )
    preview["evidence_summary"] = get_fact_evidence_summary(fact_id)
    return preview


@router.get("/dedup-scan")
def scan_fact_deduplication(
    min_score: float = 0.72,
    limit: int = 100,
    include_orphans: bool = False,
):
    facts = get_all_active_facts(
        limit=1000,
        include_orphans=include_orphans,
    )
    return scan_all_duplicate_candidates(
        facts,
        min_score=min_score,
        limit=limit,
    )


@router.post("/dedup-compare")
def compare_fact_deduplication(payload: dict = Body(...)):
    fact_a = payload.get("fact_a")
    fact_b = payload.get("fact_b")
    if not isinstance(fact_a, dict) or not isinstance(fact_b, dict):
        raise HTTPException(
            status_code=400,
            detail="fact_a and fact_b are required objects",
        )

    classification = classify_duplicate_candidate(fact_a, fact_b)
    return {
        "canonical_a": build_canonical_fact_signature(fact_a),
        "canonical_b": build_canonical_fact_signature(fact_b),
        "similarity": classification["similarity"],
        "classification": classification["classification"],
        "merge_recommended": classification["merge_recommended"],
        "auto_merge_eligible": classification["auto_merge_eligible"],
        "reasons": classification["reasons"],
        "conflicts": classification["conflicts"],
        "database_modified": False,
    }


@router.post("/merge-preview")
def preview_fact_merge(
    payload: dict = Body(...),
    force_possible: bool = False,
    force_conflict: bool = False,
):
    result = build_merge_preview(
        payload.get("fact_id_a"),
        payload.get("fact_id_b"),
        force_possible=force_possible,
        force_conflict=force_conflict,
    )
    if result.get("error") == "fact_not_found":
        raise HTTPException(status_code=404, detail="fact_not_found")
    return result


@router.post("/merge-commit")
def commit_fact_merge_endpoint(
    payload: dict = Body(...),
    force_possible: bool = False,
    force_conflict: bool = False,
):
    result = commit_fact_merge(
        payload,
        force_possible=force_possible,
        force_conflict=force_conflict,
    )
    if result.get("status") == "rejected":
        status_code = 409 if result.get("error") == "merge_not_allowed" else 400
        raise HTTPException(status_code=status_code, detail=result)
    return result


@router.post("/merge-rollback/{merge_id}")
def rollback_fact_merge_endpoint(merge_id: str, payload: dict = Body(default={})):
    result = rollback_fact_merge(
        merge_id,
        reason=payload.get("reason") if payload else None,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="merge_audit_not_found")
    if result.get("status") == "rejected":
        raise HTTPException(status_code=409, detail=result)
    return result


@router.get("/merge-audits")
def read_merge_audits(
    status: str = None,
    fact_id: int = None,
    limit: int = 50,
):
    return list_merge_audits(
        status=status,
        fact_id=fact_id,
        limit=limit,
    )


@router.get("/merge-audits/{merge_id}")
def read_merge_audit(merge_id: str):
    audit = get_merge_audit(merge_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="merge_audit_not_found")
    return audit


@router.post("/ai-commit/{article_id}")
def commit_ai_fact_extraction(
    article_id: int,
    payload: dict = Body(...),
    allow_warning: bool = False,
):
    article = get_article_for_fact_preview(article_id)
    if article is None:
        raise HTTPException(
            status_code=404,
            detail=f"Article {article_id} not found",
        )

    if not verify_candidate_id(article_id, payload):
        raise HTTPException(
            status_code=400,
            detail="candidate_hash_mismatch",
        )

    facts = payload.get("facts", [])
    if not isinstance(facts, list):
        raise HTTPException(
            status_code=400,
            detail="commit_validation_failed",
        )

    model_name = payload.get("model_name")
    recommended_source = payload.get("recommended_source", "ai")
    extraction_method = "ai" if recommended_source == "ai" else "hybrid"

    facts_committed = 0
    facts_created = 0
    facts_reused = 0
    links_created = 0
    links_existing = 0
    skipped_invalid = 0
    committed_facts = []
    skipped = []

    for fact in facts:
        validation = validate_commit_fact(
            article,
            fact,
            allow_warning=allow_warning,
        )
        if not validation["valid"]:
            skipped_invalid += 1
            skipped.append(
                {
                    "fact": fact,
                    "errors": validation["errors"],
                }
            )
            continue

        fact_to_save = {
            **fact,
            "technology": fact.get("technology") or "unknown",
            "organization": fact.get("organization") or "unknown",
            "evidence_count": 1,
            "first_seen_at": article.get("published"),
            "last_seen_at": article.get("published"),
        }
        fact_to_save["fact_key"] = generate_fact_key(fact_to_save)
        existing_fact = find_fact_by_key(fact_to_save["fact_key"])
        fact_id = upsert_fact(fact_to_save)
        if existing_fact is None:
            facts_created += 1
        else:
            facts_reused += 1

        inserted = link_article_fact(
            article_id,
            fact_id,
            evidence_sentence=fact.get("evidence_sentence"),
            extraction_method=extraction_method,
            extraction_confidence=fact.get("confidence"),
            extraction_version=AI_EXTRACTION_VERSION,
            model_name=model_name,
            validation_status=validation["validation_status"],
            validation_errors=json.dumps(validation["validation_errors"]),
        )
        if inserted:
            links_created += 1
        else:
            links_existing += 1
            update_article_fact_metadata(
                article_id,
                fact_id,
                evidence_sentence=fact.get("evidence_sentence"),
                extraction_method=extraction_method,
                extraction_confidence=fact.get("confidence"),
                extraction_version=AI_EXTRACTION_VERSION,
                model_name=model_name,
                validation_status=validation["validation_status"],
                validation_errors=json.dumps(validation["validation_errors"]),
            )

        facts_committed += 1
        committed_facts.append(
            {
                "fact_id": fact_id,
                "fact_key": fact_to_save["fact_key"],
                "validation_status": validation["validation_status"],
            }
        )

    if facts and facts_committed == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error_type": "commit_validation_failed",
                "skipped": skipped,
            },
        )

    return {
        "article_id": article_id,
        "facts_received": len(facts),
        "facts_committed": facts_committed,
        "facts_created": facts_created,
        "facts_reused": facts_reused,
        "links_created": links_created,
        "links_existing": links_existing,
        "skipped_invalid": skipped_invalid,
        "committed_facts": committed_facts,
        "skipped": skipped,
    }


@router.post("/rebuild-rules")
def rebuild_facts_with_rules(dry_run: bool = True):
    try:
        result = rebuild_facts_from_articles(dry_run=dry_run)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to rebuild facts with rules: {error}",
        ) from error

    return {
        "message": "Fact rules rebuild preview" if dry_run else "Facts rebuilt",
        **result,
    }


@router.post("/backfill")
def backfill_facts():
    try:
        result = backfill_facts_from_articles()
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to backfill facts: {error}",
        ) from error

    return {
        "message": "Facts backfilled",
        **result,
    }


@router.get("/{fact_id}")
def read_fact(fact_id: int):
    try:
        fact = get_fact_by_id(fact_id)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load fact {fact_id}: {error}",
        ) from error

    if fact is None:
        raise HTTPException(
            status_code=404,
            detail=f"Fact {fact_id} not found",
        )

    return fact
