"""Offline dense embeddings and NumPy indexes for STATE snapshots."""
from __future__ import annotations

import io
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# These are set before sentence-transformers is imported. The index build must never
# fall back to a network request when the local model cache is incomplete.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DIMENSION = 1024
WINDOWS = ("6h", "24h", "7d")

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SNAPSHOT_ROOT = REPO_ROOT / "data/ledger/state_snapshots"
DEFAULT_INDEX_ROOT = REPO_ROOT / "data/ledger/state_index"

METADATA_COLUMNS = (
    "event_id",
    "messenger_class",
    "localization_state",
    "has_counterpart",
    "z_known_at_T",
    "matching_text",
)


@dataclass(frozen=True)
class StateIndex:
    """One window's aligned metadata and L2-normalized dense vectors."""

    window: str
    vectors: np.ndarray
    metadata: pd.DataFrame
    build_metadata: dict[str, str]


@dataclass(frozen=True)
class IndexBuildResult:
    """Measurements and paths produced by one index build."""

    window: str
    n_vectors: int
    dimension: int
    embedding_seconds: float
    vectors_path: Path
    metadata_path: Path


def normalize_window(window: str | int) -> str:
    """Return a supported canonical window label."""
    label = str(window).strip().lower()
    if label.isdigit():
        label = f"{label}h"
    if label not in WINDOWS:
        raise ValueError(f"Unsupported window {window!r}; expected one of {WINDOWS}")
    return label


def load_snapshot_metadata(
    window: str | int,
    snapshot_root: Path | str = DEFAULT_SNAPSHOT_ROOT,
) -> pd.DataFrame:
    """Load and flatten the fields needed by the retrieval index."""
    label = normalize_window(window)
    window_dir = Path(snapshot_root) / f"window={label}"
    parts = sorted(window_dir.glob("part-*.parquet"))
    if not parts:
        raise FileNotFoundError(f"No STATE snapshot parts found under {window_dir}")

    snapshots = pd.concat(
        [pd.read_parquet(path) for path in parts],
        ignore_index=True,
    )
    required = {"event_id", "structured_values", "matching_text"}
    missing = required - set(snapshots.columns)
    if missing:
        raise ValueError(f"STATE snapshots for {label} lack columns: {sorted(missing)}")

    rows: list[dict[str, Any]] = []
    for snapshot in snapshots.itertuples(index=False):
        structured = snapshot.structured_values
        if isinstance(structured, str):
            structured = json.loads(structured)
        if not isinstance(structured, dict):
            raise TypeError(
                f"structured_values for {snapshot.event_id!r} is not a JSON object"
            )
        rows.append(
            {
                "event_id": str(snapshot.event_id),
                "messenger_class": str(structured.get("messenger_class") or ""),
                "localization_state": str(
                    structured.get("localization_state") or ""
                ),
                "has_counterpart": bool(structured.get("has_counterpart", False)),
                "z_known_at_T": bool(structured.get("z_known_at_T", False)),
                "matching_text": str(snapshot.matching_text),
                "_state_text_version": str(
                    getattr(snapshot, "state_text_version", "")
                ),
            }
        )

    metadata = pd.DataFrame(rows).sort_values("event_id").reset_index(drop=True)
    duplicates = metadata.loc[metadata["event_id"].duplicated(), "event_id"].tolist()
    if duplicates:
        raise ValueError(f"Duplicate event ids in {label} snapshots: {duplicates[:5]}")
    if (metadata["messenger_class"] == "").any():
        bad = metadata.loc[metadata["messenger_class"] == "", "event_id"].tolist()
        raise ValueError(f"Missing messenger_class in {label}: {bad[:5]}")
    return metadata


def load_encoder(model_name: str = MODEL_NAME):
    """Load the cached sentence-transformers model in strict offline CPU mode."""
    import torch
    from sentence_transformers import SentenceTransformer

    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    model = SentenceTransformer(
        model_name,
        device="cpu",
        local_files_only=True,
    )
    model.float()
    model.eval()
    return model


def embed_texts(
    texts: Iterable[str],
    encoder,
    *,
    batch_size: int = 16,
) -> np.ndarray:
    """Embed text as deterministic, L2-normalized float32 vectors."""
    materialized = [str(text) for text in texts]
    vectors = encoder.encode(
        materialized,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
        precision="float32",
    )
    vectors = np.ascontiguousarray(vectors, dtype=np.float32)
    expected = (len(materialized), EMBEDDING_DIMENSION)
    if vectors.shape != expected:
        raise ValueError(f"Unexpected embedding shape {vectors.shape}; expected {expected}")
    if not np.isfinite(vectors).all():
        raise ValueError("Embedding matrix contains non-finite values")
    return vectors


def npy_bytes(vectors: np.ndarray) -> bytes:
    """Serialize an array exactly as np.save does on disk."""
    buffer = io.BytesIO()
    np.save(buffer, np.ascontiguousarray(vectors, dtype=np.float32))
    return buffer.getvalue()


def write_index(
    window: str | int,
    vectors: np.ndarray,
    metadata: pd.DataFrame,
    *,
    embedding_seconds: float,
    index_root: Path | str = DEFAULT_INDEX_ROOT,
    extra_build_metadata: dict[str, str] | None = None,
) -> IndexBuildResult:
    """Write aligned vectors.npy and metadata.parquet for one window."""
    label = normalize_window(window)
    vectors = np.ascontiguousarray(vectors, dtype=np.float32)
    if vectors.shape != (len(metadata), EMBEDDING_DIMENSION):
        raise ValueError(
            f"Vector/metadata mismatch for {label}: {vectors.shape} vs {len(metadata)} rows"
        )

    output_dir = Path(index_root) / f"window={label}"
    output_dir.mkdir(parents=True, exist_ok=True)
    vectors_path = output_dir / "vectors.npy"
    metadata_path = output_dir / "metadata.parquet"
    vectors_path.write_bytes(npy_bytes(vectors))

    state_versions = sorted(
        set(metadata.get("_state_text_version", pd.Series(dtype=str)).dropna().astype(str))
        - {""}
    )
    build_metadata = {
        "embedding_model": MODEL_NAME,
        "embedding_dimension": str(EMBEDDING_DIMENSION),
        "embedding_dtype": "float32",
        "embedding_normalized": "true",
        "embedding_seconds": f"{embedding_seconds:.6f}",
        "n_vectors": str(len(metadata)),
        "state_text_versions": ",".join(state_versions),
        "window": label,
    }
    build_metadata.update(extra_build_metadata or {})
    table = pa.Table.from_pandas(
        metadata.loc[:, METADATA_COLUMNS],
        preserve_index=False,
    )
    encoded_metadata = {
        str(key).encode("utf-8"): str(value).encode("utf-8")
        for key, value in build_metadata.items()
    }
    table = table.replace_schema_metadata(encoded_metadata)
    pq.write_table(table, metadata_path)

    return IndexBuildResult(
        window=label,
        n_vectors=len(metadata),
        dimension=EMBEDDING_DIMENSION,
        embedding_seconds=embedding_seconds,
        vectors_path=vectors_path,
        metadata_path=metadata_path,
    )


def build_window_index(
    window: str | int,
    *,
    encoder=None,
    snapshot_root: Path | str = DEFAULT_SNAPSHOT_ROOT,
    index_root: Path | str = DEFAULT_INDEX_ROOT,
) -> IndexBuildResult:
    """Embed and persist one STATE snapshot window."""
    owns_encoder = encoder is None
    if owns_encoder:
        encoder = load_encoder()
    metadata = load_snapshot_metadata(window, snapshot_root)
    started = time.perf_counter()
    vectors = embed_texts(metadata["matching_text"], encoder)
    elapsed = time.perf_counter() - started
    return write_index(
        window,
        vectors,
        metadata,
        embedding_seconds=elapsed,
        index_root=index_root,
    )


def load_index(
    window: str | int,
    index_root: Path | str = DEFAULT_INDEX_ROOT,
) -> StateIndex:
    """Load and validate one in-memory NumPy retrieval index."""
    label = normalize_window(window)
    window_dir = Path(index_root) / f"window={label}"
    vectors_path = window_dir / "vectors.npy"
    metadata_path = window_dir / "metadata.parquet"
    if not vectors_path.exists() or not metadata_path.exists():
        raise FileNotFoundError(
            f"Missing index for {label}; expected {vectors_path} and {metadata_path}"
        )

    vectors = np.load(vectors_path, allow_pickle=False)
    metadata = pd.read_parquet(metadata_path)
    parquet_metadata = pq.read_schema(metadata_path).metadata or {}
    build_metadata = {
        key.decode("utf-8"): value.decode("utf-8")
        for key, value in parquet_metadata.items()
    }
    if vectors.dtype != np.float32:
        raise ValueError(f"{vectors_path} has dtype {vectors.dtype}, expected float32")
    if vectors.shape != (len(metadata), EMBEDDING_DIMENSION):
        raise ValueError(
            f"Index alignment failure for {label}: {vectors.shape} vs {len(metadata)} rows"
        )
    if list(metadata.columns) != list(METADATA_COLUMNS):
        raise ValueError(
            f"Unexpected metadata columns for {label}: {list(metadata.columns)}"
        )
    if metadata["event_id"].duplicated().any():
        raise ValueError(f"Duplicate event ids in index metadata for {label}")
    return StateIndex(
        window=label,
        vectors=np.ascontiguousarray(vectors),
        metadata=metadata.reset_index(drop=True),
        build_metadata=build_metadata,
    )
