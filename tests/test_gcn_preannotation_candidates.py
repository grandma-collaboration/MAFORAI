from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from skyportal_corpus.extraction.gcn_preannotation_candidates import (
    build_preannotation_candidates,
    find_offsets,
    map_claim_to_inception,
    resolve_selected_source_ids,
    resolve_dossier_offsets,
)
from skyportal_corpus.extraction.gcn_preannotation_review import (
    PILOT_REVIEW_COLUMNS,
    build_context_fields,
    build_pilot_review_table,
)


class GcnPreannotationCandidatesTests(unittest.TestCase):
    def test_build_context_fields_marks_evidence_text(self) -> None:
        before, after, combined = build_context_fields(
            text="aaaa evidence bbbb",
            begin=5,
            end=13,
            radius=10,
        )

        self.assertEqual(before, "aaaa")
        self.assertEqual(after, "bbbb")
        self.assertIn("[[evidence]]", combined)

    def test_find_offsets_returns_exact_match_positions(self) -> None:
        matches = find_offsets("abc trigger here abc", "trigger here")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].begin, 4)
        self.assertEqual(matches[0].end, 16)

    def test_resolve_dossier_offsets_uses_circular_block_to_disambiguate(self) -> None:
        dossier_text = (
            "================================================================================\n"
            "CIRCULAR 1\n"
            "CREATED_AT: 2026-01-01T00:00:00+00:00\n"
            "SUBJECT: A\n"
            "================================================================================\n\n"
            "shared evidence\n\n"
            "================================================================================\n"
            "CIRCULAR 2\n"
            "CREATED_AT: 2026-01-02T00:00:00+00:00\n"
            "SUBJECT: B\n"
            "================================================================================\n\n"
            "shared evidence\n"
        )

        match, flags = resolve_dossier_offsets(
            evidence_text="shared evidence",
            dossier_text=dossier_text,
            circular_id="2",
        )

        self.assertEqual(flags, [])
        self.assertIsNotNone(match)
        self.assertEqual(dossier_text[match.begin : match.end], "shared evidence")

    def test_map_claim_to_inception_for_trigger_time_is_direct_and_low_risk(self) -> None:
        row = pd.Series(
            {
                "claim_type": "trigger_time_t0",
                "extraction_rule": "trigger_t0_explicit",
                "claim_confidence": "high",
                "raw_value": "2026-01-01T12:00:00 UTC",
                "normalized_value": "2026-01-01T12:00:00",
                "evidence_text": "T0 = 2026-01-01T12:00:00 UTC",
                "instrument_if_any": "Fermi GBM",
            }
        )

        mapping = map_claim_to_inception(row)

        self.assertEqual(mapping["inception_layer"], "EVENT_EVIDENCE")
        self.assertEqual(mapping["inception_label"], "TRIGGER_TIME")
        self.assertTrue(mapping["can_preannotate"])
        self.assertEqual(mapping["risk_level"], "low")

    def test_build_preannotation_candidates_marks_direct_claim_ready_when_dossier_offsets_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw_json_path = root / "50001.json"
            raw_json_path.write_text(
                json.dumps({"body": "T0 = 2026-01-01T12:00:00 UTC"}),
                encoding="utf-8",
            )

            dossiers_dir = root / "inception_dossiers"
            dossiers_dir.mkdir(parents=True, exist_ok=True)
            dossier_path = dossiers_dir / "2026owq_inception_dossier.txt"
            dossier_path.write_text(
                "================================================================================\n"
                "CIRCULAR 50001\n"
                "CREATED_AT: 2026-01-01T12:10:00+00:00\n"
                "SUBJECT: GRB 260101A\n"
                "================================================================================\n\n"
                "T0 = 2026-01-01T12:00:00 UTC\n",
                encoding="utf-8",
            )

            selected_sources_path = root / "gcn_grandma.json"
            selected_sources_path.write_text(
                json.dumps({"sources": [{"id": "2026owq", "aliases": ["GRB 260101A"]}]}),
                encoding="utf-8",
            )

            claims = pd.DataFrame(
                [
                    {
                        "source_id": "2026owq",
                        "circular_id": "50001",
                        "year": 2026,
                        "created_at_iso": "2026-01-01T12:10:00+00:00",
                        "subject": "GRB 260101A",
                        "claim_type": "trigger_time_t0",
                        "raw_value": "2026-01-01T12:00:00 UTC",
                        "normalized_value": "2026-01-01T12:00:00",
                        "instrument_if_any": "",
                        "evidence_text": "T0 = 2026-01-01T12:00:00 UTC",
                        "extraction_rule": "trigger_t0_explicit",
                        "claim_confidence": "high",
                        "source_field": "body",
                        "raw_file_path": str(raw_json_path),
                        "best_match_score": 100,
                        "best_confidence_level": "high_confidence",
                    }
                ]
            )

            candidates = build_preannotation_candidates(
                claims,
                gcn_root=root / "circulars",
                dossiers_dir=dossiers_dir,
                selected_sources_path=selected_sources_path,
                dossier_lookup={"2026owq": dossier_path},
            )

            self.assertEqual(len(candidates), 1)
            self.assertEqual(
                candidates.iloc[0]["preannotation_status"],
                "ready_for_preannotation",
            )
            self.assertTrue(bool(candidates.iloc[0]["offset_valid"]))
            self.assertEqual(candidates.iloc[0]["inception_label"], "TRIGGER_TIME")

    def test_resolve_selected_source_ids_defaults_to_available_dossiers_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dossiers_dir = root / "inception_dossiers"
            dossiers_dir.mkdir(parents=True, exist_ok=True)

            (dossiers_dir / "2026owq_inception_dossier.txt").write_text("doc", encoding="utf-8")
            (dossiers_dir / "2026owq_inception_dossier_manifest.json").write_text(
                json.dumps({"source_id": "2026owq", "output_path": str(dossiers_dir / "2026owq_inception_dossier.txt")}),
                encoding="utf-8",
            )

            claims = pd.DataFrame(
                [
                    {"source_id": "2026owq"},
                    {"source_id": "other_event"},
                ]
            )

            selected_source_ids, dossier_lookup = resolve_selected_source_ids(
                claims_dataframe=claims,
                dossiers_dir=dossiers_dir,
                source_ids=None,
                document_names=None,
            )

            self.assertEqual(selected_source_ids, {"2026owq"})
            self.assertIn("2026owq", dossier_lookup)

    def test_resolve_selected_source_ids_supports_source_and_document_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dossiers_dir = root / "inception_dossiers"
            dossiers_dir.mkdir(parents=True, exist_ok=True)

            first_dossier = dossiers_dir / "2026owq_inception_dossier.txt"
            second_dossier = dossiers_dir / "pilot2_inception_dossier.txt"
            first_dossier.write_text("doc1", encoding="utf-8")
            second_dossier.write_text("doc2", encoding="utf-8")
            (dossiers_dir / "2026owq_inception_dossier_manifest.json").write_text(
                json.dumps({"source_id": "2026owq", "output_path": str(first_dossier)}),
                encoding="utf-8",
            )
            (dossiers_dir / "pilot2_inception_dossier_manifest.json").write_text(
                json.dumps({"source_id": "pilot2", "output_path": str(second_dossier)}),
                encoding="utf-8",
            )

            claims = pd.DataFrame([{"source_id": "2026owq"}, {"source_id": "pilot2"}])

            selected_source_ids, _ = resolve_selected_source_ids(
                claims_dataframe=claims,
                dossiers_dir=dossiers_dir,
                source_ids=["2026owq", "missing"],
                document_names=["2026owq_inception_dossier.txt"],
            )

            self.assertEqual(selected_source_ids, {"2026owq"})

    def test_pilot_review_table_marks_44891_as_identity_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dossier_path = root / "2026owq_inception_dossier.txt"
            dossier_text = (
                "================================================================================\n"
                "CIRCULAR 44891\n"
                "CREATED_AT: 2026-06-10T10:18:35+00:00\n"
                "SUBJECT: GRB 260610A: Fermi notice\n"
                "================================================================================\n\n"
                "At 10:07:46 UT on 10 Jun 2026\n"
            )
            dossier_path.write_text(dossier_text, encoding="utf-8")
            evidence_text = "At 10:07:46 UT on 10 Jun 2026"
            begin = dossier_text.index(evidence_text)
            end = begin + len(evidence_text)

            candidates = pd.DataFrame(
                [
                    {
                        "source_id": "2026owq",
                        "document_name": dossier_path.name,
                        "circular_id": "44891",
                        "subject": "GRB 260610A: Fermi notice",
                        "created_at_iso": "2026-06-10T10:18:35+00:00",
                        "claim_type": "trigger_time_t0",
                        "evidence_text": evidence_text,
                        "value": "2026-06-10T10:07:46",
                        "unit": "",
                        "claim_confidence": "high",
                        "extraction_rule": "trigger_ut_context",
                        "inception_layer": "EVENT_EVIDENCE",
                        "inception_label": "TRIGGER_TIME",
                        "measurement_type": "",
                        "target": "event",
                        "certainty": "confirmed",
                        "dossier_path": str(dossier_path),
                        "dossier_begin_offset": begin,
                        "dossier_end_offset": end,
                        "body_begin_offset": None,
                        "body_end_offset": None,
                        "subject_begin_offset": None,
                        "subject_end_offset": None,
                        "offset_valid": True,
                        "preannotation_status": "ready_for_preannotation",
                        "can_preannotate": True,
                        "needs_llm_verification": "no",
                        "needs_human_review": "no",
                        "risk_level": "low",
                        "risk_reason": "test",
                        "recommended_action": "preannotate_directly",
                        "quality_flags": "",
                        "raw_file_path": "",
                    }
                ]
            )

            review = build_pilot_review_table(candidates, source_id="2026owq")

            self.assertEqual(
                review.iloc[0]["identity_warning"],
                "possible_event_identity_or_matching_conflict",
            )
            self.assertFalse(bool(review.iloc[0]["ready_for_inception_preannotation"]))
            self.assertEqual(
                review.iloc[0]["manual_priority"],
                "5_identity_warning",
            )

    def test_pilot_review_table_contains_manual_columns_and_empty_reviewer_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dossier_path = root / "2026owq_inception_dossier.txt"
            dossier_text = (
                "================================================================================\n"
                "CIRCULAR 44944\n"
                "CREATED_AT: 2026-06-12T00:00:00+00:00\n"
                "SUBJECT: GRB 260610B\n"
                "================================================================================\n\n"
                "T90 = 65 s\n"
            )
            dossier_path.write_text(dossier_text, encoding="utf-8")
            evidence_text = "T90 = 65 s"
            begin = dossier_text.index(evidence_text)
            end = begin + len(evidence_text)

            candidates = pd.DataFrame(
                [
                    {
                        "source_id": "2026owq",
                        "document_name": dossier_path.name,
                        "circular_id": "44944",
                        "subject": "GRB 260610B",
                        "created_at_iso": "2026-06-12T00:00:00+00:00",
                        "claim_type": "duration_t90",
                        "evidence_text": evidence_text,
                        "value": "65",
                        "unit": "s",
                        "claim_confidence": "high",
                        "extraction_rule": "duration_t90_explicit",
                        "inception_layer": "EVENT_EVIDENCE",
                        "inception_label": "T90",
                        "measurement_type": "",
                        "target": "event",
                        "certainty": "confirmed",
                        "dossier_path": str(dossier_path),
                        "dossier_begin_offset": begin,
                        "dossier_end_offset": end,
                        "body_begin_offset": None,
                        "body_end_offset": None,
                        "subject_begin_offset": None,
                        "subject_end_offset": None,
                        "offset_valid": True,
                        "preannotation_status": "ready_for_preannotation",
                        "can_preannotate": True,
                        "needs_llm_verification": "no",
                        "needs_human_review": "no",
                        "risk_level": "low",
                        "risk_reason": "test",
                        "recommended_action": "preannotate_directly",
                        "quality_flags": "",
                        "raw_file_path": "",
                    }
                ]
            )

            review = build_pilot_review_table(candidates, source_id="2026owq")

            self.assertEqual(list(review.columns), PILOT_REVIEW_COLUMNS)
            self.assertEqual(review.iloc[0]["review_decision"], "")
            self.assertEqual(review.iloc[0]["reviewer_notes"], "")


if __name__ == "__main__":
    unittest.main()
