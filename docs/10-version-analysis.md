# Version analysis and feature merge (2026-10-24)

Written for v0.6.0. Three trackers have existed so far:

| Version | What it was | What went wrong |
|---|---|---|
| ActivityWatch package (another assistant) | ActivityWatch + Edge extension + report script | heavy, manual extension install, no project or Altium awareness |
| **PCBWorkTracker2** (`pwt.py`, used 22-23 Oct) | one stdlib file: window titles -> categories, employer pay, dashboard | 2-4 copies ran at once (numbers inflated 2-4x); Altium caption shows only the project, so 70% of time had no stage |
| **pcbtrack 0.1-0.5** (this repo) | interval store, signal ladder, review, Altium child-window reading | see CHANGELOG; 0.5 made the dashboard Altium-first |

The owner's verdict on 0.5: keep it, put Altium detail first, make the stage
column honest (what was detected vs what the work stage is), give other
software the same kind of detail with lower priority, and bring back the
useful parts of PCBWorkTracker2.

## 1. Detected vs work stage (the main change)

What the tracker can **observe** in Altium and what the **work stage** is are
different things, and one column was doing both jobs.

| Column | Meaning | Source | Trust |
|---|---|---|---|
| **Detected** | the editor/document type on screen: Schematic editor, PCB editor, Schematic library, PCB library, or the dialog that was open (DRC, ECO, Polygon Pour...) | Altium child windows (`TdxTabSheet` caption, visible `T*View_GraphicalForm`), dialog captions | a fact; never edited |
| **Work stage** | what you were doing: schematic, placement, routing, silkscreen, library_footprint, component_search... | starts as the tracker's guess (from Detected), you set it per document row | guess until you save it |

A PCB editor open for 40 minutes is a **fact**; whether that was placement,
routing or silkscreen is **your call**. The guess is shown in amber, a saved
stage in normal text. Saving a row relabels every block of that document
with that guessed stage on that day, so one dropdown fixes 40 minutes.

Feasibility: high. The data already exists (`obs` = detected, `labels` =
stage); only the presentation and a per-row relabel were missing.

What still cannot be detected automatically (needs your choice, or a later
experiment): placement vs routing vs silkscreen inside the PCB editor. Next
experiment: read the PCB editor's status bar / active layer child window with
`pcbtrack probe` while routing vs placing. Recorded in `08-open-questions.md`.

## 2. Other software, same shape, lower priority

The same table for non-CAD software: application -> page/document
(cleaned window title: `ESE 4025 Study Pack`, `BTN7960 datasheet.pdf`) ->
Detected (the app rule that matched, e.g. "datasheet / PDF", "part sourcing
site") -> Work stage (editable). Collapsed by default under the Altium card.
Private titles stay `(private)`.

## 3. PCBWorkTracker2 features: keep, bring back, or leave out

| Feature in pwt.py | Decision | Why |
|---|---|---|
| Today **and this week** on the dashboard | **Bring back** as KPI tiles (week worked, week in Altium) | one glance; the range report already covers any period |
| **Focus %** and **longest focus block** | **Bring back**, Altium-based | a useful signal of deep design work vs fragmented switching |
| **Daily target** progress | **Bring back** (`daily_target_hours`, editable in the dashboard) | was in config but unused in pcbtrack |
| **Top files and pages** | **Bring back** as the "Other software" table (section 2) | |
| **File saves** per project (`watch_folders`) | **Bring back** as a "Saves" column in the Altium table; folders set from the dashboard (`project_dirs`) | saves are proof of progress, not just time with a window open |
| **AI-ready brief** | **Bring back** in "Report for a period": copy a prompt + report to paste into any assistant | |
| **Portable mode** (`make_portable.bat`) | **Bring back** the .bat; the `portable.flag` mechanism already exists in `config.data_dir` | |
| Offline work log | already in pcbtrack ("Add time by hand", `pcbtrack log`) | |
| Private title patterns | already in pcbtrack | |
| **Employer pay / hourly rates** | **Left out for now** | on 2026-10-24 the owner said billing is not needed, only time. Can return as an optional per-client rate on the period report |
| Fixed category list (pcb/sch/lib/ds/web...) | replaced by pcbtrack's work stages + review | categories could not be corrected; stages can |

## 4. Weight

Everything above is read-side or UI: no new background work in the tracker
except the existing folder scan, which only runs when project folders are set
(one `os.scandir` pass per minute, depth 2, capped at 4000 entries). The
tracker stays at one Win32 call set per 5 s tick.

## 5. Risks

- Relabelling a document row changes many blocks at once. It only touches
  blocks of that document that still carry the guessed stage, never
  hand-entered blocks, and every change goes to the `audit` table.
- Cleaned browser titles depend on Edge/Chrome title formats; unknown formats
  fall back to the raw title.
- Save counts need the project folders set; without them the column is empty
  rather than wrong.
