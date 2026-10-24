# pcbtrack

**Automatic, offline work-hour tracking for PCB designers, built around Altium Designer.**

pcbtrack runs quietly in the background on Windows and records how long you
worked, **on which project, in which document, and at which design stage**:
schematic, symbol library, footprint library, PCB layout, DRC, BOM and more.
At the end of the day you check its guesses in a couple of minutes, add a
short note per project, and export a report for yourself or your client.

- **Altium first.** It reads the open document straight from Altium's window
  (`Power.SchDoc`, `ESC_Board.PcbDoc`, `ESC_FOOT.PcbLib`), so schematic, layout
  and library time are separated automatically. Other software (browser,
  datasheets, Excel, chat) is tracked too, as a secondary view.
- **Lightweight.** Pure Python standard library: no `pip install`, no admin
  rights, no browser extension, no Altium plugin. One background process
  checks the screen every 5 seconds.
- **Private.** Nothing leaves your PC. No account, no network calls, no
  screenshots, no keylogging. The dashboard is only reachable from your own
  machine (`127.0.0.1`).
- **Honest.** Every automatic label is marked as a guess until you confirm it,
  and reports say how much of the time you confirmed.

> Status: **v0.9.1**, in daily use by the author since October 2026. Windows
> only for live tracking. See [CHANGELOG.md](CHANGELOG.md).

---

## Install (5 minutes)

1. **Install Python 3.8 or newer** from [python.org](https://www.python.org/downloads/)
   and tick **"Add Python to PATH"** during setup.
2. **Get pcbtrack**: download this repository as a ZIP (green *Code* button ->
   *Download ZIP*) and extract it to a folder it can stay in, for example
   `D:\Tracker`. Or clone it:
   ```bash
   git clone https://github.com/simulahmed003/pcbtrack.git D:\Tracker
   ```
3. **Double-click `install.bat`.** It checks Python, starts tracking, and adds
   pcbtrack to your login so it starts with Windows.
4. **Double-click `dashboard.bat`** to open the dashboard in your browser.

Optional: turn on Altium Auto Save (*Preferences -> Data Management -> Backup*,
every 2 minutes). pcbtrack works without it, but autosaves are extra evidence
that you were editing rather than just looking.

Full guide, including portable (USB) mode and troubleshooting:
**[docs/07-install-windows.md](docs/07-install-windows.md)**

## Daily use in one minute

| When | What to do |
| --- | --- |
| While working | Nothing. Work in Altium as usual. |
| End of the day | Open `dashboard.bat`. In **Altium today**, check each document's **Work stage** and **Project** (amber = guess) and fix any that are wrong. |
| | Write a line in **Daily notes** for each project: what got done. |
| Off the PC (meeting, milling, soldering, study) | **Add time by hand**. |
| End of the week / for a client | **Report for a period**: pick dates and projects, download Markdown or CSV, or one report per project as a ZIP. |
| Taking a break from tracking | **Stop tracking** on the dashboard, or `stop.bat`. Start again with **Start tracking** or `track.bat`. |

The complete walkthrough of every panel is in the
**[User guide](docs/USER_GUIDE.md)**.

## What you get

- **Altium today**: every document you worked on, grouped by project: when,
  what was on screen (*Detected*: Schematic editor, PCB editor, PCB library,
  a DRC dialog...), the *Work stage*, number of saves, and time. Change the
  stage or project per row, or **split** a row across several projects.
- **Timeline** of the day, with an Altium-only lane coloured by stage.
- **Focus**: share of your work spent in Altium, longest unbroken stretch,
  daily target progress, this week's totals.
- **Daily notes**: one per project per day, editable, included in reports.
- **Reports** for any period, per project or all projects: Markdown, summary
  CSV (hours per project x stage and per document), every block as CSV, a ZIP
  with one report per project, and an AI-ready brief you can paste into any
  assistant.
- **Projects and clients** that you can create up front, rename, group
  (main board + test jig under one job), and delete in a protected
  **Danger zone** that backs up your data first.

## Command line

Everything the dashboard does is also available from a terminal in the
pcbtrack folder:

```bash
python -m pcbtrack doctor             # check the setup, say what is missing
python -m pcbtrack track              # start tracking (only one copy can run)
python -m pcbtrack stop --all         # stop tracking and close the dashboard
python -m pcbtrack serve              # open the dashboard
python -m pcbtrack report 2026-10-24  # write md / csv / json for a day
python -m pcbtrack log 45 "client call" --stage client_meeting --project "Buck converter"
python -m pcbtrack autostart off      # do not start with Windows (on to undo)
python -m pcbtrack portable           # keep data next to the program (USB drive)
python -m pcbtrack probe              # record what Altium exposes, for diagnosis
python -m pcbtrack selfcheck          # append accuracy numbers to perf.log
```

## Your data

Everything is stored in one SQLite file, `activity.db`, in
`%LOCALAPPDATA%\pcbtrack` (or in `data\` next to the program in portable mode),
together with `config.json`, logs and automatic backups. It contains
timestamps, program names, window titles, document names and your notes.
Titles matching the private patterns (banking, WhatsApp, Facebook, private
browsing...) are stored only as `(private)`.

To remove everything: run `uninstall.bat`, then delete that folder.

## How it works (short version)

Altium's title bar names the project but not the open document, so a normal
time tracker cannot tell schematic work from layout or library work. pcbtrack
reads the **active document tab from Altium's child windows** with plain
Win32 calls (`EnumChildWindows`), which also works while you are only viewing.
Dialog captions (Design Rule Checker, Engineering Change Order, Bill of
Materials...) refine the stage. Each 5-second sample is merged into intervals
in SQLite; the dashboard turns them into a day where work + idle + locked +
not-tracked always adds up to exactly 24 hours.

Details: [docs/03-architecture.md](docs/03-architecture.md) and
[docs/02-stage-detection.md](docs/02-stage-detection.md).

## For developers

- Project context and the decisions behind the design, for anyone (human or
  AI) picking this up: **[docs/CONTEXT.md](docs/CONTEXT.md)**
- Toolchain, layout, tests and conventions: [docs/04-toolchain.md](docs/04-toolchain.md)
- Why each version looks the way it does: [docs/10-version-analysis.md](docs/10-version-analysis.md)
- Open questions and next experiments: [docs/08-open-questions.md](docs/08-open-questions.md)

Run the tests (63 checks over a synthetic workday, no Windows needed):

```bash
python tests/replay_day.py
```

## Licence

MIT. See [LICENSE](LICENSE).
