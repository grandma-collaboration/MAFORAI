from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import iter_real_circulars
from skyportal_corpus.extraction_v2.event_grouping import group_event_circulars


SOURCE_ID = "2026owq"
TITLE = "GRB 260610B / AT2026owq"
ALIASES = ["GRB 260610B", "AT2026owq", "2026owq"]
MIN_CIRCULAR_ID = 44880
MAX_CIRCULAR_ID = 45050


def main() -> None:
    circulars = list(_candidate_circulars())
    result = group_event_circulars(
        source_id=SOURCE_ID,
        title=TITLE,
        aliases=ALIASES,
        circulars=circulars,
    )

    print("SUMMARY")
    print(f"source_id: {result['source_id']}")
    print(f"title: {result['title']}")
    print(f"n_candidates: {result['n_candidates']}")
    print(f"n_included: {result['n_included']}")
    print(f"n_excluded: {result['n_excluded']}")

    print("\nINCLUDED")
    if not result["included"]:
        print("(none)")
    for item in result["included"]:
        print(
            f"{item['circular_id']} | {item.get('created_on') or ''} | "
            f"{item['subject']} | {item['reason']} | {_evidence_summary(item['evidence'])}"
        )

    print("\nEXCLUDED")
    if not result["excluded"]:
        print("(none)")
    for item in result["excluded"]:
        print(
            f"{item['circular_id']} | {item['subject']} | "
            f"{item['reason']} | {_evidence_summary(item['evidence'])}"
        )

    print("\nCHECK 44891")
    print(_check_circular_44891(result))


def _candidate_circulars() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for circular in iter_real_circulars(min_year=2026):
        circular_id = int(circular["circular_id"])
        if MIN_CIRCULAR_ID <= circular_id <= MAX_CIRCULAR_ID:
            candidates.append(circular)
    return sorted(candidates, key=lambda item: (str(item.get("created_on") or ""), int(item["circular_id"])))


def _check_circular_44891(result: dict[str, Any]) -> str:
    for item in result["included"]:
        if int(item["circular_id"]) == 44891:
            return f"INCLUIDA | reason={item['reason']} | {_evidence_summary(item['evidence'])}"
    for item in result["excluded"]:
        if int(item["circular_id"]) == 44891:
            return f"EXCLUIDA | reason={item['reason']} | {_evidence_summary(item['evidence'])}"
    return "NOT FOUND among the processed candidates"


def _evidence_summary(evidence: dict[str, Any]) -> str:
    identity = evidence.get("identity")
    alias = evidence.get("alias")
    if identity and alias:
        return f"identity={identity.get('value')} text={identity.get('text')!r} alias={alias.get('raw')}"

    if evidence.get("match_type") == "normalized_body_text" and alias:
        return f"body_text_match alias={alias.get('raw')} normalized={alias.get('normalized')}"

    confirmed = evidence.get("confirmed_subject_identities")
    if confirmed:
        confirmed_values = ", ".join(str(item.get("value")) for item in confirmed)
        suppressed = evidence.get("suppressed_body_match")
        if suppressed:
            return f"confirmed_subject={confirmed_values}; suppressed_body={_evidence_summary(suppressed)}"
        return f"confirmed_subject={confirmed_values}"

    return "-"


if __name__ == "__main__":
    main()
