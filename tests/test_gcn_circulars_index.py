from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skyportal_corpus.extraction.gcn_circulars_index import (
    build_row,
    infer_archive_run_id,
    run_gcn_circulars_index_build,
    safe_timestamp_to_iso,
)


class GcnCircularsIndexTests(unittest.TestCase):
    def test_infer_archive_run_id_from_input_dir(self) -> None:
        path = Path("data/raw/gcn/circulars/archive_json/20260610_112607/extracted/archive.json")
        self.assertEqual(infer_archive_run_id(path), "20260610_112607")

    def test_safe_timestamp_to_iso_handles_milliseconds(self) -> None:
        self.assertEqual(
            safe_timestamp_to_iso(918181878000),
            "1999-02-05T02:31:18+00:00",
        )
        self.assertIsNone(safe_timestamp_to_iso("not-a-timestamp"))

    def test_build_row_normalizes_expected_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "251.json"
            path.write_text(
                json.dumps(
                    {
                        "circularId": 251,
                        "createdOn": 918181878000,
                        "subject": "GRB 990123",
                        "body": "Hello world",
                        "submitter": "Test User",
                        "eventId": "GRB 990123",
                    }
                ),
                encoding="utf-8",
            )

            row = build_row(path, "20260610_112607", "2026-06-10T11:30:00+00:00")

            self.assertEqual(row["circular_id_raw"], "251")
            self.assertEqual(row["circular_id"], "251")
            self.assertEqual(row["event_id"], "GRB 990123")
            self.assertEqual(row["body_length"], 11)
            self.assertEqual(row["subject_length"], 10)
            self.assertEqual(
                row["schema_signature"],
                "body|circularId|createdOn|eventId|subject|submitter",
            )

    def test_run_build_writes_outputs_and_collects_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_dir = tmp_path / "archive_json" / "20260610_112607" / "extracted" / "archive.json"
            input_dir.mkdir(parents=True)
            output_dir = tmp_path / "interim"

            (input_dir / "good.json").write_text(
                json.dumps(
                    {
                        "circularId": 100,
                        "createdOn": 918181878000,
                        "subject": "Subject",
                        "body": "Body text",
                        "submitter": "Submitter",
                        "email": "test@example.com",
                    }
                ),
                encoding="utf-8",
            )
            (input_dir / "bad.json").write_text("{not valid json", encoding="utf-8")

            args = argparse.Namespace(
                input_dir=str(input_dir),
                output_dir=str(output_dir),
            )

            with patch("pandas.DataFrame.to_parquet") as mock_to_parquet:
                def fake_to_parquet(path: Path, *args: object, **kwargs: object) -> None:
                    Path(path).write_bytes(b"fake parquet")

                mock_to_parquet.side_effect = fake_to_parquet
                run_gcn_circulars_index_build(args)

            report = json.loads((output_dir / "index_report.json").read_text(encoding="utf-8"))
            csv_text = (output_dir / "1999" / "circulars_index.csv").read_text(encoding="utf-8")
            errors_text = (output_dir / "index_errors.jsonl").read_text(encoding="utf-8")

            self.assertIn("good.json", csv_text)
            self.assertEqual(report["total_files_seen"], 2)
            self.assertEqual(report["total_indexed"], 1)
            self.assertEqual(report["total_errors"], 1)
            self.assertEqual(report["indexed_by_year"], {"1999": 1})
            self.assertIn("1999", report["output_files"]["by_year"])
            self.assertIn("bad.json", errors_text)


if __name__ == "__main__":
    unittest.main()
