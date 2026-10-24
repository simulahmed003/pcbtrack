"""Synthetic workday through the real pipeline. Run: python tests/replay_day.py
Mirrors the shape of the 2026-10-22/23 baseline: long Altium stretches whose
title says only the project, with Auto Save evidence revealing the document."""
import os, sys, time, datetime as dt, tempfile, sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pcbtrack import config, store, sessionize, classify
from pcbtrack.report import load_day as report_load
from pcbtrack.sysmon import Replay
from pcbtrack import tracker

ALT = "ESC_Board_5Vbuck.PrjPcb - Altium Designer Professional (26.7.1)"
TD = "TDocumentForm"
FAILS = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (" :: " + detail if detail else ""))
    if not cond:
        FAILS.append(name)


def main():
    tmp = tempfile.mkdtemp()
    cfg = config.load()
    cfg["_data_dir"] = tmp
    cfg["port"] = 18765
    tick = cfg["tick_seconds"]
    day = dt.date.today()
    start = dt.datetime.combine(day, dt.time(9, 0)).timestamp()

    # (duration_s, app, title, wclass, idle_s, locked)
    script = [
        (1800, "X2.EXE", ALT, TD, 2, False),                      # 30m schematic
        (120,  "X2.EXE", "Engineering Change Order", "TEcoForm", 2, False),
        (900,  "msedge.exe", "BTS7960 datasheet.pdf - Edge", "Chrome_WidgetWin_1", 3, False),
        (600,  "msedge.exe", "LED Indication | LCSC and 9 more pages",
         "Chrome_WidgetWin_1", 3, False),
        (1200, "X2.EXE", ALT, TD, 2, False),                      # 20m footprint lib
        (240,  "X2.EXE", " PCB Model", "TModelForm", 2, False),
        (600,  "", "", "", 900, False),                           # 10m real idle
        (3600, "X2.EXE", ALT, TD, 2, False),                      # 60m pcb layout
        (300,  "X2.EXE", "Polygon Pour Manager (45 Polygons)", "TPourForm", 2, False),
        (180,  "X2.EXE", "Design Rule Checker [mm]", "TDrcForm", 2, False),
        (300,  "WhatsApp.Root.exe", "WhatsApp", "Chrome_WidgetWin_1", 2, False),
        (600,  "", "", "", 5, True),                              # 10m locked
    ]
    rep = Replay(script, t0=start)

    # Auto Save evidence, written as Altium would: the extension is the answer
    conn = store.connect(store.db_path(cfg))
    ev = [
        (start + 600,  "recovery", "Power",      "SCH",    "Power.~(1).SchDoc"),
        (start + 1500, "recovery", "Power",      "SCH",    "Power.~(2).SchDoc"),
        (start + 4300, "recovery", "ESC_FOOT",   "PCBLIB", "ESC_FOOT.~(1).PcbLib"),
        (start + 4600, "recovery", "ESC_FOOT",   "PCBLIB", "ESC_FOOT.~(2).PcbLib"),
        (start + 6200, "recovery", "ESC_Board",  "PCB",    "ESC_Board.~(1).PcbDoc"),
        (start + 7400, "recovery", "ESC_Board",  "PCB",    "ESC_Board.~(2).PcbDoc"),
        (start + 8600, "recovery", "ESC_Board",  "PCB",    "ESC_Board.~(3).PcbDoc"),
    ]
    for t, k, d, dtp, p in ev:
        conn.execute("INSERT INTO evidence(t,kind,doc,doctype,path) VALUES(?,?,?,?,?)",
                     (t, k, d, dtp, "/Recovery/" + p))
    conn.commit()
    conn.close()

    ticks = sum(s[0] for s in script) // tick
    rc = tracker.run(cfg=cfg, probe=rep, max_ticks=ticks + 5, quiet=True)
    check("tracker ran", rc == 0)

    conn = store.connect(store.db_path(cfg))
    t0, t1 = sessionize.day_window(day, cfg["day_cutover_hour"])
    now = start + sum(s[0] for s in script)
    iv = sessionize.intervals(conn, t0, t1)
    iv = sessionize.with_off(iv, t0, t1, now=now)
    iv = sessionize.apply_grace(iv, cfg["thinking_grace_seconds"])

    ok, got, want = sessionize.check_invariant(iv, t0, t1, now=now)
    check("24h accounting exact", ok, "%.0fs vs %.0fs" % (got, want))

    by_state = sessionize.rollup(iv, lambda x: x["state"])
    print("   states:", {k: "%.0fm" % (v / 60) for k, v in by_state.items()})
    check("locked recorded", by_state.get("locked", 0) >= 590)
    check("idle recorded", by_state.get("idle", 0) >= 540)
    check("off fills the rest", by_state.get("off", 0) > 0)

    work = [x for x in iv if x["state"] == "work"]
    by_stage = sessionize.rollup(work, lambda x: x["stage"])
    print("   stages:", {k: "%.0fm" % (v / 60) for k, v in by_stage.items()})
    for want_stage in ("schematic", "library_footprint", "routing",
                       "component_search", "drc", "eco_sync"):
        check("stage present: " + want_stage, by_stage.get(want_stage, 0) > 0)
    check("schematic ~30m", 1500 <= by_stage.get("schematic", 0) <= 2300,
          "%.0fs" % by_stage.get("schematic", 0))
    check("footprint lib ~24m", 1150 <= by_stage.get("library_footprint", 0) <= 1800,
          "%.0fs" % by_stage.get("library_footprint", 0))
    unknown = by_stage.get("unknown", 0)
    tot_work = sum(by_stage.values())
    check("segmented: schematic and footprint both survive a constant caption",
          by_stage.get("schematic", 0) > 600 and by_stage.get("library_footprint", 0) > 600,
          "sch=%.0fs foot=%.0fs" % (by_stage.get("schematic", 0),
                                    by_stage.get("library_footprint", 0)))
    check("unknown under 15% of work", unknown / max(tot_work, 1) < 0.15,
          "%.1f%%" % (100 * unknown / max(tot_work, 1)))

    from pcbtrack import classify as _cl
    n = _cl.backfill(conn, cfg, t0, t1)
    iv2, _, _ = report_load(conn, cfg, day, now)
    w2 = [x for x in iv2 if x["state"] == "work"]
    bs2 = sessionize.rollup(w2, lambda x: x["stage"])
    check("backfill improved the session start", bs2.get("unknown", 0) <= by_stage.get("unknown", 0),
          "unknown %.0fs -> %.0fs (%d segments filled)"
          % (by_stage.get("unknown", 0), bs2.get("unknown", 0), n))

    by_proj = sessionize.rollup(work, lambda x: x["project_id"])
    names = store.project_names(conn)
    print("   projects:", {names.get(k, k): "%.0fm" % (v / 60) for k, v in by_proj.items()})
    check("one project detected", len([k for k in by_proj if k]) == 1)

    # no overlap anywhere
    bad = [(a["t1"], b["t0"]) for a, b in zip(iv, iv[1:]) if b["t0"] < a["t1"] - 0.001]
    check("no overlapping intervals", not bad, str(bad[:3]))

    rows = conn.execute("SELECT COUNT(*) n FROM obs").fetchone()["n"]
    size = os.path.getsize(store.db_path(cfg))
    print("   %d intervals from %d ticks, db %d bytes (%.1f bytes/tick)"
          % (rows, ticks, size, size / ticks))
    check("intervals far fewer than ticks", rows < ticks / 5, "%d vs %d" % (rows, ticks))

    # a human correction must survive a re-label
    oid = work[0]["id"]
    store.put_label(conn, oid, work[0]["project_id"], "study_existing", None,
                    1.0, "confirmed", "user")
    store.put_label(conn, oid, work[0]["project_id"], "schematic", None,
                    0.8, "auto", "robot")
    got_stage = conn.execute("SELECT stage FROM labels WHERE obs_id=?", (oid,)).fetchone()["stage"]
    check("human label not overwritten by automation", got_stage == "study_existing")
    conn.close()

    print("\n%d check(s) failed" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
