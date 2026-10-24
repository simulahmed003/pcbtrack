# Read this first

Context for anyone (including a future AI session) picking this project up.
Updated 2026-10-24.

## What this is

`pcbtrack` is a local, offline work-hour tracker for a freelance PCB/EDA
designer. It answers: **how long did I work, on which project, in which
software, on which document, at which stage of the design.** It does not do
billing maths.

Owner: Simul Ahmed. Primary tool: Altium Designer 26.7 on Windows.
Secondary: KiCad, EasyEDA Pro. Repo lives at `D:\Tracker`.

## The one fact that shapes the whole design

**Settled 24 Oct 2026 by probe.** See "The signal that actually works" below:
the active document IS readable from Altium's child windows. The Auto Save
route described next is now the *corroborating* signal, not the primary one.

**Altium's window title cannot tell you which document is open.** The
"Show full path in title bar" option was *removed in Altium Designer 18.1*.
Since then the caption is `<Project>.PrjPcb - Altium Designer <ver>`, so
schematic editing, PCB layout, symbol-library and footprint-library work all
look identical from outside.

In the 22-23 Oct 2026 baseline, **8.3 of 11.8 working hours (70%)** sat in
that one unsplittable bucket.

The way out is **Altium's own Auto Save**: it writes a recovery copy of every
*modified* open document as `<doc>.~(n).<ext>` into
`%APPDATA%\Altium\Altium Designer <GUID>\Recovery`. The **file extension is
the answer**:

| Extension | Work stage |
| --- | --- |
| `.SchDoc` | schematic |
| `.PcbDoc` | PCB layout / routing |
| `.SchLib` | library - symbol |
| `.PcbLib` | library - footprint |

`kicad-wakatime` solves the identical problem the same way for KiCad.

## The signal that actually works (probe result, 24 Oct 2026)

Altium Designer 26.7.1, process `X2.EXE`, main window class `TDocumentForm`.
Two child windows give the answer with plain Win32 - no UI Automation, no COM,
no plugin, no Auto Save dependency:

| Child class | What its caption holds |
| --- | --- |
| `TdxTabSheet`, `TViewComponent` | the active document tab: `[1] ESC_PCB.SchDoc`, `ESC_Board.PcbDoc`, or `Home Page` when none |
| `TSCHView_GraphicalForm`, `TPCBView_GraphicalForm`, `TSCHView_LibraryGraphicalForm` | one per open document; the **visible** one is the active editor |

Measured in the probe: the tab caption changed from `Home Page` to
`[1] ESC_PCB.SchDoc` to `ESC_Board.PcbDoc` exactly as the owner switched
documents. `pcbtrack/altium.py` reads it; `pick_active()` is unit-tested
against the recorded probe samples.

Do **not** read `TGUIDocBarButton` - it lists *other* open documents, not the
active one. Skip the hidden zero-size `TApplication` window too.

This beats Auto Save because it sees **viewing**, not only editing, and is
instant rather than lagging the autosave interval. Auto Save is still worth
having on: it proves editing happened and corroborates the document
(see `07-install-windows.md`), but stage tracking no longer depends on it.

## Design principles, in priority order

1. **Extremely lightweight.** Standard library only. No pip install, no
   service, no admin rights, no browser extension, no Altium plugin. This is
   the owner's stated top priority.
2. **Honest before clever.** Every stage label carries a confidence and a
   reason. Reports always separate *confirmed* from *auto-guessed*. Time that
   cannot be attributed is shown as unknown, never silently assigned.
3. **The machine proposes, the human decides.** Nothing requires setup before
   tracking starts; projects are auto-proposed from what is seen and every
   name is editable afterwards. A human label is never overwritten by
   automation.
4. **Observations are immutable, labels are not.** `obs`/`evidence` are append
   only. All interpretation lives in `labels`, which the user can freely edit.
   Renaming a project changes a name only, because history is keyed to a
   stable id.
5. **Account for all 24 hours.** `work + idle + locked + off` must equal wall
   clock exactly. Tested.

## Where things are

| Path | What |
| --- | --- |
| `pcbtrack/tracker.py` | the loop; enforces the clock rules |
| `pcbtrack/signals.py` | Altium Recovery / History / save watching |
| `pcbtrack/classify.py` | the signal ladder, confidences, backfill |
| `pcbtrack/rules_default.py` | Altium dialog dictionary (OBSERVED vs UNVERIFIED) |
| `pcbtrack/sessionize.py` | dedup, 24h accounting, thinking grace |
| `pcbtrack/store.py` | SQLite, two-layer schema |
| `pcbtrack/probe.py` | one-off Altium discovery probe |
| `tests/replay_day.py` | full pipeline against a synthetic day |
| `docs/02-stage-detection.md` | why each signal, with sources |
| `docs/08-open-questions.md` | what is still unverified |

## Hard-won bugs, do not reintroduce

1. **Two trackers ran at once** in the previous version and inflated every
   number 2-4x. There is now a loopback-port lock, and `sessionize.intervals`
   discards overlap so a duplicate can never add time.
2. **Idle backdating ate real work.** Backdating to the last input must be
   cross-checked against the previous tick's estimate; `GetLastInputInfo`'s
   tick "is not guaranteed to be incremental" (Microsoft).
3. **A constant caption collapsed hours into one row**, so a whole Altium
   session could carry only one stage. The inferred label is now part of the
   interval merge key, plus a `max_interval_seconds` cap.
4. **A dialog in the foreground outranks file evidence.** If the Design Rule
   Checker is open, that is DRC, whatever was autosaved five minutes ago.
5. **Live, evidence arrives after the work.** `classify.backfill` fills in the
   start of a session once the first Auto Save lands. Much less critical now
   that the active document is read directly, but still useful.
6. **A positional `INSERT` broke** when `projects.parent_id` was added by
   migration. Every insert names its columns now; keep it that way.
7. **`pkill -f "pcbtrack serve"` kills the shell that runs it**, because the
   pattern matches its own command line. Use a stored PID.
8. **A row stores sample times, not covered time** (found live, 0.3.0). A
   block seen on one tick has `t0 == t1` and counted 0 s, so short looks at a
   schematic vanished from "By document", and every block change leaked one
   tick to "off". `sessionize.intervals` stretches each row to the next row's
   start when the gap is <= ~2 ticks. Do the fix at read time, so old data
   is repaired too.
9. **Sticky carry-over crossed applications** (found live, 0.3.0): chatting in
   Claude and browsing Edge after Altium got "routing". Stage carry-over now
   only applies within the same process.
10. **The PcbLib editor reuses the PCB editor's form class**, so the class
    said PCB while the tab said `.PcbLib`. Within one family (sch/pcb) the
    tab's extension wins.
12. **A document caption is not a project** (found live, 0.5.0). With a
    PcbDoc in front, Altium's caption is `ESC_Board.PcbDoc - Altium
    Designer`, and treating `ESC_Board` as a project split one Altium project
    in two. Altium documents take their project from the `.PrjPcb` they were
    seen with (`doc_projects` table), else the project open in that Altium
    session.
13. **Several dashboards could share port 8765 on Windows** because
    `ThreadingHTTPServer` sets `SO_REUSEADDR`; an old copy kept answering with
    old code. The server now binds with `SO_EXCLUSIVEADDRUSE` and a second
    launch just opens the browser.
14. **Under pythonw, `sys.stderr` is None** (found live, 0.9.1). The tick
    error handler called `sys.stderr.write`, which raised inside the
    `except`, so the first transient error (e.g. "database is locked" while
    the dashboard wrote) ended the tracker silently: 2 h 20 min lost on
    2026-10-24. All output now goes through `tracker._log` (never raises);
    background runs log to `tracker.log` / `dashboard.log` in the data
    folder; the dashboard's watchdog restarts a tracker that stopped without
    a stop request (`meta.started` vs `meta.stop_request`).
11. **Crash recovery must not trim hand entries.** `close_open_intervals`
    skips `collector='manual'` rows, which may legitimately end after the last
    heartbeat.

## Working agreement with the owner

Weekly review. Each week: run `pcbtrack selfcheck`, read `perf.log`, compare
what the dashboard claims against what the owner remembers, then tighten rules. The
acceptance targets are in `01-requirements.md`.
