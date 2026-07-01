from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from skyportal_corpus.extraction.gcn_inception_dossiers import (
    build_default_title,
    choose_best_association_rows,
    load_selected_sources_lookup,
    resolve_circular_body,
    run_gcn_inception_event_dossier_build,
    safe_source_id,
)


class GcnInceptionDossiersTests(unittest.TestCase):
    def test_safe_source_id_sanitizes_for_output_paths(self) -> None:
        self.assertEqual(safe_source_id("GRB 260610B / AT2026owq"), "GRB_260610B_AT2026owq")

    def test_choose_best_association_rows_keeps_best_score_per_circular(self) -> None:
        dataframe = pd.DataFrame(
            [
                {
                    "source_id": "2026owq",
                    "circular_id": "50001",
                    "best_match_score": 75,
                    "best_confidence_level": "medium_confidence",
                    "created_at_iso": "2026-06-10T20:00:00+00:00",
                },
                {
                    "source_id": "2026owq",
                    "circular_id": "50001",
                    "best_match_score": 95,
                    "best_confidence_level": "high_confidence",
                    "created_at_iso": "2026-06-10T20:00:00+00:00",
                },
                {
                    "source_id": "2026owq",
                    "circular_id": "50002",
                    "best_match_score": 60,
                    "best_confidence_level": "medium_confidence",
                    "created_at_iso": "",
                },
            ]
        )

        deduplicated = choose_best_association_rows(dataframe)

        self.assertEqual(deduplicated["circular_id"].tolist(), ["50001", "50002"])
        self.assertEqual(int(deduplicated.iloc[0]["best_match_score"]), 95)

    def test_load_selected_sources_lookup_supports_sources_and_selected_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "selected_sources.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "selected_sources": [
                            {
                                "id": "2026owq",
                                "selection_context": {"aliases": ["GRB 260610B"]},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            lookup = load_selected_sources_lookup(payload_path)

            self.assertIn("2026owq", lookup)

    def test_build_default_title_uses_first_alias_when_available(self) -> None:
        title = build_default_title(
            "2026owq",
            source_row={"aliases": ["GRB 260610B", "AT2026owq"]},
            explicit_title=None,
        )

        self.assertEqual(title, "GRB 260610B / 2026owq")

    def test_resolve_circular_body_falls_back_to_year_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            year_dir = root / "2026"
            year_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {
                        "circular_id": "50010",
                        "body": "Fallback body from year index.",
                    }
                ]
            ).to_csv(year_dir / "circulars_index.csv", index=False)

            row = pd.Series(
                {
                    "circular_id": "50010",
                    "year": 2026,
                    "raw_file_path": root / "missing.json",
                }
            )

            body = resolve_circular_body(row, gcn_root=root)

            self.assertEqual(body, "Fallback body from year index.")

    def test_run_build_writes_dossier_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_50001 = root / "50001.json"
            raw_50002 = root / "50002.json"
            raw_50001.write_text(
                json.dumps({"body": "First circular body."}),
                encoding="utf-8",
            )
            raw_50002.write_text(
                json.dumps({"body": "Second circular body."}),
                encoding="utf-8",
            )

            associations_path = root / "event_gcn_associations.csv"
            pd.DataFrame(
                [
                    {
                        "source_id": "2026owq",
                        "circular_id": "50002",
                        "gcn_event_id": "GRB 260610B",
                        "subject": "Second circular",
                        "created_at_iso": "",
                        "year": 2026,
                        "best_matched_term": "AT2026owq",
                        "best_matched_field": "body",
                        "best_match_type": "original_term",
                        "best_match_score": 75,
                        "best_confidence_level": "medium_confidence",
                        "evidence_text": "second evidence",
                        "raw_file_path": str(raw_50002),
                        "matched_terms": "AT2026owq",
                        "matched_fields": "body",
                    },
                    {
                        "source_id": "2026owq",
                        "circular_id": "50001",
                        "gcn_event_id": "GRB 260610B",
                        "subject": "First circular",
                        "created_at_iso": "2026-06-10T20:37:00+00:00",
                        "year": 2026,
                        "best_matched_term": "GRB 260610B",
                        "best_matched_field": "subject",
                        "best_match_type": "original_term",
                        "best_match_score": 100,
                        "best_confidence_level": "high_confidence",
                        "evidence_text": "first evidence",
                        "raw_file_path": str(raw_50001),
                        "matched_terms": "GRB 260610B",
                        "matched_fields": "subject",
                    },
                    {
                        "source_id": "2026owq",
                        "circular_id": "50001",
                        "gcn_event_id": "GRB 260610B",
                        "subject": "First circular duplicate",
                        "created_at_iso": "2026-06-10T20:37:00+00:00",
                        "year": 2026,
                        "best_matched_term": "2026owq",
                        "best_matched_field": "body",
                        "best_match_type": "generated_variant",
                        "best_match_score": 60,
                        "best_confidence_level": "low_confidence",
                        "evidence_text": "duplicate evidence",
                        "raw_file_path": str(raw_50001),
                        "matched_terms": "2026owq",
                        "matched_fields": "body",
                    },
                ]
            ).to_csv(associations_path, index=False)

            selected_sources_path = root / "gcn_grandma.json"
            selected_sources_path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "2026owq",
                                "aliases": ["GRB 260610B", "AT2026owq"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            output_dir = root / "inception_dossiers"
            run_gcn_inception_event_dossier_build(
                SimpleNamespace(
                    source_id="2026owq",
                    title=None,
                    associations_path=associations_path,
                    selected_sources_path=selected_sources_path,
                    gcn_root=root / "circulars",
                    output_dir=output_dir,
                    include_low_confidence=False,
                )
            )

            dossier_path = output_dir / "2026owq_inception_dossier.txt"
            manifest_path = output_dir / "2026owq_inception_dossier_manifest.json"

            self.assertTrue(dossier_path.exists())
            self.assertTrue(manifest_path.exists())

            dossier_text = dossier_path.read_text(encoding="utf-8")
            self.assertIn("EVENT DOSSIER — PILOT ANNOTATION", dossier_text)
            self.assertIn("GRB 260610B / 2026owq", dossier_text)
            self.assertIn("- GRB 260610B", dossier_text)
            self.assertIn("- AT2026owq", dossier_text)
            self.assertLess(
                dossier_text.index("CIRCULAR 50001"),
                dossier_text.index("CIRCULAR 50002"),
            )
            self.assertIn("First circular body.", dossier_text)
            self.assertIn("Second circular body.", dossier_text)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_id"], "2026owq")
            self.assertEqual(manifest["title"], "GRB 260610B / 2026owq")
            self.assertEqual(manifest["n_circulars"], 2)
            self.assertEqual(manifest["circular_ids"], ["50001", "50002"])


if __name__ == "__main__":
    unittest.main()
