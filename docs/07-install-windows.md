# Install on Windows

## Requirements

- Windows 10 or 11
- Python 3.8 or newer (no extra packages)
- Altium Designer 18 or newer for document and stage detection (tested on 26.7.1)

## 1. Python

Install Python from [python.org](https://www.python.org/downloads/).
**Tick "Add Python to PATH"** in the installer. Check it in a new terminal:

```bash
python --version
```

## 2. Get pcbtrack

Download the repository as a ZIP from GitHub (*Code -> Download ZIP*) and
extract it, or clone it:

```bash
git clone https://github.com/simulahmed003/pcbtrack.git D:\Tracker
```

Put it somewhere it can stay. The login entry remembers this folder; if you
move it later, run `install.bat` again.

## 3. Install

Double-click **`install.bat`**. It:

1. checks that Python is on PATH,
2. runs `python -m pcbtrack doctor` and prints anything missing,
3. adds `pcbtrack.bat` to your Startup folder so tracking starts at login,
4. starts tracking now.

Then double-click **`dashboard.bat`**. Within a few seconds the top strip
should show a green dot and your current program.

## 4. Optional: Altium Auto Save

pcbtrack reads the open document from Altium's window, so Auto Save is not
required. It is still useful: autosave copies show that a document was
*edited*, not just viewed, and protect your work.

*Preferences -> Data Management -> Backup*: **Auto save every 2 minutes**,
**keep 10 versions**.

## 5. Optional: count saves per document

In the dashboard's **Settings**, list your Altium project folders, one per
line (e.g. `D:\Altium\ESC_Board_5Vbuck`). The Altium table then shows how many
times each document was saved.

## 6. Check it works

```bash
python -m pcbtrack doctor
python -m pcbtrack status
```

Open Altium, switch between a schematic, the PCB and a library for a minute,
then look at **Altium today** on the dashboard: each document should be
listed with the right *Detected* editor.

## Files and launchers

| File | What it does |
| --- | --- |
| `install.bat` | check setup, start tracking, start at every login |
| `track.bat` | start tracking now (background, no window) |
| `dashboard.bat` | open the dashboard |
| `stop.bat` | stop tracking and close the dashboard |
| `report.bat` | write today's report files |
| `doctor.bat` | check the setup |
| `probe.bat` | record what Altium shows, for diagnosing detection problems |
| `make_portable.bat` | switch to portable mode (data next to the program) |
| `uninstall.bat` | remove the login entry and stop tracking; keeps your data |

## Where the data lives

`%LOCALAPPDATA%\pcbtrack` (press Win+R and paste that to open it):

| File | Contents |
| --- | --- |
| `activity.db` | all tracking data, labels, projects and notes (SQLite) |
| `config.json` | your settings (only what you changed) |
| `backups\` | automatic backups made before any Danger zone action |
| `reports\` | report files written by `pcbtrack report` |
| `tracker.log`, `dashboard.log` | errors and restarts, for troubleshooting |
| `perf.log` | accuracy numbers from `pcbtrack selfcheck` |

## Portable mode (USB drive, second PC)

Run **`make_portable.bat`**. It stops tracking, copies your existing data
into a `data` folder next to the program, creates `portable.flag`, and starts
tracking again. From then on everything stays inside the pcbtrack folder.
Delete `portable.flag` to go back. Do not run two PCs on the same data at the
same time.

## Uninstall

1. Run **`uninstall.bat`**: removes the login entry and stops tracking.
2. Delete the pcbtrack folder.
3. To erase your data as well, delete `%LOCALAPPDATA%\pcbtrack`.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `python` is not recognised | Python is not on PATH. Reinstall it with "Add Python to PATH" ticked. |
| "already tracking" | It is running. Only one copy may run, so nothing is counted twice. |
| Altium time shows but no documents | Altium may be running as administrator while pcbtrack is not. Run both the same way. Then run `probe.bat` and share the JSON it writes. |
| Dashboard shows *stopped unexpectedly* | The tracker exited on an error. The dashboard restarts it; details are in `tracker.log`. |
| Port 8765 in use by another program | Add `{"port": 8790}` to `config.json` in the data folder. |
| Windows Defender warning | pcbtrack is plain, readable `.py` and `.bat` files; nothing is compiled or packed. |
