# Architecture and data model

One process, one SQLite file, one local web page. Standard library only.

```
                    +-- sysmon.py ---- foreground window, idle, lock (ctypes Win32)
   collectors ------|
                    +-- signals.py --- Altium Recovery / History / file saves
                                 |
                                 v
                        classify.py  -- signal ladder -> (project, stage, confidence, reason)
                                 |
                                 v
                        tracker.py   -- clock rules R1-R12, heartbeat, recovery
                                 |
                                 v
     store.py  [ obs | evidence ]  immutable      [ labels | projects | notes | rules | audit ]  editable
                                 |
                  +--------------+--------------+
                  v                             v
          sessionize.py                     server.py
      dedup, 24h accounting,            dashboard + JSON API (127.0.0.1)
      thinking grace                        |
                  |                         v
                  +----> report.py ---> md / csv / json
```

## Tables

| Table | Mutable | Purpose |
| --- | --- | --- |
| `obs` | append only | one row per contiguous observation: `t0, t1, state, app, title, wclass, collector` |
| `evidence` | append only | file signals: `t, kind, doc, doctype, path` |
| `labels` | **editable** | per-`obs` interpretation: `project_id, stage, doc, confidence, source, reason` |
| `projects` | editable | `id` (stable), `name`, `client_id`, `status` |
| `clients` | editable | `id` (stable), `name` |
| `aliases` | editable | match patterns mapping observed text to a project |
| `notes` | editable | the daily free-text "what I actually did" |
| `rules` | editable | learned corrections, applied forward only |
| `audit` | append only | before/after of every manual change |
| `meta` | - | heartbeat, schema version, scan cursor |

**Why two layers.** Observations are evidence and must never be rewritten;
interpretation is opinion and must be freely correctable. This is what makes
daily review safe: no correction can corrupt the record of what was seen.

**Why stable ids.** `projects.id` never changes, so renaming a project or
reassigning its client relabels all history with no migration.

## Interval storage, not samples

One row per contiguous observation rather than one per tick. A 5-second tick
would be 17,280 rows a day; the synthetic workday produces 24 rows for 2,088
ticks (about 35 bytes per tick of database growth). SQLite runs
`journal_mode=WAL`, `synchronous=NORMAL`.

The inferred label is part of the merge key, because an Altium session keeps
one caption for hours - without it the whole stretch would collapse into a
single row and could carry only one stage. `max_interval_seconds` (default
600) caps a row so the review queue stays granular.

## Overlap is discarded, not summed

`sessionize.intervals` walks rows in time order and clips each to the running
cursor, so two collectors writing the same instant cannot add time. The
previous tracker had 2-4 concurrent writers and inflated totals up to 4x; this
makes that class of bug arithmetically impossible.

## Performance budget

| Resource | Budget | Why it holds |
| --- | --- | --- |
| CPU | < 1% average | five cheap Win32 calls per 5 s; no hooks, no UIA in v0.1 |
| Memory | < 40 MB | CPython plus sqlite3; no third-party imports |
| Disk | < 20 MB/year | interval rows, not samples |
| Filesystem scans | one `os.scandir` pass per 60 s | depth capped at 2, entry count capped at 4,000 |
| Startup | none | no service, no admin rights, no driver |
| Network | zero | nothing to budget |

Deliberately excluded from v0.1 to protect that budget: UI Automation polling,
a message-pump thread (so no tray icon, global hotkey or Windows power
events), input hooks, and any CAD plugin.

## Known limitations in 0.1.0

- Live tracking is Windows only; the pipeline is testable anywhere via `Replay`.
- Lock detection uses `OpenInputDesktop`. Sleep and shutdown are inferred from
  heartbeat gaps, not from `WM_POWERBROADCAST`.
- Browser attribution uses the active tab's title; no URL, by design.
- Viewing without editing writes no Auto Save, so it needs review or a note.
