# pcbtrack

Local, offline work-hour tracking for PCB and electronics design work.
It records **how long you worked, on which project, in which software, on
which document, and at which stage of the design** - then lets you correct
its guesses in a couple of minutes a day.

Built for Altium Designer on Windows first; KiCad and EasyEDA next.

- **Standard library only.** No `pip install`, no service, no admin rights,
  no browser extension, no CAD plugin.
- **Nothing leaves your machine.** No network calls, no account, no telemetry.
  The dashboard binds `127.0.0.1` only.
- **No screenshots, no keylogging.** Window titles, process names and the
  timing of file saves. Nothing else.
- **Honest by design.** Every label carries a confidence; reports separate
  what you confirmed from what the tracker guessed.

## Why it exists

Altium's window title only ever shows the *project*, never the open document
(the option was removed in Altium Designer 18.1). So schematic, PCB layout,
symbol-library and footprint-library work look identical from outside the
application. In a two-day baseline with a title-only tracker, 70% of working
time landed in one unsplittable bucket.

pcbtrack reads the **active document out of Altium's child windows** - the
`TdxTabSheet` caption holds `[1] ESC_PCB.SchDoc`, `ESC_Board.PcbDoc` and so on
- with plain Win32 calls. No UI Automation, no COM, no Altium plugin. Altium's
Auto Save recovery files corroborate it and prove that editing (not just
viewing) happened. Confirmed by probe against Altium Designer 26.7.1:
[docs/09-probe-2026-10-24.md](docs/09-probe-2026-10-24.md),
[docs/02-stage-detection.md](docs/02-stage-detection.md).

## Install (Windows)

1. Install Python 3.8+ from python.org, ticking **Add Python to PATH**.
2. Download or clone this folder.
3. Recommended: turn Altium Auto Save on - *Preferences -> Data Management ->
   Backup*, every **2 minutes**, keep **10** versions. Stage detection works
   without it, but Auto Save distinguishes editing from viewing and is a
   genuine crash safety net.
4. Double-click `install.bat`. It checks the setup and starts tracking at login.
5. Double-click `dashboard.bat` to see your day.
6. To switch it off: **Stop tracking** on the dashboard, or `stop.bat` (stops
   tracking and closes the dashboard). `track.bat` starts it again; untick
   **start at login** if you only want it when you ask.

Full walkthrough: [docs/07-install-windows.md](docs/07-install-windows.md).

## Use

```
python -m pcbtrack doctor      check the setup, say what is missing
python -m pcbtrack track       start tracking (one instance only)
python -m pcbtrack stop        stop tracking (--all also closes the dashboard)
python -m pcbtrack autostart off   do not start at login (on to undo)
python -m pcbtrack serve       dashboard at http://127.0.0.1:8765
python -m pcbtrack report      write md / csv / json for today
python -m pcbtrack note "finished power stage, 3 footprints done"
python -m pcbtrack log 45 "client call" --stage client_meeting
python -m pcbtrack probe       inspect what Altium exposes on your machine
python -m pcbtrack selfcheck   append a line to perf.log for weekly review
```

The dashboard shows a **live strip** of what you are doing right now
(refreshed every 5 s from a 291-byte endpoint), the full 24 hours, the
breakdown by project / stage / software / document, a review queue of the
blocks it is unsure about, and a box for a short note on what you actually got
done. Every work block gets a project: by file or title, by a shared word in
the project name (`Buck converter` <- `Buck_Regulator.PcbDoc`), or, when
nothing names one, a guess from the project you last worked on, shown in
amber until you confirm or change it.

In the Altium table every document row shows **when** it happened, what was
**detected** on screen (a fact), and a **work stage** and **project** you can
change; a row can be **split** across projects and the split undone.
Deleting projects, clients, stages or whole days lives in Settings ->
Danger zone, behind typed confirmations and an automatic backup. One client job can hold several Altium projects, grouped with the
"Groups under" dropdown, and library + footprint + component-search time can
be merged into one report line with a checkbox.

## Status

v0.2.0, early. The pipeline is tested against a synthetic workday
(`python tests/replay_day.py`, 24 checks). The Altium dialog dictionary is
partly verified: entries are marked `OBSERVED` or `UNVERIFIED` in
`pcbtrack/rules_default.py`. Open questions are in
[docs/08-open-questions.md](docs/08-open-questions.md).

## Privacy

Stored locally in `%LOCALAPPDATA%\pcbtrack` (or `./data` in portable mode):
timestamps, process names, window titles, file names and your own notes.
Titles matching `private_title_patterns` are stored as `(private)`. Delete
everything by deleting that folder. Nothing is uploaded, ever.

## Licence

MIT - see [LICENSE](LICENSE).
