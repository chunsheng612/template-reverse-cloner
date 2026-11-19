"""Check observation evidence links and coverage claims; not a semantic review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate(record: dict) -> list[str]:
    errors = []
    if not isinstance(record, dict):
        return ["Record must be an object"]
    coverage = record.get("coverage", {})
    if not isinstance(coverage, dict):
        coverage = {}
    if coverage.get("status") not in {"full", "partial", "unknown"}:
        errors.append("coverage.status must be full, partial, or unknown")
    if not isinstance(coverage.get("basis"), str) or not coverage.get("basis", "").strip():
        errors.append("coverage.basis is required")
    if not isinstance(coverage.get("gaps"), list):
        errors.append("coverage.gaps must be a list")
    if coverage.get("status") == "full" and coverage.get("gaps"):
        errors.append("Full coverage cannot have gaps")
    if record.get("record_scope") not in {"full_class", "draft"}:
        errors.append("record_scope must be full_class or draft")
    if record.get("record_scope") == "full_class" and (coverage.get("status") != "full" or coverage.get("gaps")):
        errors.append("full_class requires confirmed full coverage without gaps")

    sources = {}
    source_rows = record.get("sources", [])
    if not isinstance(source_rows, list) or not source_rows:
        errors.append("At least one source is required")
        source_rows = []
    for row in source_rows:
        if not isinstance(row, dict):
            errors.append("Source must be an object")
            continue
        key = row.get("id")
        if not isinstance(key, str) or not key.strip() or key in sources:
            errors.append("Source IDs must be unique nonempty strings")
            continue
        sources[key] = row
        if row.get("kind") not in {"transcript", "audio_transcript", "observer_notes", "post_conference"}:
            errors.append("Unknown source kind: " + key)
        if not isinstance(row.get("reference"), str) or not row.get("reference", "").strip():
            errors.append("Source reference missing: " + key)

    events = {}
    event_rows = record.get("events", [])
    if not isinstance(event_rows, list):
        errors.append("events must be a list")
        event_rows = []
    for row in event_rows:
        if not isinstance(row, dict):
            errors.append("Event must be an object")
            continue
        key = row.get("id")
        if not isinstance(key, str) or not key.strip() or key in events:
            errors.append("Event IDs must be unique nonempty strings")
            continue
        events[key] = row
        if row.get("source_id") not in sources:
            errors.append("Unknown event source: " + key)
        if not isinstance(row.get("locator"), str) or not row.get("locator", "").strip():
            errors.append("Event locator missing: " + key)
        if not any(isinstance(row.get(field), str) and row[field].strip() for field in ("teacher_behavior", "student_behavior")):
            errors.append("Event has no recorded behavior: " + key)

    statements = record.get("statements", [])
    if not isinstance(statements, list):
        errors.append("statements must be a list")
        statements = []
    for index, row in enumerate(statements):
        if not isinstance(row, dict):
            errors.append("Statement must be an object")
            continue
        kind = row.get("type")
        if kind not in {"fact", "analysis", "suggestion", "pending"}:
            errors.append("Unknown statement type: " + str(index))
        if not isinstance(row.get("text"), str) or not row.get("text", "").strip():
            errors.append("Statement text missing: " + str(index))
        links = row.get("evidence_ids", [])
        if not isinstance(links, list) or any(not isinstance(link, str) for link in links):
            errors.append("evidence_ids must contain string IDs: " + str(index))
            continue
        if kind in {"fact", "analysis"} and not links:
            errors.append("Fact or analysis requires evidence: " + str(index))
        if any(link not in events for link in links):
            errors.append("Unknown evidence ID: " + str(index))
        if kind == "fact" and row.get("section") == "post_conference":
            if not any(sources.get(events.get(link, {}).get("source_id"), {}).get("kind") == "post_conference" for link in links):
                errors.append("Post-conference fact requires post-conference evidence: " + str(index))
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(json.loads(args.record.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        errors = [str(error)]
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
