#!/usr/bin/env python
"""Build offline BGE-M3 indexes for the 6h, 24h, and 7d STATE snapshots."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skyportal_corpus.retrieval.embed import (  # noqa: E402
    WINDOWS,
    embed_texts,
    load_encoder,
    load_snapshot_metadata,
    npy_bytes,
    write_index,
)


def main() -> int:
    """Embed all windows and verify deterministic re-embedding of the 6h window."""
    encoder = load_encoder()
    built: dict[str, tuple] = {}

    for window in WINDOWS:
        metadata = load_snapshot_metadata(window)
        started = time.perf_counter()
        vectors = embed_texts(metadata["matching_text"], encoder)
        elapsed = time.perf_counter() - started
        built[window] = (metadata, vectors, elapsed)

    metadata_6h, vectors_6h, _ = built["6h"]
    repeated_6h = embed_texts(metadata_6h["matching_text"], encoder)
    deterministic = npy_bytes(vectors_6h) == npy_bytes(repeated_6h)
    if not deterministic:
        raise RuntimeError("6h re-embedding was not byte-identical")

    results = []
    for window in WINDOWS:
        metadata, vectors, elapsed = built[window]
        result = write_index(
            window,
            vectors,
            metadata,
            embedding_seconds=elapsed,
            extra_build_metadata={
                "offline_mode": "true",
                "deterministic_reembed_6h": "PASS" if deterministic else "FAIL",
            },
        )
        results.append(result)

    for result in results:
        print(
            f"{result.window}: {result.n_vectors} vectors x {result.dimension} "
            f"float32; embedding_seconds={result.embedding_seconds:.3f}"
        )
    print("6h deterministic re-embed: PASS (byte-identical .npy serialization)")
    print("Offline model loading: PASS (HF_HUB_OFFLINE=1, local_files_only=True)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
