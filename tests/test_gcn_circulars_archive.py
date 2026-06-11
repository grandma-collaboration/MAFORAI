from __future__ import annotations

import argparse
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skyportal_corpus.extraction.gcn_circulars_archive import (
    extract_archive_file,
    run_gcn_circulars_archive_download,
)


class GcnCircularsArchiveTests(unittest.TestCase):
    def test_extract_archive_file_returns_extracted_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            archive_path = tmp_path / "archive.tar.gz"
            payload_path = tmp_path / "archive.json"
            payload_path.write_text('{"status": "ok"}', encoding="utf-8")

            with tarfile.open(archive_path, mode="w:gz") as archive:
                archive.add(payload_path, arcname="archive.json")

            extract_dir = tmp_path / "extracted"
            extracted_files = extract_archive_file(archive_path, extract_dir)

            self.assertEqual(extracted_files, ["archive.json"])
            self.assertTrue((extract_dir / "archive.json").exists())

    def test_run_download_creates_run_directory_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            args = argparse.Namespace(
                url="https://example.test/archive.tar.gz",
                output_dir=str(tmp_path / "runs"),
                extract=True,
            )

            with patch(
                "skyportal_corpus.extraction.gcn_circulars_archive.generate_run_id",
                return_value="20260610_143000",
            ), patch(
                "skyportal_corpus.extraction.gcn_circulars_archive.download_archive_file",
            ) as mock_download, patch(
                "skyportal_corpus.extraction.gcn_circulars_archive.compute_sha256",
                return_value="abc123",
            ), patch(
                "skyportal_corpus.extraction.gcn_circulars_archive.extract_archive_file",
                return_value=["archive.json"],
            ):
                def fake_download(
                    *,
                    url: str,
                    destination: Path,
                    **_: object,
                ) -> dict[str, object]:
                    destination.write_bytes(b"archive-bytes")
                    return {
                        "url": url,
                        "destination": str(destination),
                        "http_status_code": 200,
                        "content_type": "application/gzip",
                        "content_length_header": "13",
                        "attempts_used": 1,
                        "downloaded_bytes": 13,
                    }

                mock_download.side_effect = fake_download

                run_gcn_circulars_archive_download(args)

            run_dir = tmp_path / "runs" / "20260610_143000"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertTrue((run_dir / "gcn_circulars_json.tar.gz").exists())
            self.assertEqual(manifest["run_id"], "20260610_143000")
            self.assertEqual(manifest["archive_file"], "gcn_circulars_json.tar.gz")
            self.assertEqual(manifest["extract_directory"], str(run_dir / "extracted"))
            self.assertEqual(manifest["extracted_files"], ["archive.json"])
            self.assertEqual(manifest["download"]["sha256"], "abc123")


if __name__ == "__main__":
    unittest.main()
