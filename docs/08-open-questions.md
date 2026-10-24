# Open questions

Two kinds: things only a test on the owner's machine can settle, and
decisions for the owner.

## A. Needs a local test - run `python -m pcbtrack probe`

| # | Question | Why it matters |
| --- | --- | --- |
| A1 | Where exactly is the Recovery folder on this install, and does AD 26.7 name files `<doc>.~(n).<ext>`? | The whole stage split depends on it. Altium's KB warns naming "may vary slightly between versions". |
| A2 | What is the Auto Save default interval and version count here? | Sets the resolution of stage tracking. |
| A3 | Do child window classes differ between the schematic, PCB, SchLib and PcbLib editors? | A free signal if they do; the main window is `TDocumentForm` and the canvas class looks generic. |
| A4 | What are the ~20% of baseline Altium samples whose title was *not* the project? | May be a cheaper signal than Auto Save. |
| A5 | Does the UIA tree expose the active document tab, menu names or the status bar? | Decides whether v0.2 can track *viewing*, not just editing. |
| A6 | Does Altium keep a live record of the open document (registry, `*.ini`, `DXP.RCS`)? | Would beat everything else. Needs Process Monitor while switching tabs. |

## B. Decisions for the owner

| # | Question | Default taken if unanswered |
| --- | --- | --- |
| B1 | Is a "project" always one Altium project, or can one client project hold several (main board plus test jig)? | One `.PrjPcb` = one project; several can be merged in the dashboard. |
| B2 | How many projects active at once - 2, 5, 10? | Assumed under 10. |
| B3 | Library management and component search: one report line or two? | Two, merged by `merge_library_stages_in_report`. |
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
