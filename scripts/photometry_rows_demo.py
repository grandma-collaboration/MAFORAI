from __future__ import annotations

from collections import defaultdict

from skyportal_corpus.canonical.document import iter_real_circulars, render_canonical
from skyportal_corpus.extraction_v2.photometry_rows import parse_table_to_measurements
from skyportal_corpus.extraction_v2.photometry_tables import detect_table_blocks


KEYWORDS = ("UVOT", "GRANDMA", "KNC")
MAX_TOTAL_CIRCULARS = 5
MAX_PER_KEYWORD = 2
PREFERRED_CIRCULAR_IDS = (35457, 35534, 36026, 36050, 36326)


def main() -> None:
    records = list(iter_real_circulars(min_year=2024))
    selected = []
    seen_circular_ids: set[int] = set()
    found_by_keyword: dict[str, int] = defaultdict(int)

    # Try known real examples first so the demo covers UVOT, GRANDMA, and KNC
    # measurement tables rather than large catalog-like tables. The generic
    # keyword search below remains as a fallback.
    for preferred_id in PREFERRED_CIRCULAR_IDS:
        circular = next((record for record in records if int(record["circular_id"]) == preferred_id), None)
        if circular is None:
            continue
        selected_item = _parse_candidate(circular)
        if selected_item is None:
            continue
        keyword, circular, doc, blocks, measurements = selected_item
        selected.append((keyword, circular, doc, blocks, measurements))
        seen_circular_ids.add(int(circular["circular_id"]))
        found_by_keyword[keyword] += 1
        if len(selected) >= MAX_TOTAL_CIRCULARS:
            break

    for keyword in KEYWORDS:
        for circular in records:
            circular_id = int(circular["circular_id"])
            if (
                circular_id in seen_circular_ids
                or found_by_keyword[keyword] >= MAX_PER_KEYWORD
                or len(selected) >= MAX_TOTAL_CIRCULARS
            ):
                continue
            haystack = f"{circular.get('subject', '')}\n{circular.get('body', '')}"
            if keyword.lower() not in haystack.lower():
                continue
            selected_item = _parse_candidate(circular, keyword_hint=keyword)
            if selected_item is None:
                continue
            selected.append(selected_item)
            seen_circular_ids.add(circular_id)
            found_by_keyword[keyword] += 1
            if len(selected) >= MAX_TOTAL_CIRCULARS:
                break
        if len(selected) >= MAX_TOTAL_CIRCULARS:
            break

    if not selected:
        print("No targeted photometric measurements found in tables.")
        return

    total_measurements = 0
    for keyword, circular, doc, blocks, measurements in selected:
        total_measurements += len(measurements)
        print("=" * 100)
        print(f"keyword: {keyword}")
        print(f"circular_id: {circular['circular_id']}")
        print(f"subject: {circular.get('subject', '')}")
        print(f"table_blocks: {len(blocks)}")
        print(f"measurements: {len(measurements)}")
        for index, annotation in enumerate(measurements, start=1):
            print("-" * 100)
            print(f"measurement {index}")
            print(f"measurement_type: {annotation.measurement_type}")
            print(f"magnitude_or_limit: {annotation.magnitude_or_limit}")
            print(f"unit: {annotation.unit}")
            print(f"photometric_band: {annotation.photometric_band}")
            print(f"photometric_system: {annotation.photometric_system}")
            print(f"obs_time_raw: {annotation.obs_time_raw}")
            print(f"obs_time_type: {annotation.obs_time_type}")
            print(f"obs_time_reference: {annotation.obs_time_reference}")
            print(f"exposure_time_raw: {annotation.exposure_time_raw}")
            print(f"instrument: {annotation.instrument}")
            print(f"needs_review: {annotation.needs_review}")
            print(f"comment: {annotation.comment or ''}")
            print(f"provenance_inherited: {annotation.provenance_inherited}")
            print(f"verify: {'OK' if annotation.verify(doc.rendered_text) else 'FAIL'}")
            print(f"text: {annotation.text}")

    print("=" * 100)
    print(f"SUMMARY circulars={len(selected)} measurements={total_measurements}")
    print(f"BY_KEYWORD {dict(found_by_keyword)}")


def _parse_candidate(circular: dict, keyword_hint: str | None = None):
    doc = render_canonical(**circular)
    blocks = detect_table_blocks(doc.rendered_text)
    measurements = []
    for block in blocks:
        measurements.extend(parse_table_to_measurements(block, doc))
    if not measurements:
        return None
    keyword = keyword_hint or _classify_keyword(circular)
    return keyword, circular, doc, blocks, measurements


def _classify_keyword(circular: dict) -> str:
    haystack = f"{circular.get('subject', '')}\n{circular.get('body', '')}".lower()
    for keyword in KEYWORDS:
        if keyword.lower() in haystack:
            return keyword
    return "TABLE"


if __name__ == "__main__":
    main()
