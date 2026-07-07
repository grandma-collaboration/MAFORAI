from __future__ import annotations

import hashlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from skyportal_corpus.canonical.document import (  # noqa: E402
    _strip_illegal_xml_chars,
    load_one_real_circular,
    render_canonical,
)


def main() -> int:
    circular = load_one_real_circular()
    document = render_canonical(**circular)

    print(f"circular_id: {document.circular_id}")
    print(f"subject: {document.subject}")
    print(f"text_sha256: {document.text_sha256}")
    print("segments:")
    for segment in document.segments:
        print(f"  - {segment.name}: {segment.start}-{segment.end}")
    print("rendered_text_first_600:")
    print(document.rendered_text[:600])

    print("checks:")
    segment_slices_ok = all(
        document.rendered_text[segment.start : segment.end] == segment.text
        for segment in document.segments
    )
    print(f"  segment slices: {_status(segment_slices_ok)}")

    body_segment = next(segment for segment in document.segments if segment.name == "body")
    body_start = document.rendered_text.index("\n\n") + 2
    body_ok = body_segment.start == body_start and body_segment.text == document.rendered_text[body_start:]
    print(f"  body after header: {_status(body_ok)}")

    sha_ok = hashlib.sha256(document.rendered_text.encode("utf-8")).hexdigest() == document.text_sha256
    print(f"  sha256: {_status(sha_ok)}")

    xml_ok = document.rendered_text == _strip_illegal_xml_chars(document.rendered_text)
    print(f"  illegal XML controls removed: {_status(xml_ok)}")

    return 0 if all((segment_slices_ok, body_ok, sha_ok, xml_ok)) else 1


def _status(ok: bool) -> str:
    return "OK" if ok else "FAIL"


if __name__ == "__main__":
    raise SystemExit(main())
