from app.services.fact_constants import (
    ALLOWED_FACT_TYPES,
    ALLOWED_STATUSES,
    MAX_AI_PROMPT_CONTENT_CHARS,
)


def build_ai_fact_prompt(article):
    analysis = article.get("analysis", {})
    content = article.get("content_preview") or article.get("content") or ""
    limited_content = content[:MAX_AI_PROMPT_CONTENT_CHARS]

    return f"""
You are a nuclear industry fact extraction system.

Goal:
Extract only verifiable nuclear industry facts from the article. Do not summarize
the article. A Fact must describe something that happened, was announced,
approved, delayed, funded, proposed, tested, built, operated, or otherwise
changed in the nuclear industry.

Do not extract:
- opinions
- speculation
- background-only explanations
- unsupported market trends
- duplicate facts with only wording changes
- countries, organizations, or technologies not present in the article

Split facts when subject/action/object or status differs. Return JSON only.
If there are no clear facts, return {{"article_id": {article.get("id")}, "facts": []}}.

Allowed fact_type values:
{", ".join(sorted(ALLOWED_FACT_TYPES))}

Allowed status values:
{", ".join(sorted(ALLOWED_STATUSES))}

Each fact must include evidence_sentence copied from or closely grounded in the
article text. Use lower confidence when evidence is weak.

Article:
- article_id: {article.get("id")}
- title: {article.get("title")}
- published: {article.get("published")}
- rule_country: {analysis.get("country")}
- rule_technology: {analysis.get("technology")}
- rule_organization: {analysis.get("organization")}
- rule_category: {analysis.get("category")}
- summary: {analysis.get("summary")}
- content: {limited_content}

Return this JSON shape:
{{
  "article_id": {article.get("id")},
  "facts": [
    {{
      "subject": "...",
      "action": "...",
      "object": "...",
      "fact_type": "technology",
      "status": "proposed",
      "country": "USA",
      "technology": ["SMR"],
      "organization": ["DOE"],
      "category": "Technology",
      "importance": 3,
      "confidence": 0.75,
      "summary": "...",
      "evidence_sentence": "..."
    }}
  ]
}}
""".strip()

