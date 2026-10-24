# Requirements

Agreed 24 Oct 2026. The outer layer: what the system must do, independent of
how it is built.

## 1. The core model

Every minute of the day is tagged on eight dimensions. Every report is a slice
of that.

| Dimension | Values | Who decides |
| --- | --- | --- |
| Time | timestamp, day | machine |
| State | work / idle / locked / off | machine, by rule |
| Client | editable list | proposed, then the user |
| Project | editable list | proposed from files, then the user |
| Software | Altium, KiCad, Edge, Excel... | machine |
| Document | `Power.SchDoc`, `ESC.PcbDoc`, `lib.PcbLib` | machine, where visible |
| Work stage | library_footprint, schematic, routing... | **machine recommends, user confirms** |
| Label source | auto / confirmed / manual / corrected | machine |

Hierarchy: **Client -> Project -> {Software} x {Documents} x {Stages}**.
One project spans many tools and many files; one tool serves many projects.
Time belongs to the project, never to the tool.

## 2. Nothing is declared up front

The user never has to register anything before tracking. The tracker proposes
the best option it can from what it sees - a project named after the `.PrjPcb`
it found, status `proposed` - and **every name is editable afterwards**.
Because history is keyed to a stable internal id, renaming a project or client
relabels all past time automatically.

When time matches no known project, the tracker still knows the software and
often the document, so the review queue **offers** that context and the user
assigns it or deliberately leaves it unassigned. It is never guessed silently
and never thrown away.

## 3. Clock conditions

| # | Condition | Status |
| --- | --- | --- |
| R1 | One writer only. A second instance exits rather than double count. | done |
| R2 | Every second has exactly one state and at most one project. | done, tested |
| R3 | `work` requires a foreground window and input within the idle threshold. | done |
| R4 | Idle is backdated to the last real input, cross-checked against the previous sample. | done |
| R5 | A short pause inside work on the same project stays work (default 5 min); longer splits the session. Sessions are recorded, and the stage is editable. | done |
| R6 | Locked, asleep and off are gaps. Never work, never interpolated. | done |
| R7 | Heartbeat every tick; on restart, open intervals close at the last heartbeat. | done |
| R8 | Observations immutable; labels a separate editable layer; corrections audited. | done |
| R9 | Intervals are capped so the review stays granular; dust merges. | partly |
| R10 | Nothing silently dropped; unattributable time is visible. | done |
| R11 | Off-PC work exists only if entered by hand. | done (`log`) |
| R12 | One machine writes at a time; a copy merges later, deduplicated. | partly |

**Invariant, tested every run:** `work + idle + locked + off = wall clock`.

## 4. Attribution conditions

Strongest signal wins; a weaker signal never overrides a stronger one.

1. a confirmed or manual label
2. a learned correction rule
3. an Altium dialog open in the foreground
4. a document extension visible in the window title
5. Altium Auto Save / History / save evidence
6. app and domain rules (LCSC, PDF, Zoom, Excel...)
7. sticky carry-over from the previous known activity
8. `unknown` -> review queue

The stage is **always a recommendation** carrying a confidence and a reason.
Reports separate confirmed from auto-guessed minutes.

## 5. Review and the daily note

| # | Condition |
| --- | --- |
| C1 | Review is optional. Skipping it loses nothing; blocks stay `auto`. |
| C2 | Review is block-level, biggest first, with project and stage dropdowns. |
| C3 | Target effort: under 2 minutes a day. |
| C4 | A correction can become a rule, applied forward only. History is never silently rewritten. |
| C5 | An optional free-text note per day and project records what was actually achieved, and appears in the daily report beside the hours. |
| C6 | Every report shows the confirmed / auto / manual split and the unassigned remainder. |

## 6. Required outputs

Per day, week and project lifetime: time per **software**, per **project and
client**, per **document** (each schematic sheet, each PCB, each library
file), per **work stage** with library and component-search separable or
merged by a single setting, plus the confirmed/auto split. Exports: CSV, JSON,
Markdown.

## 7. Out of scope

Billing or rate maths. Cloud, accounts, login, multi-user. Screenshots,
keylogging, clipboard, file contents. Productivity scoring.

## 8. Acceptance targets

| Criterion | Target | 0.1.0 |
| --- | --- | --- |
| Max writers per instant | 1 | lock + overlap-proof aggregation |
| 24h invariant holds | always | tested |
| Altium time with no stage | < 15% | 0-2% on synthetic; unmeasured live |
| Auto labels accepted unchanged | >= 85% after 2 weeks | not yet measured |
| Daily review effort | <= 2 min | not yet measured |
| Minutes lost or invented over restart/sleep/crash | 0 | recovery implemented, untested live |
| Day total vs the owner's own memory | within 5% | **week 1 task** |
| CPU while tracking | < 1% | not yet measured |
| Database growth | < 20 MB/year | ~35 bytes/tick synthetic |
