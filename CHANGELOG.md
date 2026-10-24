# Changelog

## 0.4.0 - 2026-10-24
Added
- No work block is left without a project. Order: project file or title,
  project alias, a distinctive word shared between a project name and the
  window title or open document, else a GUESS from the project last named by
  a real signal (live) or the nearest such block in time (past data).
  Guesses are flagged (`labels.project_guess`), shown in amber in Review and
  striped on the timeline, counted as "Project guessed" in every report, and
  kept as recorded if ignored. Saving a block clears the flag.
- "Accept all as shown" in Review.
- Tracker on/off: Stop / Start tracking on the dashboard, `pcbtrack stop
  [--all]`, `stop.bat`; "start at login" switch and `pcbtrack autostart
  on|off`; "Close dashboard" button.

## 0.3.0 - 2026-10-24
From the first live day on the owner's PC.

Added
- Create projects (with client and parent) before any file is seen, from the
  Projects card or "+ new project" in any dropdown.
- Custom work stages ("+ new stage"), plus built-in `study_learning`,
  `pcb_layout` and `assembly_testing`.
- Add time by hand for any date and time range (study, meetings, milling,
  soldering, or correcting a wrong stretch). Hand entries replace tracked time
  for the same minutes and can be removed.
- Notes can cover a date range and several projects.
- Report for a period: from/to dates, presets (this/last week, month),
  project filter; download Markdown, a summary CSV (project x stage, project
  x document) or every block as CSV.
- "Files by project" card; durations under a minute are shown in seconds.

Fixed
- One-tick blocks counted 0 s and each block change leaked a tick to "off";
  short document visits never appeared. Fixed at read time, old data included.
- Stage carry-over leaked from Altium into Claude/Edge time.
- A `.PcbLib` shown in the PCB-class editor was labelled routing.
- An open PcbDoc is now `pcb_layout`, not `routing`: placement vs routing is
  confirmed in review.
- Dashboard default date used UTC and showed the wrong day after midnight.
- The minute refresh no longer wipes unsaved review/project edits.
- Untitled Altium dialogs read the active document from their owner window.

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

## 0.2.0 - 2026-10-24

The probe paid off: Altium's active document turns out to be readable after
all, which changes the primary signal and removes the Auto Save dependency
for stage detection.

Added
- `pcbtrack/altium.py`: reads the ACTIVE DOCUMENT from Altium's child windows
  (`TdxTabSheet` / `TViewComponent` captions, plus the visible
  `T*View_GraphicalForm`) with plain Win32 - no UI Automation, no COM, no
  plugin. Confirmed against a real probe of Altium Designer 26.7.1.
  Consequence: **viewing** is now tracked, not only editing, and all four
  stages separate instantly.
- Sub-project grouping: `projects.parent_id`, report roll-up, and a
  "Groups under" dropdown, so one client job can hold several Altium projects.
- Live view: `/api/now`, a 291-byte payload polled every 5 s, with a strip
  showing current stage, document, project and today's total.
- A dashboard checkbox that merges library + footprint + component search into
  one `library_management` report line, without changing what is recorded.
- `/api/setting` for the two presentation switches.
- Four more checks in the replay test, covering the active-document signal.

Changed
- Ladder order: dialog > active document > caption extension > Auto Save.
  A dialog still wins because it says what you are doing *to* the document.
- A dialog label now keeps the document name underneath it.
- Auto Save is recommended rather than required; it corroborates editing.
- Every INSERT names its columns (a positional one broke on the `parent_id`
  migration).
