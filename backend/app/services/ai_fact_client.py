import json
import logging
import os

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from app.services.ai_fact_prompt import build_ai_fact_prompt

logger = logging.getLogger(__name__)


def _mock_response_for_article(article):
    title = article.get("title") or ""

    if "DOE approves TRISO fuel demonstration" in title:
        return {
            "article_id": article.get("id"),
            "facts": [
                {
                    "subject": "DOE",
                    "action": "approved",
                    "object": "TRISO fuel demonstration",
                    "fact_type": "regulation",
                    "status": "approved",
                    "country": "USA",
                    "technology": ["TRISO"],
                    "organization": ["DOE"],
                    "category": "Regulation",
                    "importance": 4,
                    "confidence": 0.92,
                    "summary": "DOE approved a TRISO fuel demonstration.",
                    "evidence_sentence": "DOE approves TRISO fuel demonstration",
                }
            ],
        }

    if "Holtec and EDF submit UK SMR project proposal" in title:
        return {
            "article_id": article.get("id"),
            "facts": [
                {
                    "subject": "Holtec; EDF",
                    "action": "submitted",
                    "object": "UK SMR project proposal",
                    "fact_type": "technology",
                    "status": "proposed",
                    "country": "UK",
                    "technology": ["SMR"],
                    "organization": ["Holtec", "EDF"],
                    "category": "Technology",
                    "importance": 3,
                    "confidence": 0.88,
                    "summary": "Holtec and EDF submitted a UK SMR project proposal.",
                    "evidence_sentence": "Holtec and EDF submit UK SMR project proposal",
                },
                {
                    "subject": "Holtec; EDF",
                    "action": "announced",
                    "object": "development partnership",
                    "fact_type": "technology",
                    "status": "in_progress",
                    "country": "UK",
                    "technology": ["SMR"],
                    "organization": ["Holtec", "EDF"],
                    "category": "Technology",
                    "importance": 3,
                    "confidence": 0.74,
                    "summary": "Holtec and EDF announced a development partnership.",
                    "evidence_sentence": "announce a development partnership",
                },
            ],
        }

    if "background" in title.lower():
        return {
            "article_id": article.get("id"),
            "facts": [],
        }

    return {
        "article_id": article.get("id"),
        "facts": [
            {
                "subject": "Global nuclear industry",
                "action": "reported",
                "object": title,
                "fact_type": "industry_signal",
                "status": "unknown",
                "country": "unknown",
                "technology": [],
                "organization": [],
                "category": "Industry Signal",
                "importance": 3,
                "confidence": 0.45,
                "summary": title,
                "evidence_sentence": title,
            }
        ],
    }


def _get_usage(response):
    usage = getattr(response, "usage", None)
    if usage is None:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    total_tokens = getattr(usage, "total_tokens", input_tokens + output_tokens) or 0
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def extract_facts_with_ai(article, dry_run=True, use_mock=False):
    enabled = os.getenv("ENABLE_AI_FACT_EXTRACTION", "false").lower() == "true"
    if not enabled and not use_mock:
        return {
            "enabled": False,
            "status": "disabled",
            "error_type": "ai_disabled",
            "message": "AI Fact Extraction is disabled.",
            "model_name": None,
            "usage": None,
            "raw_response": None,
        }

    if use_mock:
        payload = _mock_response_for_article(article)
        return {
            "enabled": enabled,
            "status": "mock",
            "message": "Mock AI Fact Extraction response.",
            "model_name": "mock-ai-fact-model",
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
            "raw_response": json.dumps(payload),
        }

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "enabled": True,
            "status": "config_error",
            "error_type": "missing_api_key",
            "message": "OPENAI_API_KEY is not configured.",
            "model_name": None,
            "usage": None,
            "raw_response": None,
        }

    model_name = os.getenv("AI_FACT_MODEL", "gpt-4.1-mini")
    max_output_tokens = int(os.getenv("AI_FACT_MAX_OUTPUT_TOKENS", "1800"))
    timeout_seconds = float(os.getenv("AI_FACT_TIMEOUT_SECONDS", "20"))
    prompt = build_ai_fact_prompt(article)
    client = OpenAI(api_key=api_key, timeout=timeout_seconds)

    try:
        response = client.responses.create(
            model=model_name,
            input=prompt,
            max_output_tokens=max_output_tokens,
            text={"format": {"type": "json_object"}},
            store=False,
            timeout=timeout_seconds,
        )
    except APITimeoutError as error:
        logger.warning("AI fact extraction timeout article_id=%s", article.get("id"))
        return {
            "enabled": True,
            "status": "error",
            "error_type": "timeout",
            "message": str(error),
            "model_name": model_name,
            "usage": None,
            "raw_response": None,
        }
    except APIStatusError as error:
        error_type = "rate_limit" if error.status_code == 429 else "api_status_error"
        logger.warning(
            "AI fact extraction API error article_id=%s status=%s",
            article.get("id"),
            error.status_code,
        )
        return {
            "enabled": True,
            "status": "error",
            "error_type": error_type,
            "message": str(error),
            "model_name": model_name,
            "usage": None,
            "raw_response": None,
        }
    except APIConnectionError as error:
        logger.warning("AI fact extraction connection error article_id=%s", article.get("id"))
        return {
            "enabled": True,
            "status": "error",
            "error_type": "connection_error",
            "message": str(error),
            "model_name": model_name,
            "usage": None,
            "raw_response": None,
        }
    except Exception as error:
        logger.warning("AI fact extraction error article_id=%s", article.get("id"))
        return {
            "enabled": True,
            "status": "error",
            "error_type": "unknown_error",
            "message": str(error),
            "model_name": model_name,
            "usage": None,
            "raw_response": None,
        }

    raw_response = getattr(response, "output_text", None)
    if raw_response is None:
        raw_response = str(response)

    return {
        "enabled": True,
        "status": "success",
        "model_name": model_name,
        "usage": _get_usage(response),
        "raw_response": raw_response,
    }
