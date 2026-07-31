# Data Snapshot Pointer

- Snapshot ID: `pre2026-freeze-v1-pilot-20260731`
- Freeze timestamp: `2026-07-31T20:07:21+02:00`
- Intended storage: IJCLab OwnCloud
- Current status: local only; upload pending
- Local snapshot path: `/home/meneses/project_astronomical/MAFORAI_FREEZES/pre2026-freeze-v1-pilot-20260731/`
- Payload size before the post-tag Git bundle: 219,119,990 bytes (208.97 MiB)
- Manifested files: 292
- Manifest SHA-256: `fe9a0af58aa582d54a0fae19bb74502cf51815553273ecabe98dac93d867534b`
- Access classification: restricted

The absolute path above is local to the creation workstation and is not portable. A future downloaded copy must retain the snapshot directory structure and ID.

Verify the payload from the snapshot root with:

```bash
sha256sum -c FREEZE_MANIFEST.sha256
```

Verify the post-tag Git bundle separately with:

```bash
sha256sum MAFORAI_pre2026_freeze_v1.bundle
git bundle verify MAFORAI_pre2026_freeze_v1.bundle
```

Compare the bundle hash with `BUNDLE_VERIFICATION.txt` and the execution report. The exact final directory size, including the post-tag bundle, is recorded in the execution report because the bundle can only be produced after the metadata commit and local annotated tag exist.

No OwnCloud credential or private access URL is stored here.
