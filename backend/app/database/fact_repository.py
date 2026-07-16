import hashlib
import sqlite3
from datetime import datetime, timezone

from app.database.database import get_connection
from app.services.fact_extraction import extract_candidate_fact_from_article


FACT_COLUMNS = {
    "fact_key": "TEXT",
    "subject": "TEXT",
    "action": "TEXT",
    "object": "TEXT",
    "fact_type": "TEXT",
    "status": "TEXT",
    "country": "TEXT",
    "technology": "TEXT",
    "organization": "TEXT",
    "category": "TEXT",
    "importance": "INTEGER",
    "confidence": "REAL",
    "summary": "TEXT",
    "evidence_count": "INTEGER",
    "first_seen_at": "TEXT",
    "last_seen_at": "TEXT",
    "event_date": "TEXT",
    "date_precision": "TEXT",
    "date_source": "TEXT",
    "event_date_end": "TEXT",
    "event_date_confidence": "REAL",
    "merge_status": "TEXT",
    "merged_into_fact_id": "INTEGER",
    "merged_at": "TEXT",
    "merge_reason": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}

ARTICLE_FACT_COLUMNS = {
    "article_id": "INTEGER",
    "fact_id": "INTEGER",
    "evidence_sentence": "TEXT",
    "extraction_method": "TEXT",
    "extraction_confidence": "REAL",
    "extraction_version": "TEXT",
    "model_name": "TEXT",
    "validation_status": "TEXT",
    "validation_errors": "TEXT",
    "created_at": "TEXT",
}


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_columns(cursor, table_name, columns):
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for column_name, column_type in columns.items():
        if column_name not in existing_columns:
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )


def ensure_facts_schema():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_key TEXT UNIQUE,

            subject TEXT,
            action TEXT,
            object TEXT,

            fact_type TEXT,
            status TEXT,

            country TEXT,
            technology TEXT,
            organization TEXT,
            category TEXT,

            importance INTEGER,
            confidence REAL,

            summary TEXT,

            evidence_count INTEGER,
            first_seen_at TEXT,
            last_seen_at TEXT,
            event_date TEXT,
            date_precision TEXT,
            date_source TEXT,
            event_date_end TEXT,
            event_date_confidence REAL,
            merge_status TEXT,
            merged_into_fact_id INTEGER,
            merged_at TEXT,
            merge_reason TEXT,

            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS article_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER,
            fact_id INTEGER,
            evidence_sentence TEXT,
            extraction_method TEXT,
            extraction_confidence REAL,
            extraction_version TEXT,
            model_name TEXT,
            validation_status TEXT,
            validation_errors TEXT,
            created_at TEXT,
            UNIQUE(article_id, fact_id)
        )
        """
    )

    _ensure_columns(cursor, "facts", FACT_COLUMNS)
    _ensure_columns(cursor, "article_facts", ARTICLE_FACT_COLUMNS)

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fact_merge_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merge_id TEXT UNIQUE,
            survivor_fact_id INTEGER,
            source_fact_id INTEGER,
            status TEXT,
            similarity_score REAL,
            classification TEXT,
            reason_codes TEXT,
            conflicts TEXT,
            survivor_snapshot TEXT,
            source_snapshot TEXT,
            links_before TEXT,
            links_after TEXT,
            created_at TEXT,
            rolled_back_at TEXT,
            rollback_reason TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_fact_key
        ON facts(fact_key)
        """
    )
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_article_facts_unique_pair
        ON article_facts(article_id, fact_id)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_facts_fact_type
        ON facts(fact_type)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_facts_country
        ON facts(country)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_facts_technology
        ON facts(technology)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_facts_merge_status
        ON facts(merge_status)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_facts_event_date
        ON facts(event_date)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_article_facts_article_id
        ON article_facts(article_id)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_article_facts_fact_id
        ON article_facts(fact_id)
        """
    )

    conn.commit()
    conn.close()


def get_fact_tables_status():
    ensure_facts_schema()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM facts")
    facts_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM article_facts")
    article_facts_count = cursor.fetchone()[0]

    conn.close()

    return {
        "facts": facts_count,
        "article_facts": article_facts_count,
    }


def find_fact_by_key(fact_key):
    ensure_facts_schema()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM facts
        WHERE fact_key = ?
        LIMIT 1
        """,
        (fact_key,),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return dict(row)


def _clean_fact_part(value):
    if value is None:
        return "unknown"

    parts = [
        part.strip()
        for part in str(value).split(";")
        if part.strip()
    ]
    if len(parts) > 1:
        normalized = ";".join(sorted(parts, key=str.lower))
    else:
        normalized = str(value).strip()

    normalized = normalized.lower()
    normalized = "".join(
        character if character.isalnum() else "-"
        for character in normalized
    )
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "unknown"


def generate_fact_key(fact):
    object_value = fact.get("object")
    if object_value and len(str(object_value)) > 90:
        digest = hashlib.sha1(str(object_value).encode("utf-8")).hexdigest()[:10]
        object_value = f"{str(object_value)[:70]} {digest}"

    parts = [
        fact.get("subject"),
        fact.get("action"),
        object_value,
        fact.get("technology"),
        fact.get("country"),
    ]
    return ":".join(_clean_fact_part(part) for part in parts)


def _row_to_fact(row):
    return dict(row)


def _count_fact_evidence(cursor, fact_id):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM article_facts
        WHERE fact_id = ?
        """,
        (fact_id,),
    )
    return cursor.fetchone()[0]


def _article_fact_exists(cursor, article_id, fact_id):
    cursor.execute(
        """
        SELECT 1
        FROM article_facts
        WHERE article_id = ?
          AND fact_id = ?
        LIMIT 1
        """,
        (article_id, fact_id),
    )
    return cursor.fetchone() is not None


def upsert_fact(fact):
    ensure_facts_schema()

    fact_key = fact.get("fact_key") or generate_fact_key(fact)
    now = utc_now_iso()
    first_seen_at = fact.get("first_seen_at") or now
    last_seen_at = fact.get("last_seen_at") or first_seen_at
    source_article_id = fact.get("source_article_id")

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM facts
        WHERE fact_key = ?
        LIMIT 1
        """,
        (fact_key,),
    )
    existing = cursor.fetchone()

    if existing is not None:
        fact_id = existing["id"]
        evidence_count = _count_fact_evidence(cursor, fact_id)
        if source_article_id and not _article_fact_exists(
            cursor,
            source_article_id,
            fact_id,
        ):
            evidence_count += 1

        cursor.execute(
            """
            UPDATE facts
            SET
                subject = ?,
                action = ?,
                object = ?,
                fact_type = ?,
                status = ?,
                country = ?,
                technology = ?,
                organization = ?,
                category = ?,
                importance = ?,
                confidence = ?,
                summary = ?,
                last_seen_at = ?,
                event_date = ?,
                date_precision = ?,
                date_source = ?,
                event_date_end = ?,
                event_date_confidence = ?,
                evidence_count = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                fact.get("subject", existing["subject"]),
                fact.get("action", existing["action"]),
                fact.get("object", existing["object"]),
                fact.get("fact_type", existing["fact_type"]),
                fact.get("status", existing["status"]),
                fact.get("country", existing["country"]),
                fact.get("technology", existing["technology"]),
                fact.get("organization", existing["organization"]),
                fact.get("category", existing["category"]),
                fact.get("importance", existing["importance"]),
                fact.get("confidence", existing["confidence"]),
                fact.get("summary", existing["summary"]),
                last_seen_at,
                fact.get("event_date", existing["event_date"]),
                fact.get("date_precision", existing["date_precision"]),
                fact.get("date_source", existing["date_source"]),
                fact.get("event_date_end", existing["event_date_end"]),
                fact.get("event_date_confidence", existing["event_date_confidence"]),
                evidence_count,
                now,
                fact_id,
            ),
        )
        conn.commit()
        conn.close()
        return fact_id

    cursor.execute(
        """
        INSERT INTO facts (
            fact_key,
            subject,
            action,
            object,
            fact_type,
            status,
            country,
            technology,
            organization,
            category,
            importance,
            confidence,
            summary,
            evidence_count,
            first_seen_at,
            last_seen_at,
            event_date,
            date_precision,
            date_source,
            event_date_end,
            event_date_confidence,
            created_at,
            updated_at,
            merge_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fact_key,
            fact.get("subject", "unknown"),
            fact.get("action", "changed"),
            fact.get("object", "unknown"),
            fact.get("fact_type", "unknown"),
            fact.get("status", "unknown"),
            fact.get("country", "unknown"),
            fact.get("technology", "unknown"),
            fact.get("organization", "unknown"),
            fact.get("category", "Unknown"),
            fact.get("importance", 3),
            fact.get("confidence", 0.4),
            fact.get("summary", ""),
            fact.get("evidence_count", 1),
            first_seen_at,
            last_seen_at,
            fact.get("event_date"),
            fact.get("date_precision"),
            fact.get("date_source"),
            fact.get("event_date_end"),
            fact.get("event_date_confidence"),
            now,
            now,
            fact.get("merge_status", "active"),
        ),
    )

    fact_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return fact_id


def link_article_fact(
    article_id,
    fact_id,
    evidence_sentence=None,
    extraction_method="rule",
    extraction_confidence=None,
    extraction_version="rule-v2",
    model_name=None,
    validation_status="valid",
    validation_errors=None,
):
    ensure_facts_schema()

    conn = get_connection()
    cursor = conn.cursor()
    now = utc_now_iso()

    cursor.execute(
        """
        INSERT OR IGNORE INTO article_facts (
            article_id,
            fact_id,
            evidence_sentence,
            extraction_method,
            extraction_confidence,
            extraction_version,
            model_name,
            validation_status,
            validation_errors,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article_id,
            fact_id,
            evidence_sentence,
            extraction_method,
            extraction_confidence,
            extraction_version,
            model_name,
            validation_status,
            validation_errors,
            now,
        ),
    )
    inserted = cursor.rowcount > 0
    evidence_count = _count_fact_evidence(cursor, fact_id)

    cursor.execute(
        """
        UPDATE facts
        SET
            evidence_count = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (evidence_count, now, fact_id),
    )

    conn.commit()
    conn.close()

    return inserted


def update_article_fact_metadata(
    article_id,
    fact_id,
    evidence_sentence=None,
    extraction_method=None,
    extraction_confidence=None,
    extraction_version=None,
    model_name=None,
    validation_status=None,
    validation_errors=None,
):
    ensure_facts_schema()

    updates = []
    values = []
    for column, value in [
        ("evidence_sentence", evidence_sentence),
        ("extraction_method", extraction_method),
        ("extraction_confidence", extraction_confidence),
        ("extraction_version", extraction_version),
        ("model_name", model_name),
        ("validation_status", validation_status),
        ("validation_errors", validation_errors),
    ]:
        if value is not None:
            updates.append(f"{column} = ?")
            values.append(value)

    if not updates:
        return False

    values.extend([article_id, fact_id])
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        UPDATE article_facts
        SET {", ".join(updates)}
        WHERE article_id = ?
          AND fact_id = ?
        """,
        values,
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return updated


def get_article_fact_links(article_id=None, fact_id=None):
    ensure_facts_schema()

    filters = []
    values = []
    if article_id is not None:
        filters.append("article_id = ?")
        values.append(article_id)
    if fact_id is not None:
        filters.append("fact_id = ?")
        values.append(fact_id)

    where_clause = ""
    if filters:
        where_clause = "WHERE " + " AND ".join(filters)

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT *
        FROM article_facts
        {where_clause}
        ORDER BY id ASC
        """,
        values,
    )
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_facts(
    limit=50,
    technology=None,
    country=None,
    organization=None,
    fact_type=None,
    status=None,
    include_orphans=False,
    include_merged=False,
):
    ensure_facts_schema()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    filters = []
    values = []
    for column, value in [
        ("technology", technology),
        ("country", country),
        ("organization", organization),
        ("fact_type", fact_type),
        ("status", status),
    ]:
        if value:
            filters.append(f"LOWER({column}) LIKE LOWER(?)")
            values.append(f"%{value}%")

    if not include_orphans:
        if include_merged:
            filters.append("(evidence_count > 0 OR merge_status = 'merged')")
        else:
            filters.append("evidence_count > 0")
    if not include_merged:
        filters.append("(merge_status IS NULL OR merge_status = 'active')")

    where_clause = ""
    if filters:
        where_clause = "WHERE " + " AND ".join(filters)

    values.append(limit)
    cursor.execute(
        f"""
        SELECT *
        FROM facts
        {where_clause}
        ORDER BY importance DESC, last_seen_at DESC, id DESC
        LIMIT ?
        """,
        values,
    )
    rows = cursor.fetchall()
    conn.close()

    return [_row_to_fact(row) for row in rows]


def get_fact_by_id(fact_id):
    ensure_facts_schema()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM facts
        WHERE id = ?
        LIMIT 1
        """,
        (fact_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return _row_to_fact(row)


def get_active_fact_by_id(fact_id):
    fact = get_fact_by_id(fact_id)
    if fact is None:
        return None
    if (fact.get("evidence_count") or 0) <= 0:
        return None
    return fact


def get_all_active_facts(limit=1000, include_orphans=False):
    return get_facts(limit=limit, include_orphans=include_orphans)


def get_candidate_facts_for_dedup(fact, limit=50, include_orphans=False):
    candidates = get_facts(limit=limit + 1, include_orphans=include_orphans)
    return [
        candidate
        for candidate in candidates
        if candidate["id"] != fact["id"]
    ][:limit]


def get_fact_evidence_summary(fact_id):
    ensure_facts_schema()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            f.evidence_count,
            f.first_seen_at,
            f.last_seen_at,
            af.article_id
        FROM facts f
        LEFT JOIN article_facts af ON af.fact_id = f.id
        WHERE f.id = ?
        ORDER BY af.article_id ASC
        """,
        (fact_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return None

    return {
        "evidence_count": rows[0]["evidence_count"],
        "article_ids": [
            row["article_id"]
            for row in rows
            if row["article_id"] is not None
        ],
        "first_seen_at": rows[0]["first_seen_at"],
        "last_seen_at": rows[0]["last_seen_at"],
    }


def _row_to_article(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "link": row["link"],
        "published": row["published"],
        "content_preview": row["content"],
        "event_key": row["event_key"],
        "analysis": {
            "country": row["country"],
            "organization": row["organization"],
            "technology": row["technology"],
            "category": row["category"],
            "importance": row["importance"],
            "summary": row["summary"],
            "impact": row["impact"],
        },
    }


def get_article_for_fact_preview(article_id):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM articles
        WHERE id = ?
        LIMIT 1
        """,
        (article_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return _row_to_article(row)


def backfill_facts_from_articles():
    ensure_facts_schema()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM articles
        ORDER BY id ASC
        """
    )
    article_rows = cursor.fetchall()
    conn.close()

    created_or_found = 0
    linked = 0
    facts = []

    for row in article_rows:
        article = _row_to_article(row)
        fact = extract_candidate_fact_from_article(article)
        fact["fact_key"] = generate_fact_key(fact)
        fact["source_article_id"] = article["id"]

        fact_id = upsert_fact(fact)
        if link_article_fact(
            article["id"],
            fact_id,
            evidence_sentence=article["title"],
            extraction_confidence=fact.get("confidence"),
        ):
            linked += 1

        saved_fact = get_fact_by_id(fact_id)
        facts.append(saved_fact)
        created_or_found += 1

    return {
        "articles_processed": len(article_rows),
        "facts_processed": created_or_found,
        "links_created": linked,
        "facts": facts,
    }


def _get_article_rows():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM articles
        ORDER BY id ASC
        """
    )
    rows = cursor.fetchall()
    conn.close()

    return rows


def _get_article_fact_keys():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT af.article_id, f.id AS fact_id, f.fact_key
        FROM article_facts af
        JOIN facts f ON f.id = af.fact_id
        """
    )
    rows = cursor.fetchall()
    conn.close()

    relations = {}
    for row in rows:
        relations.setdefault(row["article_id"], []).append(
            {
                "fact_id": row["fact_id"],
                "fact_key": row["fact_key"],
            }
        )

    return relations


def _get_orphan_fact_ids():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT f.id
        FROM facts f
        LEFT JOIN article_facts af ON af.fact_id = f.id
        WHERE af.id IS NULL
        ORDER BY f.id
        """
    )
    rows = cursor.fetchall()
    conn.close()

    return [row[0] for row in rows]


def _refresh_evidence_count(fact_id):
    conn = get_connection()
    cursor = conn.cursor()
    now = utc_now_iso()
    evidence_count = _count_fact_evidence(cursor, fact_id)

    cursor.execute(
        """
        UPDATE facts
        SET
            evidence_count = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (evidence_count, now, fact_id),
    )

    conn.commit()
    conn.close()


def rebuild_facts_from_articles(dry_run=True):
    ensure_facts_schema()

    article_rows = _get_article_rows()
    existing_relations = _get_article_fact_keys()
    current_fact_keys = {
        fact["fact_key"]
        for fact in get_facts(limit=10000, include_orphans=True)
    }

    candidates = []
    facts_to_create = 0
    facts_to_update = 0
    links_to_change = 0

    for row in article_rows:
        article = _row_to_article(row)
        fact = extract_candidate_fact_from_article(article)
        fact["fact_key"] = generate_fact_key(fact)
        fact["source_article_id"] = article["id"]

        article_relations = existing_relations.get(article["id"], [])
        existing_article_keys = {
            relation["fact_key"]
            for relation in article_relations
        }

        if fact["fact_key"] in current_fact_keys:
            facts_to_update += 1
        else:
            facts_to_create += 1

        if existing_article_keys != {fact["fact_key"]}:
            links_to_change += 1

        candidates.append(
            {
                "article_id": article["id"],
                "title": article["title"],
                "current_fact_keys": sorted(existing_article_keys),
                "candidate_fact": fact,
            }
        )

    if dry_run:
        return {
            "dry_run": True,
            "articles_processed": len(article_rows),
            "facts_to_create": facts_to_create,
            "facts_to_update": facts_to_update,
            "links_to_change": links_to_change,
            "orphan_fact_ids": _get_orphan_fact_ids(),
            "candidates": candidates,
        }

    changed_old_fact_ids = set()
    linked = 0
    facts = []

    for candidate in candidates:
        article_id = candidate["article_id"]
        fact = candidate["candidate_fact"]
        fact_id = upsert_fact(fact)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT fact_id
            FROM article_facts
            WHERE article_id = ?
              AND fact_id <> ?
            """,
            (article_id, fact_id),
        )
        changed_old_fact_ids.update(row[0] for row in cursor.fetchall())

        cursor.execute(
            """
            DELETE FROM article_facts
            WHERE article_id = ?
              AND fact_id <> ?
            """,
            (article_id, fact_id),
        )
        conn.commit()
        conn.close()

        if link_article_fact(
            article_id,
            fact_id,
            evidence_sentence=candidate["title"],
            extraction_confidence=fact.get("confidence"),
        ):
            linked += 1

        facts.append(get_fact_by_id(fact_id))

    for old_fact_id in changed_old_fact_ids:
        _refresh_evidence_count(old_fact_id)

    return {
        "dry_run": False,
        "articles_processed": len(article_rows),
        "facts_processed": len(facts),
        "links_created": linked,
        "links_to_change": links_to_change,
        "orphan_fact_ids": _get_orphan_fact_ids(),
        "facts": facts,
    }
