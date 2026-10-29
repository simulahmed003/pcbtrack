# pcbtrack user guide

This guide walks through the dashboard from top to bottom and explains a
normal working day. Installation is in [07-install-windows.md](07-install-windows.md).

Open the dashboard with **`dashboard.bat`** (or `python -m pcbtrack serve`).
It opens `http://127.0.0.1:8765` in your browser. Only your own PC can reach
it. Opening `dashboard.bat` a second time just opens the browser again.

---

## 1. Key ideas

| Term | Meaning |
| --- | --- |
| **Block** | A stretch of time with one program, window and document. pcbtrack samples every 5 seconds and merges samples into blocks. |
| **Detected** | What was observably on screen: *Schematic editor*, *PCB editor*, *Schematic library*, *PCB library*, a dialog such as *Dialog: Design Rule Checker*, or a program name. This is a fact and cannot be edited. |
| **Work stage** | What you were doing: `schematic`, `library_footprint`, `placement`, `routing`, `drc`, `component_search`, `client_meeting`... pcbtrack guesses it from *Detected*; you confirm or change it. |
| **Guess (amber)** | Anything pcbtrack decided on its own. Amber rows and the *guess* tag stay until you save a choice. If you never touch them, they stay as guessed. |
| **Project** | Taken from the Altium `.PrjPcb` name, from a word shared with one of your project names (`Buck converter` <- `Buck_Regulator.PcbDoc`), or guessed from the project you last worked on. |
| **States** | Every second of the day is one of: **work** (input within 3 minutes), **idle** (no keyboard or mouse for 3+ minutes), **locked**, or **not tracked** (PC off or tracker stopped). They always add up to 24 hours. Short pauses under 5 minutes inside work on the same project count as work (thinking time). |

---

## 2. The top strip

Shows what is happening **right now**: current stage, document, project, time
worked today, time in Altium today, and the last Altium document you used.
The grey text explains why the tracker chose that label.

Buttons on the right:

- **Stop tracking / Start tracking**: pause and resume. While stopped, the
  time shows as *not tracked*.
- **start at login**: tick to start tracking with Windows; untick to start it
  only when you want.
- **Close dashboard**: closes this page's server. Tracking keeps running.

If the strip says **stopped unexpectedly** in red, the tracker exited without
being asked. While the dashboard is open it restarts the tracker
automatically within about 30 seconds. Details go to `tracker.log` in your
data folder.

Use **<- / -> / Today** and the date box at the top to look at other days.

## 3. Summary numbers

- **Today**: worked, time in Altium, idle, not tracked.
- **Accuracy**: share of work time you confirmed, time with an unknown stage,
  time whose project was guessed.
- **This week**: totals since Monday.
- **Altium focus**: share of work spent in Altium, and the longest Altium
  stretch where no break was longer than 2 minutes.
- **Daily target**: progress bar towards the hours set in Settings.

Hover over a number for a short explanation.

## 4. Altium today (the main table)

One row per document, stage and project, grouped by project. Click a project
heading to fold its rows away; click the card title to fold the whole card.

| Column | What it is | Can you change it? |
| --- | --- | --- |
| When | first to last time of that row | no |
| Document | the Altium document, e.g. `ESC_Board.PcbDoc` | no |
| Project | which project the time belongs to | **yes**: pick another project, or *+ new project...* |
| Detected | editor or dialog on screen | no |
| Work stage | the stage; amber means guess | **yes**: pick a stage, or *+ new stage...* |
| Saves | how often the file was saved that day (needs project folders in Settings) | no |
| Time | total time of the row | no |

Changing a project or stage applies to **every block in that row** at once,
so one choice can fix 40 minutes of layout work.

### Splitting a row between projects

If one document served several projects, for example a shared footprint
library, press **split...** under the document name:

1. Each line is a project and a number of minutes.
2. The **last line always gets the remaining minutes**, so the total never
   changes. Use *+ add project* for more lines.
3. The earliest minutes go to the first line.
4. Press **Split**. The row becomes one row per project.

**undo split** appears on split rows and puts the whole row back the way it
was tracked. The original tracking is never changed by a split, so undo is
always possible.

### Merging rows into one

When several rows were really one piece of work (a footprint plus the
datasheet you read for it plus a schematic fix), tick the box at the left of
each row and press **Merge N selected rows** above the table (Altium and
Other software both have one). Choose one project, one work stage and an
optional note, then **Merge**. The rows become one row; its *Detected*
column lists every tool, comma-separated, e.g.
`Merged: Altium (Buttons.SchDoc, ESC_Board.PcbDoc), Edge`.
**undo merge** on that row brings the original rows back.

### What pcbtrack cannot know

Inside the PCB editor it sees "PCB editor", not whether you were placing,
routing or editing silkscreen. It guesses `pcb_layout`; set `placement`,
`routing` or `silkscreen` yourself where it matters.

## 5. Other software

Collapsed by default. The same table for everything outside Altium:
browser pages (titles are cleaned, e.g. *ESE 4025 Study Pack*), PDFs,
Excel, chat. Lower priority: fix it when it matters for a report.

## 6. Timeline

The bar shows the day zoomed to the hours you used the PC. Tick
**full 24 h** to see the whole day. Colours: green work, amber idle, purple
locked, grey not tracked, blue added by hand, striped amber where the project
was guessed. The thinner lane below shows only Altium time, coloured by work
stage. Hover over any part for details.

## 7. Add or merge time

Pick the date, a **from** and **to** time, the project and the work stage,
and describe it.

- **If the PC tracked work in that window**, all of it is **merged into one
  block** with your project and stage. Blocks that cross the window's edges
  are split there: only the part inside is merged, the rest stays as it was.
  The software used in the window is kept as a comma list, for example
  `Merged: Altium (BTN7960.PcbLib, Power.SchDoc), Edge, Acrobat`.
- **If nothing was tracked** (meeting, milling, soldering, reading on paper),
  it is simply added.

Before anything changes, **an approve dialog lists every tracked record in
the window** (program, page or document, when, how long) and says whether an
earlier log overlaps. Nothing is merged until you press **Approve & merge**.
The whole window then counts as your entry, once.

Entries are listed below the form. Each one has a folding list
*"N tracked record(s) merged into this"* showing what it replaced, for
reference only; those minutes are not counted again. **undo merge** /
**remove** puts back whatever was tracked in that window. A merge that
includes Altium counts as Altium time.

## 8. Review

The biggest uncertain blocks first. By default it shows only Altium blocks;
untick **Altium / CAD blocks only** to see the rest. Set the project and stage
and press **Save**, or **Accept all as shown** to confirm everything listed.

## 9. Breakdown cards

By work stage, by project, by software, and files by project for the day.
The checkbox in *By work stage* merges symbol library, footprint library and
component search into one *library_management* line in reports, without
changing what is stored.

## 10. Daily notes

**One note per project per day**, plus one *General* note. Every project you
worked on that day gets a box automatically; add others with *+ note for
another project*. Write what got done, then **Save**. Edit and save again any
time; saving an empty box deletes the note. Notes appear under their project
in every report.

**Note for a period** (collapsed below) is for a note that covers several
days and/or several projects at once, for example "all week: footprints for
the buck stage".

## 11. Report for a period

1. Choose **From** and **To**, or a preset: *This week*, *Last week*,
   *This month*, *Last month*.
2. Tick projects to report only those; tick none for all projects.
3. Press **Show** to preview, or download:
   - **Download report (.md)**: readable report with each project's stages,
     documents and notes.
   - **Download summary (.csv)**: hours per project x stage and per project x
     document, for a spreadsheet or invoice.
   - **Download every block (.csv)**: every block with start, end, project,
     stage, document, program and whether it was confirmed.
   - **One report per project (.zip)**: a Markdown report for each project
     plus one for all projects.
   - **Copy AI brief**: the report with a ready-made prompt, to paste into
     any AI assistant for a summary and suggestions.

**Day report** at the top of the page shows today's report as text.

## 12. Settings

- **Daily target (hours)**.
- **Project folders**, one per line, e.g. `D:\Altium\ESC_Board_5Vbuck`.
  Used to count saves per document. Optional.

### Danger zone

Collapsed and outlined in red at the bottom of Settings. Each action asks you
to **type the exact name** (or `DELETE`), asks once more, and **backs up the
whole database first** (the newest 10 backups are kept in the `backups`
folder next to your data).

| Action | What happens |
| --- | --- |
| Delete a project | The project disappears. Its time moves to the project you choose, or becomes unassigned. No tracked time is deleted. |
| Delete a client | The client disappears; its projects stay, without a client. |
| Remove a work stage | The stage disappears from every list. Its time is relabelled to the stage you choose. Built-in stages are hidden, your own are removed. `unknown` cannot be removed. |
| Delete recorded data | Everything tracked, entered by hand, split or noted on the chosen days is deleted permanently. |

To undo a mistake, stop pcbtrack (`stop.bat`), copy the backup over
`activity.db` in your data folder, and start it again.

## 13. Projects and clients

Add a project before you start work (**Add project**), give it a client, and
optionally group it under another project: one client job can hold several
Altium projects, such as the main board and a test jig. Reports can roll
sub-projects up into their parent. Rename freely; history follows the
project, not its name.

---

## A normal day

1. Log in. Tracking starts by itself.
2. Work.
3. Before you finish, open the dashboard:
   - In **Altium today**, fix amber stages (`pcb_layout` -> `routing` or
     `placement`) and wrong projects.
   - Add hand entries for anything off the PC.
   - Write one line per project in **Daily notes**.
4. On Friday, or when a client asks: **Report for a period** -> *This week* ->
   tick the client's projects -> **Download report (.md)** or **summary (.csv)**.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| Top strip says *tracking stopped* | Press **Start tracking**, or run `track.bat`. |
| *stopped unexpectedly* (red) | It restarts itself while the dashboard is open. Look at `tracker.log` in the data folder and report the error. |
| Altium time missing | Check `python -m pcbtrack doctor`. If Altium runs as administrator, run pcbtrack as administrator too. |
| A document shows under the wrong project | Change the project in its row; future time for that document follows the `.PrjPcb` it is opened with. |
| "already tracking" | One copy is already running. That is deliberate: two would count everything twice. |
| Dashboard does not open | Run `dashboard.bat` again; if port 8765 is taken by another program, set `"port"` in `config.json`. |
