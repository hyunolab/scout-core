import sqlite3

from app.database.database import get_connection
from app.database.fact_repository import ensure_facts_schema
from app.services.timeline_dates import utc_now_iso


def _active_fact_filter(include_merged=False):
    if include_merged:
        return "1 = 1"
    return "(f.merge_status IS NULL OR f.merge_status = 'active')"


def get_active_facts_with_articles(limit=10000, include_merged=False):
    ensure_facts_schema()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT
            f.*,
            af.article_id,
            a.title AS article_title,
            a.link AS article_link,
            a.published AS article_published
        FROM facts f
        LEFT JOIN article_facts af ON af.fact_id = f.id
        LEFT JOIN articles a ON a.id = af.article_id
        WHERE f.evidence_count > 0
          AND {_active_fact_filter(include_merged)}
        ORDER BY f.importance DESC, f.last_seen_at DESC, f.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()

    facts_by_id = {}
    for row in rows:
        fact_id = row["id"]
        if fact_id not in facts_by_id:
            fact = {
                key: row[key]
                for key in row.keys()
                if not key.startswith("article_")
            }
            fact["linked_articles"] = []
            facts_by_id[fact_id] = fact

        if row["article_id"] is not None:
            facts_by_id[fact_id]["linked_articles"].append(
                {
                    "id": row["article_id"],
                    "title": row["article_title"],
                    "link": row["article_link"],
                    "published": row["article_published"],
                }
            )

    return list(facts_by_id.values())


def update_fact_event_date(
    fact_id,
    event_date,
    date_precision,
    date_source,
    event_date_confidence=None,
):
    ensure_facts_schema()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE facts
        SET
            event_date = ?,
            date_precision = ?,
            date_source = ?,
            event_date_confidence = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            event_date,
            date_precision,
            date_source,
            event_date_confidence,
            utc_now_iso(),
            fact_id,
        ),
    )
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed
