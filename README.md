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
symbol-library and footprint-library work are indistinguishable from outside
the application. In a two-day baseline, 70% of working time landed in one
unsplittable bucket.

pcbtrack reads **Altium's own Auto Save recovery files** instead, whose
extension (`.SchDoc` / `.PcbDoc` / `.SchLib` / `.PcbLib`) identifies the work.
See [docs/02-stage-detection.md](docs/02-stage-detection.md).

## Install (Windows)

1. Install Python 3.8+ from python.org, ticking **Add Python to PATH**.
2. Download or clone this folder.
3. **Turn Altium Auto Save on** - without it, stages cannot be separated:
   *Preferences -> Data Management -> Backup*: Auto Save **every 2 minutes**,
   versions to keep **10**.
4. Double-click `install.bat`. It checks the setup and starts tracking at login.
5. Double-click `dashboard.bat` to see your day.

Full walkthrough: [docs/07-install-windows.md](docs/07-install-windows.md).

## Use

```
python -m pcbtrack doctor      check the setup, say what is missing
python -m pcbtrack track       start tracking (one instance only)
python -m pcbtrack serve       dashboard at http://127.0.0.1:8765
python -m pcbtrack report      write md / csv / json for today
python -m pcbtrack note "finished power stage, 3 footprints done"
python -m pcbtrack log 45 "client call" --stage client_meeting
python -m pcbtrack probe       inspect what Altium exposes on your machine
python -m pcbtrack selfcheck   append a line to perf.log for weekly review
```

The dashboard shows the full 24 hours, the breakdown by project / stage /
software / document, a review queue of the blocks it is unsure about, and a
box for a short note on what you actually got done.

## Status

v0.1.0, early. The pipeline is tested against a synthetic workday
(`python tests/replay_day.py`, 20 checks). The Altium dialog dictionary is
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
