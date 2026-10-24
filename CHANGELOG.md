# Changelog

## 0.1.0 - 2026-10-24
First working version. Built after a two-day baseline with a title-only
tracker showed 70% of working time was unclassifiable.

Added
- Interval-based SQLite store; immutable `obs`/`evidence`, editable `labels`.
- Altium Auto Save / Local History / file-save watching, which is what makes
  schematic vs PCB vs symbol vs footprint work separable.
- Signal ladder with per-label confidence and a human-readable reason.
- Altium dialog dictionary (DRC, ECO, BOM, Polygon Pour, PCB Model, Replace,
  Update From Library and more), marked OBSERVED or UNVERIFIED.
- Full 24-hour accounting: work + idle + locked + off equals wall clock.
- Single-instance lock, heartbeat, crash recovery, overlap-proof aggregation.
- Idle backdating with a cross-check against the previous sample.
- Retroactive `backfill` so the start of a session is labelled once the first
  Auto Save arrives.
- Auto-proposed projects and clients; every name editable, history keyed to a
  stable id.
- Local dashboard with a review queue, inline label editing, project rename
  and a daily free-text note.
- `report` (md/csv/json), `note`, `log`, `status`, `doctor`, `selfcheck`,
  `probe` commands.
- `tests/replay_day.py`: 20 checks over a synthetic workday.

Known limits
- Live tracking is Windows only.
- Viewing without editing produces no Auto Save, so review-only time needs
  the review queue or a manual note.
- Browser tracking sees the active tab title only; no URL, no extension.
- Lock detection uses `OpenInputDesktop`; sleep and shutdown are inferred
  from heartbeat gaps rather than Windows power events.
