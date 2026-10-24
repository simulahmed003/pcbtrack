# Baseline: 22-23 October 2026

The two days recorded with the previous title-only tracker. This is the
measurement that justified rebuilding, and the yardstick for whether v0.1 is
better.

## Data quality problem found first

Raw sums said 795 and 855 minutes. Real wall clock between the first and last
record was 411 and 465 minutes. Cause: **2 to 4 tracker instances running at
once**, each writing the same seconds. The install script started one and also
registered a logon task, and the folder had a second start script.

Corrected by taking one label per 5-second slice of wall clock. Every figure
below is deduplicated. v0.1 prevents the whole class of bug with a
single-instance lock plus overlap-discarding aggregation.

## Hours

| | Thu 22 Oct | Fri 23 Oct | Total |
| --- | --- | --- | --- |
| At the PC | 6.9 h | 7.8 h | 14.6 h |
| Active | 5.3 h | 6.6 h | 11.8 h |
| Idle (no input 3 min+) | 1.6 h | 1.2 h | 2.8 h |
| Tracking window | 15:43-22:57 | 08:15-16:16 | |

The overnight gap (22:57 to 08:15) was correctly left empty.

## By software

| Software | Thu | Fri | Total |
| --- | --- | --- | --- |
| Altium Designer (`X2.EXE`) | 4.0 h | 5.6 h | 9.7 h |
| Microsoft Edge | 44 min | 23 min | 1.1 h |
| File Explorer | 16 min | 11 min | 27 min |
| WhatsApp | 7 min | 13 min | 20 min |
| Excel (BOM sheet) | 6 min | 0 | 6 min |

## By stage - the failure

| Stage | Total | Note |
| --- | --- | --- |
| **Altium, stage unidentifiable** | **8.3 h** | **70% of active time** |
| Part sourcing (LCSC, EasyEDA) | 36 min | reliable |
| Altium dialogs, unmapped | 36 min | filed as "Other" |
| Routing / copper pour | 16 min | dialog time only, a floor |
| BOM (Altium dialog + Excel) | 9 min | floor |
| DRC | 5 min | floor |
| ECO / annotation | 5 min | floor |
| Library / component swap | 5 min | floor |
| Datasheet reading | 1 min | **badly undercounted** |
| Tool building / AI chat | 12 min | **not client work** |

Honest reading: *"11.8 h of work over two days, 9.7 h of it in Altium on
ESC_Board"* was defensible. Any split of that 9.7 h into schematic, layout and
library work was not.

## Lessons that became requirements

| Observation | Became |
| --- | --- |
| Title shows only `.PrjPcb` | Auto Save watching (`02-stage-detection.md`) |
| Dialogs carry real information, were discarded | the dialog dictionary |
| Datasheet time ~0 | PDF detection, and the review queue |
| 2-4 writers inflated everything | R1 lock + overlap-proof aggregation |
| `watch_folders` empty, so 0 file saves | auto-discovery of the Recovery path; `doctor` |
| Rates left at 0, no pay output | billing dropped from scope entirely |
| Tracker-building time counted as project work | project assignment + review |
| 70% unlabelled | acceptance target: under 15% |

## Re-run this comparison

Once v0.1 has a full real day:

```
python -m pcbtrack selfcheck
```

Compare `pct_unknown_stage` against the 70% baseline, and the dashboard's day
against your own memory (target: within 5%).
