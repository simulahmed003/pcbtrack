# Roadmap

## v0.1.0 - done, 24 Oct 2026

Tracking loop with the clock rules; Altium Auto Save / History / save
watching; signal ladder with confidences and reasons; dialog dictionary;
24-hour accounting; single-instance lock and crash recovery; auto-proposed
editable projects and clients; review queue; daily note; md/csv/json export;
`doctor`, `selfcheck`, `probe`; replay test.

## v0.2 - the week after the first real data

Driven by what week 1 gets wrong, in likely order:

1. **Tune the dialog dictionary** from the `probe` output and real
   mislabellings; promote `UNVERIFIED` entries.
2. **UI Automation probe, on ambiguity only.** When Altium is in front and no
   file evidence has arrived for N minutes, read the active document tab or
   the menu names. Must use `IUIAutomation2` with ~250 ms connection and
   transaction timeouts: an untimed property read against a hung application
   was measured at 23 s. This is the main fix for *viewing without editing*.
3. **Idle reason prompt.** On returning from a long idle, offer "was that a
   meeting / a break / reading?" as one click.
4. **Week and project-lifetime reports**, not just per day.
5. **`min_block_seconds` dust merging** (R9).

## v0.3

- **Tray icon and global hotkey** for mid-day project switching. Needs a
  message-pump thread, which also unlocks proper lock/unlock and sleep/resume
  events (`WTSRegisterSessionNotification`, `WM_POWERBROADCAST`) instead of
  heartbeat-gap inference.
- **KiCad support.** Easier than Altium: separate editor windows with
  informative titles, plus `~*.lck` and `_autosave-*` files, plus an IPC API
  in KiCad 9+ (request-reply only, needs `pynng` + `protobuf`, so it stays
  optional).
- **Opt-in Altium DelphiScript bridge** writing
  `DM_FocusedDocument.DM_DocumentKind` to a file. The most accurate signal
  that exists; kept optional because it must be started inside Altium each
  session.
- **Database compaction** of old raw intervals.

## v0.4 and later

- Evidence-grade export: hash-chained records so after-the-fact edits are
  detectable, for clients who want proof.
- Client mode: hide file names, show "Schematic sheet 1" instead, for NDA work.
- Estimate vs actual per project, to quote better from history.
- EasyEDA Pro, if its titles turn out to be usable.

## Explicitly not planned

Billing and invoicing maths. Cloud sync, accounts, login. Team or employer
monitoring features. Screenshots or keylogging. Productivity scoring.
