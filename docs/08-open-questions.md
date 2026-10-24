# Open questions

Two kinds: things only a test on the owner's machine can settle, and
decisions for the owner.

## A. Needs a local test - run `python -m pcbtrack probe`

| # | Question | Why it matters |
| --- | --- | --- |
| ~~A1~~ | ~~Where is the Recovery folder?~~ **ANSWERED:** `C:\Users\<you>\AppData\Roaming\Altium\Altium Designer {D7C2F043-...}\Recovery`, found automatically by glob. Naming still to confirm once files appear. | |
| A2 | What is the Auto Save default interval and version count here? | Sets the resolution of stage tracking. |
| ~~A3~~ | ~~Do child window classes differ per editor?~~ **ANSWERED: yes, and better than hoped.** `TdxTabSheet` carries the active document name outright, and the visible `T*View_GraphicalForm` gives the editor type. This replaced Auto Save as the primary signal. | |
| ~~A4~~ | ~~What are the ~20% of samples whose caption was not the project?~~ **ANSWERED:** the caption *does* sometimes show the document (`ESC_Board.PcbDoc - Altium Designer...` appeared in the probe). Already handled, but the tab caption is more reliable. | |
| ~~A5~~ | ~~Does UIA expose the active document?~~ **MOOT.** Plain Win32 already does, so UIA is not needed at all - saving the COM dependency and the hung-app timeout risk. |  |
| A7 | What is the window class of the **footprint** library editor? Two guesses sit in `altium.py`. | Only a cross-check; the `.PcbLib` tab caption already works. Confirm on the next probe. |
| A6 | Does Altium keep a live record of the open document (registry, `*.ini`, `DXP.RCS`)? | Would beat everything else. Needs Process Monitor while switching tabs. |

## B. Decisions for the owner

| # | Question | Default taken if unanswered |
| --- | --- | --- |
| ~~B1~~ | **ANSWERED by owner: one client job can hold several Altium projects, and they overlap in time.** Built: `projects.parent_id` groups sub-projects, reports roll up (`roll_up_subprojects_in_report`), and a "Groups under" dropdown sits in the dashboard. Overlap needs nothing special - every interval is tagged independently. | |
| B2 | How many projects active at once - 2, 5, 10? | Assumed under 10. |
| ~~B3~~ | **ANSWERED: track two, present either.** Always recorded separately (`library_symbol`, `library_footprint`, `component_search`); a checkbox in the dashboard merges them into one `library_management` line for client reports. No data is ever lost to the choice. | |
| B4 | Should WhatsApp and Zoom count as client meetings automatically? | No. `messaging` at low confidence, goes to review. |
| B5 | When should the review happen - fixed time, first unlock, or only when you open the dashboard? | Only when you open the dashboard. |
| B6 | Licence: MIT, or Apache-2.0 for the patent grant once others contribute rule files? | MIT. |
| B7 | Public or private GitHub repo to start? | Owner's call at publish time. |
| B8 | Is `D:\Tracker` the permanent home? The startup entry records the path. | Yes, as given. |

## C. Known blind spots, by design

- **Viewing without editing** writes no Auto Save, so it stays unlabelled
  until v0.2's UIA probe, or the review queue, or a note.
- **Thinking time** is indistinguishable from idling. The 5-minute grace and
  the daily note are the only honest answers.
- **Datasheets on a phone or on paper** cannot be seen at all. Use `log`.
- **Browser URLs** are not read, only tab titles. Deliberate: reading the
  address bar needs UIA on browser chrome and is unreliable and slow.
