import hashlib
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from app.database.database import get_connection
from app.database.fact_repository import ensure_facts_schema
from app.services.fact_deduplication import classify_duplicate_candidate
from app.services.fact_normalization import normalize_fact_organization, normalize_fact_technology

MERGE_VERSION = "fact-merge-v1"
METHOD_PRIORITY = {"manual": 5, "hybrid": 4, "ai": 3, "rule": 2, None: 1, "": 1}
VALIDATION_PRIORITY = {"valid": 4, "warning": 3, "pending": 2, "invalid": 1, None: 0, "": 0}


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_dict(row):
    return dict(row) if row is not None else None


def _json_dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _parse_time(value):
    if not value:
        return None
    try:
        if "," in str(value):
            return parsedate_to_datetime(value)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError, IndexError):
        return None


def _min_time(*values):
    parsed = [(value, _parse_time(value)) for value in values if value]
    parsed = [item for item in parsed if item[1] is not None]
    if not parsed:
        return next((value for value in values if value), None)
    return min(parsed, key=lambda item: item[1])[0]


def _max_time(*values):
    parsed = [(value, _parse_time(value)) for value in values if value]
    parsed = [item for item in parsed if item[1] is not None]
    if not parsed:
        return next((value for value in values if value), None)
    return max(parsed, key=lambda item: item[1])[0]


def _get_fact(conn, fact_id):
    conn.row_factory = __import__("sqlite3").Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM facts WHERE id = ?", (fact_id,))
    return _row_to_dict(cursor.fetchone())


def _get_links(conn, fact_ids):
    placeholders = ",".join("?" for _ in fact_ids)
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT *
        FROM article_facts
        WHERE fact_id IN ({placeholders})
        ORDER BY id ASC
        """,
        list(fact_ids),
    )
    return [dict(row) for row in cursor.fetchall()]


def _get_links_for_fact(conn, fact_id):
    return _get_links(conn, [fact_id])


def _get_evidence_summary(conn, fact_id):
    links = _get_links_for_fact(conn, fact_id)
    return {
        "evidence_count": len(links),
        "article_ids": sorted(link["article_id"] for link in links),
        "best_method_priority": max(
            [METHOD_PRIORITY.get(link.get("extraction_method"), 1) for link in links] or [1]
        ),
        "best_validation_priority": max(
            [VALIDATION_PRIORITY.get(link.get("validation_status"), 0) for link in links] or [0]
        ),
    }


def _specificity_score(fact):
    score = 0
    if fact.get("subject") != "Global nuclear industry":
        score += 1
    if fact.get("action") != "reported":
        score += 1
    if fact.get("status") not in {None, "", "unknown"}:
        score += 1
    if fact.get("fact_type") != "industry_signal":
        score += 1
    for field in ["country", "technology", "organization"]:
        if fact.get(field) not in {None, "", "unknown", "Unknown"}:
            score += 1
    return score


def select_survivor_fact(fact_a, fact_b, evidence_summary_a, evidence_summary_b):
    comparisons = [
        (
            evidence_summary_a["best_method_priority"],
            evidence_summary_b["best_method_priority"],
            "survivor_has_better_extraction_method",
        ),
        (
            evidence_summary_a["best_validation_priority"],
            evidence_summary_b["best_validation_priority"],
            "survivor_has_better_validation_status",
        ),
        (_specificity_score(fact_a), _specificity_score(fact_b), "survivor_is_more_specific"),
        (fact_a.get("confidence") or 0, fact_b.get("confidence") or 0, "survivor_has_higher_confidence"),
        (evidence_summary_a["evidence_count"], evidence_summary_b["evidence_count"], "survivor_has_more_evidence"),
    ]

    a_score = 0
    b_score = 0
    reasons = []
    for value_a, value_b, reason in comparisons:
        if value_a > value_b:
            a_score += 1
            reasons.append(reason)
        elif value_b > value_a:
            b_score += 1
            reasons.append(reason)

    if a_score == b_score:
        time_a = _parse_time(fact_a.get("first_seen_at") or fact_a.get("created_at"))
        time_b = _parse_time(fact_b.get("first_seen_at") or fact_b.get("created_at"))
        if time_a and time_b and time_a != time_b:
            survivor = fact_a if time_a < time_b else fact_b
            reasons.append("survivor_seen_earlier")
        else:
            survivor = fact_a if fact_a["id"] < fact_b["id"] else fact_b
            reasons.append("survivor_has_lower_id")
    else:
        survivor = fact_a if a_score > b_score else fact_b

    source = fact_b if survivor["id"] == fact_a["id"] else fact_a
    return {
        "survivor_fact_id": survivor["id"],
        "source_fact_id": source["id"],
        "reasons": reasons,
    }


def _candidate_payload(candidate):
    return {
        "fact_id_a": candidate["fact_id_a"],
        "fact_id_b": candidate["fact_id_b"],
        "survivor_fact_id": candidate["survivor_fact_id"],
        "source_fact_id": candidate["source_fact_id"],
        "similarity_score": candidate["similarity_score"],
        "classification": candidate["classification"],
        "reason_codes": sorted(candidate.get("reason_codes", [])),
        "conflicts": sorted(candidate.get("conflicts", [])),
        "merge_version": MERGE_VERSION,
    }


def generate_merge_candidate_id(candidate):
    payload = _json_dump(_candidate_payload(candidate))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"fact-merge-{digest}"


def build_merge_preview(fact_id_a, fact_id_b, force_possible=False, force_conflict=False):
    ensure_facts_schema()
    if fact_id_a == fact_id_b:
        return {"merge_allowed": False, "error": "same_fact_id", "database_modified": False}

    conn = get_connection()
    conn.row_factory = __import__("sqlite3").Row
    try:
        fact_a = _get_fact(conn, fact_id_a)
        fact_b = _get_fact(conn, fact_id_b)
        if fact_a is None or fact_b is None:
            return {"merge_allowed": False, "error": "fact_not_found", "database_modified": False}
        if (fact_a.get("merge_status") not in {None, "active"}) or (
            fact_b.get("merge_status") not in {None, "active"}
        ):
            return {"merge_allowed": False, "error": "fact_not_active", "database_modified": False}

        classification = classify_duplicate_candidate(fact_a, fact_b)
        summary_a = _get_evidence_summary(conn, fact_a["id"])
        summary_b = _get_evidence_summary(conn, fact_b["id"])
        survivor = select_survivor_fact(fact_a, fact_b, summary_a, summary_b)
        reason_codes = [reason["code"] for reason in classification["reasons"]]

        merge_allowed = classification["classification"] in {"exact", "high"}
        if classification["classification"] == "possible":
            merge_allowed = force_possible
        if classification["conflicts"]:
            merge_allowed = force_conflict
        if classification["classification"] in {"unlikely", "different"}:
            merge_allowed = False

        candidate = {
            "fact_id_a": fact_id_a,
            "fact_id_b": fact_id_b,
            "survivor_fact_id": survivor["survivor_fact_id"],
            "source_fact_id": survivor["source_fact_id"],
            "similarity_score": classification["similarity_score"],
            "classification": classification["classification"],
            "reason_codes": reason_codes + survivor["reasons"],
            "conflicts": classification["conflicts"],
        }
        candidate["candidate_id"] = generate_merge_candidate_id(candidate)

        return {
            "fact_id_a": fact_id_a,
            "fact_id_b": fact_id_b,
            "similarity_score": classification["similarity_score"],
            "classification": classification["classification"],
            "merge_allowed": merge_allowed,
            "conflicts": classification["conflicts"],
            "survivor_selection": survivor,
            "candidate_id": candidate["candidate_id"],
            "reason_codes": candidate["reason_codes"],
            "database_modified": False,
        }
    finally:
        conn.close()


def _merge_metadata(existing, incoming):
    if existing is None:
        return incoming
    merged = dict(existing)
    for field in ["extraction_method", "validation_status"]:
        priority = METHOD_PRIORITY if field == "extraction_method" else VALIDATION_PRIORITY
        if priority.get(incoming.get(field), 0) > priority.get(existing.get(field), 0):
            merged[field] = incoming.get(field)
    if (incoming.get("extraction_confidence") or 0) > (existing.get("extraction_confidence") or 0):
        merged["extraction_confidence"] = incoming.get("extraction_confidence")
    for field in ["evidence_sentence", "model_name", "extraction_version"]:
        if not merged.get(field) and incoming.get(field):
            merged[field] = incoming.get(field)
    errors = set()
    for value in [existing.get("validation_errors"), incoming.get("validation_errors")]:
        if value:
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    errors.update(str(item) for item in parsed)
                else:
                    errors.add(str(parsed))
            except json.JSONDecodeError:
                errors.add(str(value))
    merged["validation_errors"] = _json_dump(sorted(errors)) if errors else None
    return merged


def _recalculate_evidence_count(conn, fact_id):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM article_facts WHERE fact_id = ?", (fact_id,))
    count = cursor.fetchone()[0]
    cursor.execute(
        "UPDATE facts SET evidence_count = ?, updated_at = ? WHERE id = ?",
        (count, utc_now_iso(), fact_id),
    )
    return count


def _union_semicolon_values(value_a, value_b, normalizer):
    values = normalizer(value_a) + normalizer(value_b)
    unique = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return "; ".join(sorted(unique, key=str.lower)) if unique else "unknown"


def _better_value(current, incoming, generic_values):
    if current in generic_values and incoming not in generic_values:
        return incoming
    return current


def _improve_survivor_fields(conn, survivor, source):
    technology = _union_semicolon_values(survivor.get("technology"), source.get("technology"), normalize_fact_technology)
    organization = _union_semicolon_values(survivor.get("organization"), source.get("organization"), normalize_fact_organization)
    cursor = conn.cursor()
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
            first_seen_at = ?,
            last_seen_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            _better_value(survivor.get("subject"), source.get("subject"), {None, "", "Global nuclear industry"}),
            _better_value(survivor.get("action"), source.get("action"), {None, "", "reported"}),
            _better_value(survivor.get("object"), source.get("object"), {None, ""}),
            _better_value(survivor.get("fact_type"), source.get("fact_type"), {None, "", "industry_signal"}),
            _better_value(survivor.get("status"), source.get("status"), {None, "", "unknown"}),
            _better_value(survivor.get("country"), source.get("country"), {None, "", "unknown", "Unknown"}),
            technology,
            organization,
            _better_value(survivor.get("category"), source.get("category"), {None, "", "Industry Signal"}),
            max(survivor.get("importance") or 0, source.get("importance") or 0),
            max(survivor.get("confidence") or 0, source.get("confidence") or 0),
            _min_time(survivor.get("first_seen_at"), source.get("first_seen_at")),
            _max_time(survivor.get("last_seen_at"), source.get("last_seen_at")),
            utc_now_iso(),
            survivor["id"],
        ),
    )


def _merge_links(conn, survivor_fact_id, source_fact_id):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM article_facts WHERE fact_id = ? ORDER BY id ASC",
        (source_fact_id,),
    )
    source_links = [dict(row) for row in cursor.fetchall()]
    links_moved = 0
    links_deduplicated = 0

    for source_link in source_links:
        cursor.execute(
            """
            SELECT *
            FROM article_facts
            WHERE article_id = ?
              AND fact_id = ?
            LIMIT 1
            """,
            (source_link["article_id"], survivor_fact_id),
        )
        existing = cursor.fetchone()
        if existing:
            merged = _merge_metadata(dict(existing), source_link)
            cursor.execute(
                """
                UPDATE article_facts
                SET
                    evidence_sentence = ?,
                    extraction_method = ?,
                    extraction_confidence = ?,
                    extraction_version = ?,
                    model_name = ?,
                    validation_status = ?,
                    validation_errors = ?
                WHERE id = ?
                """,
                (
                    merged.get("evidence_sentence"),
                    merged.get("extraction_method"),
                    merged.get("extraction_confidence"),
                    merged.get("extraction_version"),
                    merged.get("model_name"),
                    merged.get("validation_status"),
                    merged.get("validation_errors"),
                    existing["id"],
                ),
            )
            cursor.execute("DELETE FROM article_facts WHERE id = ?", (source_link["id"],))
            links_deduplicated += 1
        else:
            cursor.execute(
                "UPDATE article_facts SET fact_id = ? WHERE id = ?",
                (survivor_fact_id, source_link["id"]),
            )
            links_moved += 1

    return links_moved, links_deduplicated


def _insert_audit(conn, merge_id, survivor_id, source_id, classification, candidate, survivor_snapshot, source_snapshot, links_before, links_after):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO fact_merge_audit (
            merge_id,
            survivor_fact_id,
            source_fact_id,
            status,
            similarity_score,
            classification,
            reason_codes,
            conflicts,
            survivor_snapshot,
            source_snapshot,
            links_before,
            links_after,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            merge_id,
            survivor_id,
            source_id,
            "committed",
            candidate["similarity_score"],
            classification,
            _json_dump(candidate.get("reason_codes", [])),
            _json_dump(candidate.get("conflicts", [])),
            _json_dump(survivor_snapshot),
            _json_dump(source_snapshot),
            _json_dump(links_before),
            _json_dump(links_after),
            utc_now_iso(),
        ),
    )


def commit_fact_merge(payload, force_possible=False, force_conflict=False):
    ensure_facts_schema()
    merge_id = payload.get("candidate_id")
    if merge_id:
        existing_audit = get_merge_audit(merge_id)
        if existing_audit is not None:
            return {
                "merge_id": merge_id,
                "status": existing_audit["status"],
                "survivor_fact_id": existing_audit["survivor_fact_id"],
                "source_fact_id": existing_audit["source_fact_id"],
                "idempotent": True,
            }

    preview = build_merge_preview(
        payload.get("fact_id_a"),
        payload.get("fact_id_b"),
        force_possible=force_possible,
        force_conflict=force_conflict,
    )
    if preview.get("error"):
        return {"status": "rejected", "error": preview["error"]}
    candidate = {
        "fact_id_a": payload.get("fact_id_a"),
        "fact_id_b": payload.get("fact_id_b"),
        "survivor_fact_id": preview["survivor_selection"]["survivor_fact_id"],
        "source_fact_id": preview["survivor_selection"]["source_fact_id"],
        "similarity_score": preview["similarity_score"],
        "classification": preview["classification"],
        "reason_codes": preview["reason_codes"],
        "conflicts": preview["conflicts"],
    }
    expected_id = generate_merge_candidate_id(candidate)
    if payload.get("candidate_id") != expected_id:
        return {"status": "rejected", "error": "candidate_hash_mismatch"}
    if not preview["merge_allowed"]:
        return {"status": "rejected", "error": "merge_not_allowed", **preview}

    merge_id = expected_id
    conn = get_connection()
    conn.row_factory = __import__("sqlite3").Row
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        cursor.execute("SELECT * FROM fact_merge_audit WHERE merge_id = ?", (merge_id,))
        existing = cursor.fetchone()
        if existing:
            conn.rollback()
            return {
                "merge_id": merge_id,
                "status": existing["status"],
                "survivor_fact_id": existing["survivor_fact_id"],
                "source_fact_id": existing["source_fact_id"],
                "idempotent": True,
            }

        survivor_id = candidate["survivor_fact_id"]
        source_id = candidate["source_fact_id"]
        survivor = _get_fact(conn, survivor_id)
        source = _get_fact(conn, source_id)
        links_before = _get_links(conn, [survivor_id, source_id])
        survivor_snapshot = dict(survivor)
        source_snapshot = dict(source)

        links_moved, links_deduplicated = _merge_links(conn, survivor_id, source_id)
        _improve_survivor_fields(conn, survivor, source)
        survivor_evidence_count = _recalculate_evidence_count(conn, survivor_id)
        _recalculate_evidence_count(conn, source_id)
        cursor.execute(
            """
            UPDATE facts
            SET
                merge_status = ?,
                merged_into_fact_id = ?,
                merged_at = ?,
                merge_reason = ?,
                evidence_count = 0,
                updated_at = ?
            WHERE id = ?
            """,
            ("merged", survivor_id, utc_now_iso(), merge_id, utc_now_iso(), source_id),
        )
        links_after = _get_links(conn, [survivor_id, source_id])
        _insert_audit(
            conn,
            merge_id,
            survivor_id,
            source_id,
            candidate["classification"],
            candidate,
            survivor_snapshot,
            source_snapshot,
            links_before,
            links_after,
        )
        conn.commit()
        return {
            "merge_id": merge_id,
            "status": "committed",
            "survivor_fact_id": survivor_id,
            "source_fact_id": source_id,
            "links_moved": links_moved,
            "links_deduplicated": links_deduplicated,
            "survivor_evidence_count": survivor_evidence_count,
            "source_merge_status": "merged",
            "audit_created": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_merge_audit(merge_id):
    ensure_facts_schema()
    conn = get_connection()
    conn.row_factory = __import__("sqlite3").Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fact_merge_audit WHERE merge_id = ?", (merge_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_merge_audits(status=None, fact_id=None, limit=50):
    ensure_facts_schema()
    filters = []
    values = []
    if status:
        filters.append("status = ?")
        values.append(status)
    if fact_id:
        filters.append("(survivor_fact_id = ? OR source_fact_id = ?)")
        values.extend([fact_id, fact_id])
    where_clause = "WHERE " + " AND ".join(filters) if filters else ""
    values.append(limit)
    conn = get_connection()
    conn.row_factory = __import__("sqlite3").Row
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT *
            FROM fact_merge_audit
            {where_clause}
            ORDER BY id DESC
            LIMIT ?
            """,
            values,
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _restore_fact(conn, snapshot):
    columns = [
        "fact_key", "subject", "action", "object", "fact_type", "status",
        "country", "technology", "organization", "category", "importance",
        "confidence", "summary", "evidence_count", "first_seen_at",
        "last_seen_at", "event_date", "date_precision", "date_source",
        "event_date_end", "event_date_confidence", "merge_status",
        "merged_into_fact_id", "merged_at",
        "merge_reason", "created_at", "updated_at",
    ]
    assignments = ", ".join(f"{column} = ?" for column in columns)
    values = [snapshot.get(column) for column in columns]
    values.append(snapshot["id"])
    conn.execute(f"UPDATE facts SET {assignments} WHERE id = ?", values)


def rollback_fact_merge(merge_id, reason=None):
    ensure_facts_schema()
    conn = get_connection()
    conn.row_factory = __import__("sqlite3").Row
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        cursor.execute("SELECT * FROM fact_merge_audit WHERE merge_id = ?", (merge_id,))
        audit = cursor.fetchone()
        if audit is None:
            conn.rollback()
            return {"status": "not_found"}
        if audit["status"] == "rolled_back":
            conn.rollback()
            return {"merge_id": merge_id, "status": "rolled_back", "idempotent": True}
        if audit["status"] != "committed":
            conn.rollback()
            return {"status": "rejected", "error": "audit_not_committed"}

        survivor_id = audit["survivor_fact_id"]
        source_id = audit["source_fact_id"]
        links_after = json.loads(audit["links_after"])
        current_links = _get_links(conn, [survivor_id, source_id])
        if _json_dump(current_links) != _json_dump(links_after):
            conn.rollback()
            return {"status": "rejected", "error": "merge_dependency_detected"}

        survivor_snapshot = json.loads(audit["survivor_snapshot"])
        source_snapshot = json.loads(audit["source_snapshot"])
        links_before = json.loads(audit["links_before"])

        cursor.execute(
            "DELETE FROM article_facts WHERE fact_id IN (?, ?)",
            (survivor_id, source_id),
        )
        for link in links_before:
            columns = [
                "id", "article_id", "fact_id", "evidence_sentence",
                "extraction_method", "extraction_confidence", "extraction_version",
                "model_name", "validation_status", "validation_errors", "created_at",
            ]
            placeholders = ",".join("?" for _ in columns)
            cursor.execute(
                f"INSERT INTO article_facts ({','.join(columns)}) VALUES ({placeholders})",
                [link.get(column) for column in columns],
            )
        _restore_fact(conn, survivor_snapshot)
        _restore_fact(conn, source_snapshot)
        cursor.execute(
            """
            UPDATE fact_merge_audit
            SET status = ?, rolled_back_at = ?, rollback_reason = ?
            WHERE merge_id = ?
            """,
            ("rolled_back", utc_now_iso(), reason, merge_id),
        )
        conn.commit()
        return {
            "merge_id": merge_id,
            "status": "rolled_back",
            "survivor_fact_id": survivor_id,
            "source_fact_id": source_id,
            "facts_restored": 2,
            "links_restored": len(links_before),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
