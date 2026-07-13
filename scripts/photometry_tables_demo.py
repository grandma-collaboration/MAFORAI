from __future__ import annotations

from skyportal_corpus.canonical.document import iter_real_circulars, render_canonical
from skyportal_corpus.extraction_v2.photometry_tables import (
    detect_table_blocks,
    infer_column_roles,
    split_row,
)


KEYWORDS = ("UVOT", "GRANDMA", "KNC")
MAX_PER_KEYWORD = 5


def _marked_excerpt(text: str, start: int, end: int, window: int = 180) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    excerpt = text[left:start] + "⟦" + text[start:end] + "⟧" + text[end:right]
    return excerpt.replace("\n", " ⏎ ")


def _format_roles(block) -> str:
    details = infer_column_roles(block)
    parts = []
    for index, detail in details.items():
        subtype = f", time_subtype={detail.time_subtype}" if detail.time_subtype else ""
        parts.append(f"{index}: {detail.role} (confidence={detail.confidence:.2f}{subtype})")
    return "{ " + "; ".join(parts) + " }"


def main() -> None:
    selected = []
    found = {keyword: 0 for keyword in KEYWORDS}
    records = list(iter_real_circulars(min_year=2024))
    for subject_only in (True, False):
        for circular in records:
            subject = circular.get("subject", "")
            haystack = subject if subject_only else f"{subject}\n{circular.get('body', '')}"
            matching_keywords = [keyword for keyword in KEYWORDS if keyword.lower() in haystack.lower()]
            if not matching_keywords:
                continue
            doc = render_canonical(**circular)
            blocks = detect_table_blocks(doc.rendered_text)
            if not blocks:
                continue
            for keyword in matching_keywords:
                if found[keyword] >= MAX_PER_KEYWORD:
                    continue
                found[keyword] += 1
                selected.append((keyword, circular, doc, blocks))
            if all(count >= MAX_PER_KEYWORD for count in found.values()):
                break
        if all(count >= MAX_PER_KEYWORD for count in found.values()):
            break

    if not selected:
        print("No targeted photometry table blocks found.")
        return

    for keyword, circular, doc, blocks in selected:
        print("=" * 100)
        print(f"keyword: {keyword}")
        print(f"circular_id: {circular['circular_id']}")
        print(f"subject: {circular.get('subject', '')}")
        print(f"blocks: {len(blocks)}")
        for index, block in enumerate(blocks, start=1):
            print("-" * 100)
            print(f"block {index}: delimiter={block.delimiter_type}")
            print(f"raw_header: {block.raw_header or ''}")
            print(f"column_roles: {_format_roles(block)}")
            print("context_before:")
            print(block.context_before or "")
            print("context_after:")
            print(block.context_after or "")
            data_lines = [line for line in block.lines if split_row(line, block.delimiter_type)]
            for row in data_lines[:4]:
                print(f"cells: {split_row(row, block.delimiter_type)}")
            print("excerpt:")
            print(_marked_excerpt(doc.rendered_text, block.start_offset, block.end_offset))
    print(f"SUMMARY {found}")


if __name__ == "__main__":
    main()
