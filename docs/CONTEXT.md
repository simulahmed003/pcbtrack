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

`kicad-wakatime` solves the identical problem the same way for KiCad. This is
why **Auto Save must be on** or the tracker is blind (see
`07-install-windows.md`).

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
   start of a session once the first Auto Save lands.

## Working agreement with the owner

Weekly review. Each week: run `pcbtrack selfcheck`, read `perf.log`, compare
what the dashboard claims against what he remembers, then tighten rules. The
acceptance targets are in `01-requirements.md`.
