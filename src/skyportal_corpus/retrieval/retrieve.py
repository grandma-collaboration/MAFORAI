"""Hybrid hard-filter plus dense-cosine retrieval over STATE indexes."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .embed import DEFAULT_INDEX_ROOT, StateIndex, load_index

RESULT_COLUMNS = (
    "rank",
    "event_id",
    "score",
    "messenger_class",
    "localization_state",
    "has_counterpart",
    "z_known_at_T",
    "matching_text",
)


def retrieve_from_index(
    query_event_id: str,
    state_index: StateIndex,
    k: int = 5,
) -> pd.DataFrame:
    """Return top-k other events after filtering on messenger_class."""
    if k < 1:
        raise ValueError("k must be at least 1")

    metadata = state_index.metadata
    query_rows = metadata.index[metadata["event_id"] == str(query_event_id)].tolist()
    if not query_rows:
        raise KeyError(
            f"Event {query_event_id!r} is not in the {state_index.window} index"
        )
    query_position = query_rows[0]
    query_class = metadata.at[query_position, "messenger_class"]

    # The physical messenger filter is intentionally applied before any cosine score.
    candidate_mask = (
        metadata["messenger_class"].eq(query_class)
        & metadata["event_id"].ne(str(query_event_id))
    )
    candidate_positions = np.flatnonzero(candidate_mask.to_numpy())
    if not len(candidate_positions):
        return pd.DataFrame(columns=RESULT_COLUMNS)

    query_vector = state_index.vectors[query_position]
    scores = state_index.vectors[candidate_positions] @ query_vector
    event_ids = metadata.iloc[candidate_positions]["event_id"].astype(str).to_numpy()
    order = np.lexsort((event_ids, -scores))[: min(k, len(candidate_positions))]
    selected_positions = candidate_positions[order]
    selected_scores = scores[order]

    results = metadata.iloc[selected_positions].copy()
    results.insert(0, "score", selected_scores.astype(float))
    results.insert(0, "rank", np.arange(1, len(results) + 1, dtype=int))
    return results.loc[:, RESULT_COLUMNS].reset_index(drop=True)


def retrieve(
    query_event_id: str,
    window: str | int,
    k: int = 5,
    *,
    index_root: Path | str = DEFAULT_INDEX_ROOT,
) -> pd.DataFrame:
    """Load one window and retrieve same-messenger neighbours by cosine similarity."""
    return retrieve_from_index(query_event_id, load_index(window, index_root), k)
