# Install on Windows

## 1. Python

Install Python 3.8 or newer from [python.org](https://www.python.org/downloads/).
**Tick "Add Python to PATH"** in the installer. Check it worked:

```
python --version
```

## 2. Turn on Altium Auto Save - this step is not optional

Without it, pcbtrack can tell you *that* you were in Altium but not whether
you were drawing a schematic, routing the board, or building a footprint.
Altium's window title does not carry the document name (removed in AD 18.1),
so the Auto Save recovery files are the only cheap signal.

In Altium Designer:

1. **Preferences** (the gear, top right) -> **Data Management** -> **Backup**
2. **Auto save every: 2 minutes**  (1-5 is fine; shorter means finer tracking)
3. **Number of versions to keep: 10**
4. Leave the path at its default, or note it if you change it
5. Optionally tick **Add autosaved documents to history**
6. Apply, OK

Altium warns that each Auto Save briefly pauses editing while it writes. At a
2-minute interval this is barely noticeable, and it is also a genuine crash
safety net.

## 3. Install pcbtrack

Put the folder where it will stay - `D:\Tracker` - then double-click
**`install.bat`**. It will:

- check Python is on PATH
- run `doctor` and tell you if the Recovery folder cannot be found
- add a startup entry so tracking begins when you log in
- start tracking now

For a portable copy (USB stick, second PC) create an empty file named
`portable.flag` next to `install.bat`; the database then lives in `.\data`
beside the program instead of `%LOCALAPPDATA%\pcbtrack`.

## 4. Check it is working

```
python -m pcbtrack doctor
```

You want to see a Recovery folder found, and recovery files listed once you
have had Altium open with unsaved changes for a few minutes.

Then work normally for an hour and open **`dashboard.bat`**.

## 5. Run the discovery probe once

```
python -m pcbtrack probe
```

It watches for two minutes. While it runs, switch Altium between a schematic,
the PCB, a schematic library and a PCB library, holding each about 20 seconds.
It saves a JSON file and prints what it saw. Send that back and the rules get
tuned for your exact install - this is how the remaining unknowns in
`08-open-questions.md` get settled.

## Daily use

| Action | How |
| --- | --- |
| See the day | `dashboard.bat` |
| Fix wrong guesses | the Review table, biggest blocks first |
| Say what you got done | the note box, or `python -m pcbtrack note "..."` |
| Log off-PC work | `python -m pcbtrack log 45 "client call" --stage client_meeting` |
| Export | the Export button, or `python -m pcbtrack report` |

## Uninstall

`uninstall.bat` removes the startup entry. Your data stays in
`%LOCALAPPDATA%\pcbtrack` - delete that folder to erase everything.

## If something is wrong

| Symptom | Cause and fix |
| --- | --- |
| "already tracking" | It is running. One instance is deliberate: two would double count. |
| Recovery folder NOT FOUND | Auto Save is off, or on a non-default path. Do step 2, then `doctor`. |
| All Altium time shows one stage | Auto Save interval too long, or you were viewing without editing. Shorten the interval; confirm blocks in Review. |
| Stage is `unknown` | No signal existed. Confirm it in Review; the correction can become a rule. |
| Defender warns | Nothing is compiled or packed - these are plain `.py` text files you can read. |
