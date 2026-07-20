from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from skyportal_corpus.canonical.document import CanonicalDocument, render_canonical
from skyportal_corpus.extraction_v2.annotations import EventEvidenceAnnotation
from skyportal_corpus.extraction_v2.event_identity import EventIdentityExtractor


def normalize_for_match(s: str) -> str:
    """Normalize direct event-name matching by keeping only lowercase ASCII letters/digits."""
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def canonical_aliases(aliases: list[str]) -> dict[str, dict[str, Any]]:
    extractor = EventIdentityExtractor()
    result: dict[str, dict[str, Any]] = {}
    for alias in aliases:
        doc = render_canonical(circular_id=0, subject=alias, body="Alias canonicalization probe.")
        identities = extractor.extract(doc)
        canonical = identities[0].value if identities else None
        result[alias] = {
            "raw": alias,
            "canonical": canonical,
            "normalized": normalize_for_match(alias),
            "recognizable": canonical is not None,
        }
    return result


def circular_matches_event(
    subject_identities: Sequence[EventEvidenceAnnotation | Mapping[str, Any]],
    body_identities: Sequence[EventEvidenceAnnotation | Mapping[str, Any]],
    event_alias_info: Mapping[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    aliases = _alias_entries(event_alias_info)

    # Hierarchy:
    # 1. Confirmed subject identities are authoritative. If one matches an alias,
    #    the circular belongs to the event.
    # 2. If the subject confirms another event and the body mentions the requested
    #    event, we exclude it as a confirmed conflict. This is the 44891 pattern:
    #    a GRB 260610A circular can mention GRB 260610B without belonging to it.
    # 3. Only when the subject has no confirmed event identity do body identities
    #    or direct normalized body mentions act as fallback inclusion evidence.
    for identity in subject_identities:
        match = _matching_alias(identity, aliases)
        if match is not None:
            return True, "confirmed_subject_match", {"identity": _identity_evidence(identity), "alias": match}

    body_match = _body_match(body_identities, event_alias_info, aliases)
    if subject_identities:
        if body_match is not None:
            return (
                False,
                "confirmed_other_event",
                {
                    "confirmed_subject_identities": [
                        _identity_evidence(identity) for identity in subject_identities
                    ],
                    "suppressed_body_match": body_match,
                },
            )
        return (
            False,
            "no_match",
            {"confirmed_subject_identities": [_identity_evidence(identity) for identity in subject_identities]},
        )

    if body_match is not None:
        return True, "body_mention", body_match

    return False, "no_match", {}


def _body_match(
    body_identities: Sequence[EventEvidenceAnnotation | Mapping[str, Any]],
    event_alias_info: Mapping[str, Any],
    aliases: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    for identity in body_identities:
        match = _matching_alias(identity, aliases)
        if match is not None:
            return {"identity": _identity_evidence(identity), "alias": match}

    body_text = str(event_alias_info.get("body_text") or "")
    for alias in aliases:
        pattern = _body_name_pattern(str(alias.get("raw") or ""))
        if pattern is None:
            continue
        match = pattern.search(body_text)
        if match is not None:
            return {
                "alias": dict(alias),
                "match_type": "body_name_match",
                "matched_text": match.group(0),
            }
    return None


def _body_name_pattern(alias: str) -> re.Pattern[str] | None:
    """Build a separator-flexible, boundary-aware pattern for one event name."""
    runs = re.findall(r"[A-Za-z]+|\d+[A-Za-z]*", alias)
    if not runs:
        return None
    expression = r"\b" + r"[^A-Za-z0-9]*".join(
        re.escape(run) for run in runs
    ) + r"\b"
    return re.compile(expression, re.IGNORECASE)


def group_event_circulars(
    source_id: str,
    aliases: list[str],
    circulars: Iterable[Mapping[str, Any]],
    title: str | None = None,
) -> dict[str, Any]:
    alias_info = canonical_aliases(aliases)
    extractor = EventIdentityExtractor()
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    n_candidates = 0

    for circular in circulars:
        n_candidates += 1
        doc = render_canonical(**_render_kwargs(circular))
        annotations = extractor.extract(doc)
        subject_identities = [
            annotation
            for annotation in annotations
            if _is_in_header(doc, annotation) and not annotation.needs_review
        ]
        body_identities = [
            annotation
            for annotation in annotations
            if annotation not in subject_identities
        ]
        belongs, reason, evidence = circular_matches_event(
            subject_identities,
            body_identities,
            {"aliases": list(alias_info.values()), "body_text": _body_text(doc)},
        )
        item = {
            "circular_id": doc.circular_id,
            "subject": doc.subject,
            "reason": reason,
            "evidence": evidence,
            "created_on": doc.created_on,
        }
        if belongs:
            included.append(item)
        else:
            excluded.append(item)

    included.sort(key=_group_item_sort_key)
    excluded.sort(key=_group_item_sort_key)
    return {
        "source_id": source_id,
        "title": title or source_id,
        "aliases": list(alias_info.values()),
        "n_candidates": n_candidates,
        "n_included": len(included),
        "n_excluded": len(excluded),
        "included": included,
        "excluded": excluded,
    }


def _render_kwargs(circular: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "circular_id": int(circular["circular_id"]),
        "subject": str(circular.get("subject") or ""),
        "body": str(circular.get("body") or ""),
        "event_id": _optional_str(circular.get("event_id")),
        "created_on": _optional_str(circular.get("created_on")),
        "submitter": _optional_str(circular.get("submitter")),
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _alias_entries(event_alias_info: Mapping[str, Any]) -> list[dict[str, Any]]:
    if isinstance(event_alias_info.get("aliases"), list):
        return [dict(item) for item in event_alias_info["aliases"] if isinstance(item, Mapping)]
    return [dict(item) for item in event_alias_info.values() if isinstance(item, Mapping)]


def _matching_alias(
    identity: EventEvidenceAnnotation | Mapping[str, Any],
    aliases: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    value = _identity_value(identity)
    normalized_value = normalize_for_match(value)
    for alias in aliases:
        canonical = alias.get("canonical")
        if alias.get("recognizable") and canonical is not None and value == str(canonical):
            return dict(alias)
        if normalized_value == str(alias.get("normalized") or ""):
            return dict(alias)
    return None


def _identity_value(identity: EventEvidenceAnnotation | Mapping[str, Any]) -> str:
    if isinstance(identity, EventEvidenceAnnotation):
        return str(identity.value or "")
    return str(identity.get("value") or "")


def _identity_evidence(identity: EventEvidenceAnnotation | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(identity, EventEvidenceAnnotation):
        return {
            "value": identity.value,
            "text": identity.text,
            "span_start": identity.span_start,
            "span_end": identity.span_end,
            "rule_id": identity.rule_id,
            "needs_review": identity.needs_review,
        }
    return dict(identity)


def _is_in_header(doc: CanonicalDocument, annotation: EventEvidenceAnnotation) -> bool:
    for segment in doc.segments:
        if segment.name == "header":
            return annotation.span_start < segment.end and annotation.span_end > segment.start
    return False


def _body_text(doc: CanonicalDocument) -> str:
    for segment in doc.segments:
        if segment.name == "body":
            return segment.text
    return ""


def _group_item_sort_key(item: Mapping[str, Any]) -> tuple[str, int]:
    created_on = str(item.get("created_on") or "")
    circular_id = int(item.get("circular_id") or 0)
    return created_on, circular_id
