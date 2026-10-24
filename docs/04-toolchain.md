# Toolchain and development

## Runtime

| | |
| --- | --- |
| Language | Python 3.8+ (live on 3.12 on the owner's PC) |
| Dependencies | **none** - standard library only, on purpose |
| OS for tracking | Windows 10 / 11 |
| OS for development and tests | any (the `Replay` backend removes the Windows need) |
| Storage | SQLite via `sqlite3` |
| UI | one static HTML file served by `http.server` |
| Packaging | a folder, or a zip. **No PyInstaller** |

**Why no PyInstaller.** Unsigned single-file builds are routinely quarantined
as false positives (Defender flagged one as `Trojan:Win32/Bearfoos.A!ml` in
Oct 2026) and SmartScreen warns on low-reputation binaries. A plain folder of
`.py` files plus `.bat` launchers avoids the whole problem and keeps the code
auditable, which matters more for a tool that watches your screen titles.

## Layout

```
pcbtrack/            the package
  config.py          defaults + user config merge + data dir
  store.py           schema, interval writer, projects, labels, audit
  sysmon.py          Win32 probe (ctypes) and the Replay test backend
  altium.py          reads Altium's active document from its child windows
  signals.py         Altium Recovery / History / save watching
  rules_default.py   dialog dictionary, app rules, title patterns
  classify.py        the signal ladder, confidences, backfill
  sessionize.py      dedup, 24h accounting, thinking grace, rollups
  tracker.py         the loop and the clock rules
  report.py          summary, review queue, markdown/csv/json
  server.py          dashboard + JSON API, 127.0.0.1 only
  probe.py           one-off Altium window discovery
  web/dashboard.html the whole UI (one file, no framework, no CDN)
  cli.py             `python -m pcbtrack <command>`
tests/replay_day.py  full pipeline over a synthetic workday
docs/                this folder
*.bat                Windows launchers
```

## Development loop

```
python tests/replay_day.py        # 63 checks, must print "0 check(s) failed"
python -m pcbtrack doctor         # setup check (reports Altium gaps)
PCBTRACK_DATA=/tmp/x python -m pcbtrack report
```

**Never test UI changes against the owner's live data.** Copy the database
into a scratch folder and point a second dashboard at it:

```
mkdir C:\tmp\pt
python -c "import sqlite3,os; s=sqlite3.connect(os.path.expandvars(r'%LOCALAPPDATA%\pcbtrack\activity.db')); d=sqlite3.connect(r'C:\tmp\pt\activity.db'); s.backup(d)"
echo {"port": 18902} > C:\tmp\pt\config.json
set PCBTRACK_DATA=C:\tmp\pt
python -m pcbtrack serve
```

Restart the live tracker after code changes with `python -m pcbtrack stop
--all`, then `track.bat` and `dashboard.bat`.

`tests/replay_day.py` drives the real tracker, classifier and sessionizer
through a scripted day, with synthetic Auto Save evidence. Anything touching
the clock rules, the classifier ladder or the store schema must keep it green.

To test a scenario by hand, add a line to its `script` list:
`(duration_seconds, process, window_title, window_class, idle_seconds, locked)`.

## Conventions

- Standard library only. A third-party import in the tracking path is a bug.
- Every stage label carries a confidence and a human-readable reason string;
  reasons appear in the dashboard, so write them for a person.
- New dialog rules are marked `OBSERVED` only once seen in real data,
  otherwise `UNVERIFIED`.
- `obs` and `evidence` are append only. If a change needs to rewrite them, the
  design is wrong.
- Automation must never overwrite a `confirmed`, `manual` or `corrected` label.

## Weekly review procedure

1. `python -m pcbtrack selfcheck` - appends a JSON line to `perf.log`.
2. Open the dashboard for two or three real days; compare against memory.
3. Note every wrong label and what was actually on screen.
4. Tighten `rules_default.py`; promote `UNVERIFIED` to `OBSERVED` as confirmed.
5. Re-run the replay test; bump `CHANGELOG.md`.

Tracked metrics: `pct_unknown_stage`, `pct_unassigned_project`,
`pct_confirmed`, `db_mb`, `intervals`.
