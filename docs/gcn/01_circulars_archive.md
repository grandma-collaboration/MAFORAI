# GCN Circular Archive and Yearly Index

## Goal

This stage prepares the raw and indexed GCN Circular corpus used by the rest of
the workflow.

It has two parts:

1. download the official GCN Circular JSON archive;
2. build a normalized tabular index partitioned by year.

## Entry points

| File | Role |
|---|---|
| `scripts/gcn/01_download_circulars_archive.py` | Download one raw GCN Circular archive run |
| `scripts/gcn/02_build_circulars_index.py` | Build the normalized yearly index from one extracted raw run |
| `src/skyportal_corpus/extraction/gcn_circulars_archive.py` | Archive download and extraction logic |
| `src/skyportal_corpus/extraction/gcn_circulars_index.py` | Index-building and year partitioning logic |

## Step 1. Download the raw archive

Default archive URL:

```text
https://gcn.nasa.gov/circulars/archive.json.tar.gz
```

Typical command:

```bash
python scripts/gcn/01_download_circulars_archive.py --extract
```

Optional CLI arguments:

- `--url`
- `--output-dir`
- `--extract`

Default output root:

```text
data/raw/gcn/circulars/archive_json
```

Each run creates:

```text
data/raw/gcn/circulars/archive_json/<run_id>/
```

Typical contents:

- `gcn_circulars_json.tar.gz`
- `manifest.json`
- `download_circulars_archive.log`
- `extracted/` when `--extract` is used

Notes:

- `<run_id>` is a timestamp such as `20260610_143000`;
- the manifest records the URL, the checksum, download metadata, and the list
  of extracted files;
- extraction is optional but normally needed before indexing.

## Step 2. Build the normalized index

Typical command:

```bash
python scripts/gcn/02_build_circulars_index.py \
  --input-dir data/raw/gcn/circulars/archive_json/<run_id>/extracted/archive.json
```

Optional CLI arguments:

- `--input-dir`
- `--output-dir`

Default output root:

```text
data/interim/gcn/circulars
```

The index step writes:

- one `circulars_index.csv` per year;
- one `circulars_index.parquet` per year;
- one shared `index_report.json`;
- one shared `index_errors.jsonl`;
- one shared `circulars_index.log`.

Typical layout:

```text
data/interim/gcn/circulars/
├── 2023/
│   ├── circulars_index.csv
│   └── circulars_index.parquet
├── 2024/
│   ├── circulars_index.csv
│   └── circulars_index.parquet
├── 2025/
│   ├── circulars_index.csv
│   └── circulars_index.parquet
├── 2026/
│   ├── circulars_index.csv
│   └── circulars_index.parquet
├── circulars_index.log
├── index_errors.jsonl
└── index_report.json
```

## Normalized columns

The normalized index keeps a broad row per raw Circular with fields such as:

- `archive_run_id`
- `raw_file_name`
- `raw_file_path`
- `circular_id_raw`
- `circular_id`
- `bibcode`
- `event_id`
- `subject`
- `body`
- `created_on`
- `created_at_iso`
- `submitter`
- `email`
- `submitted_how`
- `format`
- `edited_by`
- `edited_on`
- `edited_at_iso`
- `body_length`
- `subject_length`
- `body_hash`
- `schema_signature`
- `processed_at`

Important design choices:

- `circular_id` is stored as a string;
- raw `body` text is preserved at this stage;
- the index does not try to extract scientific claims yet;
- the index does not assume a single strict schema across all raw JSON files.

## What to inspect after the run

The main quick checks are:

- `index_report.json`
  - total files seen
  - total indexed
  - total errors
  - indexed rows by year
  - most common schema signatures
- `index_errors.jsonl`
  - only needed when some raw files failed to parse
- one yearly `circulars_index.parquet`
  - this becomes the main input for the matching stage

## Handoff to Step A

The matching stage usually reads only a subset of years from:

```text
data/interim/gcn/circulars/<year>/circulars_index.parquet
```

In the current workflow, the active default range is:

- `2023`
- `2024`
- `2025`
- `2026`
