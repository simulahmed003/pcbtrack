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
    # every scratch database of this run lives under one folder, removed at
    # the end, so test runs leave nothing behind in %TEMP%
    base = tempfile.mkdtemp(prefix="pcbtrack-test-")
    tempfile.tempdir = base
    try:
        return _run()
    finally:
        tempfile.tempdir = None
        import shutil, gc
        gc.collect()                  # close stray sqlite handles (Windows locks open files)
        shutil.rmtree(base, ignore_errors=True)


def _run():
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

    # --- the active-document signal, discovered by probe on 2026-10-24 ---
    tmp2 = tempfile.mkdtemp()
    cfg2 = config.load()
    cfg2["_data_dir"] = tmp2
    cfg2["port"] = 18799
    s2 = [(1800, "X2.EXE", ALT, TD, 2, False, "ESC_PCB.SchDoc", "SCH", "document tab"),
          (900, "X2.EXE", ALT, TD, 2, False, "ESC_PCBLIB.PcbLib", "PCBLIB", "document tab"),
          (900, "X2.EXE", ALT, TD, 2, False, "ESC_SCHLIB.SchLib", "SCHLIB", "document tab"),
          (1800, "X2.EXE", ALT, TD, 2, False, "ESC_Board.PcbDoc", "PCB", "document tab"),
          (300, "X2.EXE", "Design Rule Checker [mm]", "TDrcForm", 2, False,
           "ESC_Board.PcbDoc", "PCB", "document tab")]
    tracker.run(cfg=cfg2, probe=Replay(s2, t0=start),
                max_ticks=sum(x[0] for x in s2) // tick + 3, quiet=True)
    c2 = store.connect(store.db_path(cfg2))
    from pcbtrack import report as _rp
    sm = _rp.summary(c2, cfg2, day, now=start + sum(x[0] for x in s2))
    bs, bd = sm["by_stage"], sm["by_doc"]
    print("   active-doc stages:", {k: "%.0fm" % (v / 60) for k, v in bs.items()})
    print("   active-doc docs  :", {k: "%.0fm" % (v / 60) for k, v in bd.items()})
    check("active document: all four types separated",
          bs.get("schematic", 0) > 1500 and bs.get("library_footprint", 0) > 700
          and bs.get("library_symbol", 0) > 700 and bs.get("pcb_layout", 0) > 1500)
    check("active document: dialog still wins over it", bs.get("drc", 0) > 250)
    check("active document: zero unknown", bs.get("unknown", 0) == 0,
          "%.0fs" % bs.get("unknown", 0))
    check("per-document breakdown present",
          len([k for k in bd if k]) == 4, str(sorted(k for k in bd if k)))
    c2.close()

    # --- 2026-10-24 live findings: short visits, PcbLib, carry-over ---
    tmp3 = tempfile.mkdtemp()
    cfg3 = config.load()
    cfg3["_data_dir"] = tmp3
    cfg3["port"] = 18833
    s3 = [(5, "X2.EXE", ALT, TD, 2, False, "Buttons.SchDoc", "SCH", "document tab"),
          (5, "X2.EXE", ALT, TD, 2, False, "USB_C.SchDoc", "SCH", "document tab"),
          (5, "X2.EXE", ALT, TD, 2, False, "ESC_Board.PcbDoc", "PCB", "document tab"),
          (60, "X2.EXE", ALT, TD, 2, False, "ESC_PCBLIB.PcbLib", "PCBLIB", "document tab"),
          (300, "claude.exe", "Claude", "Chrome_WidgetWin_1", 2, False),
          (300, "msedge.exe", "ESE 4025 Study Pack - Microsoft Edge", "Chrome_WidgetWin_1", 2, False)]
    tracker.run(cfg=cfg3, probe=Replay(s3, t0=start),
                max_ticks=sum(x[0] for x in s3) // tick, quiet=True)
    c3 = store.connect(store.db_path(cfg3))
    end3 = start + sum(x[0] for x in s3)
    sm3 = _rp.summary(c3, cfg3, day, now=end3)
    print("   short visits docs:", {k: "%.0fs" % v for k, v in sm3["by_doc"].items()})
    check("one-tick document visit is counted, not 0 s",
          sm3["by_doc"].get("Buttons.SchDoc", 0) >= 4 and sm3["by_doc"].get("USB_C.SchDoc", 0) >= 4,
          str(sm3["by_doc"]))
    check("chat/browser after Altium does not inherit its stage",
          sm3["by_stage"].get("unknown", 0) >= 550, str(sm3["by_stage"]))
    ok3, got3, want3 = sessionize.check_invariant(
        report_load(c3, cfg3, day, end3)[0], t0, t1, now=end3)
    check("24h accounting exact with gap joining", ok3, "%.0fs vs %.0fs" % (got3, want3))

    from pcbtrack.altium import pick_active
    d, k, _ = pick_active([("TdxTabSheet", "ESC_PCBLIB.PcbLib", True),
                           ("TPCBView_GraphicalForm", "", True)])
    check("PcbLib tab in a PCB-class editor is footprint library", k == "PCBLIB", str(k))

    # manual entry overrides tracked minutes and fills untracked ones
    pid = store.create_project(c3, "Study", client="Self")
    store.add_manual(c3, start + 400, start + 500, pid, "study_learning", "read datasheet")
    store.add_manual(c3, end3 + 600, end3 + 1200, pid, "client_meeting", "call")
    sm4 = _rp.summary(c3, cfg3, day, now=end3 + 1300)
    check("manual entry replaces tracked time", 95 <= sm4["by_stage"].get("study_learning", 0) <= 105,
          str(sm4["by_stage"]))
    check("manual entry fills untracked time", 595 <= sm4["by_stage"].get("client_meeting", 0) <= 605)
    ok4, got4, want4 = sessionize.check_invariant(
        report_load(c3, cfg3, day, end3 + 1300)[0], t0, t1, now=end3 + 1300)
    check("24h accounting exact with manual entries", ok4, "%.0fs vs %.0fs" % (got4, want4))

    # notes over a period and several projects; date-range report
    other = store.create_project(c3, "Kairon")
    store.add_note(c3, (day - dt.timedelta(days=2)).isoformat(), None, "week of footprints",
                   day_to=day.isoformat(), project_ids=[pid, other])
    check("period note shows on a day inside it",
          len(_rp.summary(c3, cfg3, day, now=end3)["notes"]) == 1)
    rr = _rp.range_summary(c3, cfg3, day - dt.timedelta(days=3), day, [pid], now=end3 + 1300)
    check("range report filtered to one project",
          list(rr["by_project"]) == ["Study"] and rr["notes"], str(rr["by_project"]))
    md = _rp.range_markdown(rr)
    check("range markdown has stages and notes", "study_learning" in md and "week of footprints" in md)
    check("range csv has rows", "Study,study_learning" in _rp.range_csv(rr))
    c3.close()

    # --- project is matched by name, else guessed and flagged ---
    tmp5 = tempfile.mkdtemp()
    cfg5 = config.load()
    cfg5["_data_dir"] = tmp5
    cfg5["port"] = 18855
    c5 = store.connect(store.db_path(cfg5))
    buck = store.create_project(c5, "Buck converter", client="Freelance")
    c5.close()
    s5 = [(120, "msedge.exe", "YouTube - Microsoft Edge", "Chrome_WidgetWin_1", 2, False),
          (180, "X2.EXE", "Altium Designer (26.7.1)", TD, 2, False,
           "Buck_Regulator.PcbDoc", "PCB", "document tab"),
          (300, "claude.exe", "Claude", "Chrome_WidgetWin_1", 2, False)]
    tracker.run(cfg=cfg5, probe=Replay(s5, t0=start),
                max_ticks=sum(x[0] for x in s5) // tick, quiet=True)
    c5 = store.connect(store.db_path(cfg5))
    end5 = start + sum(x[0] for x in s5)
    sm5 = _rp.summary(c5, cfg5, day, now=end5)
    print("   name match/guess:", {k: "%.0fs" % v for k, v in sm5["by_project"].items()},
          "guessed %.0fs" % sm5["guessed_s"])
    check("PcbDoc assigned to the project whose name it shares",
          sm5["by_project"].get("Buck converter", 0) >= 595, str(sm5["by_project"]))
    check("no work left unassigned", sm5["unassigned_s"] == 0, "%.0fs" % sm5["unassigned_s"])
    check("guessed time flagged (before and after the Altium block)",
          400 <= sm5["guessed_s"] <= 430, "%.0fs" % sm5["guessed_s"])
    rq = _rp.review_queue(c5, cfg5, day, now=end5)
    check("guessed blocks are in the review list", any(r["guess"] for r in rq))
    g = [r for r in rq if r["guess"]][0]
    store.put_label(c5, g["id"], buck, "study_learning", None, 1.0, "confirmed", "user")
    c5.commit()
    check("confirming clears the guess flag",
          c5.execute("SELECT project_guess FROM labels WHERE obs_id=?", (g["id"],)).fetchone()[0] == 0)
    c5.close()

    # --- a PcbDoc caption must not become its own project (seen live) ---
    tmp6 = tempfile.mkdtemp()
    cfg6 = config.load()
    cfg6["_data_dir"] = tmp6
    cfg6["port"] = 18866
    PCBCAP = "ESC_Board.PcbDoc - Altium Designer Professional (26.7.1)"
    s6 = [(60, "X2.EXE", ALT, TD, 2, False, "Buttons.SchDoc", "SCH", "document tab"),
          (120, "X2.EXE", PCBCAP, TD, 2, False, "ESC_Board.PcbDoc", "PCB", "document tab"),
          (60, "X2.EXE", ALT, TD, 2, False, "ESC_Board.PcbDoc", "PCB", "document tab")]
    tracker.run(cfg=cfg6, probe=Replay(s6, t0=start),
                max_ticks=sum(x[0] for x in s6) // tick, quiet=True)
    # a fresh tracker run that starts while the PcbDoc caption is showing
    s6b = [(60, "X2.EXE", PCBCAP, TD, 2, False, "ESC_Board.PcbDoc", "PCB", "document tab")]
    tracker.run(cfg=cfg6, probe=Replay(s6b, t0=start + 600),
                max_ticks=12, quiet=True)
    c6 = store.connect(store.db_path(cfg6))
    sm6 = _rp.summary(c6, cfg6, day, now=start + 700)
    print("   altium projects:", {k: "%.0fs" % v for k, v in sm6["by_project"].items()},
          "cad %.0fs" % sm6["cad"]["work_s"])
    check("PcbDoc caption stays in the .PrjPcb project",
          list(sm6["by_project"]) == ["ESC_Board_5Vbuck"], str(sm6["by_project"]))
    check("Altium card has per-document time",
          sm6["cad"]["docs"].get("ESC_Board_5Vbuck", {}).get("ESC_Board.PcbDoc", {}).get("secs", 0) >= 230)
    # detected vs work stage, relabel by row, saves, focus, week
    c6.execute("INSERT INTO evidence(t,kind,doc,doctype,path) VALUES(?,?,?,?,?)",
               (start + 100, "save", "ESC_Board", "PCB", "/p/ESC_Board.PcbDoc"))
    c6.execute("INSERT INTO evidence(t,kind,doc,doctype,path) VALUES(?,?,?,?,?)",
               (start + 200, "save", "ESC_Board", "PCB", "/p/ESC_Board.PcbDoc"))
    c6.commit()
    sm7 = _rp.summary(c6, cfg6, day, now=start + 700)
    rows = sm7["cad"]["rows"]
    pcb = [r for r in rows if r["item"] == "ESC_Board.PcbDoc"][0]
    print("   altium rows:", [(r["item"], r["detected"], r["stage"], r.get("saves")) for r in rows])
    check("Detected column is the editor, stage is separate",
          pcb["detected"] == "PCB editor" and pcb["stage"] == "pcb_layout" and not pcb["confirmed"])
    check("saves counted per document", pcb["saves"] == 2, str(pcb.get("saves")))
    for oid in pcb["ids"]:
        pj, dc = c6.execute("SELECT project_id,doc FROM labels WHERE obs_id=?", (oid,)).fetchone()
        store.put_label(c6, oid, pj, "routing", dc, 1.0, "confirmed", "user")
    c6.commit()
    sm8 = _rp.summary(c6, cfg6, day, now=start + 700)
    pr = [r for r in sm8["cad"]["rows"] if r["item"] == "ESC_Board.PcbDoc"]
    check("relabelling a row moves all its time", len(pr) == 1 and pr[0]["stage"] == "routing"
          and pr[0]["confirmed"] and pr[0]["detected"] == "PCB editor", str(pr))
    check("focus stats present", sm8["cad"]["focus_pct"] == 100 and sm8["cad"]["longest_s"] >= 230,
          "%s%% %.0fs" % (sm8["cad"]["focus_pct"], sm8["cad"]["longest_s"]))
    check("week totals include today", sm8["week"]["cad_s"] >= sm8["cad"]["work_s"] - 1)
    rr6 = _rp.range_summary(c6, cfg6, day, day, now=start + 700)
    check("AI brief has prompt and report",
          (_rp.AI_PROMPT + _rp.range_markdown(rr6)).count("routing") >= 1)
    from pcbtrack.report import clean_title
    check("browser title cleaned",
          clean_title("ESE 4025 Study Pack and 4 more pages - Personal - Microsoft​ Edge")
          == "ESE 4025 Study Pack")
    # split a row between two projects, then undo from either piece
    other6 = store.create_project(c6, "Test jig")
    own6 = c6.execute("SELECT id FROM projects WHERE name='ESC_Board_5Vbuck'").fetchone()[0]
    row = [r for r in _rp.summary(c6, cfg6, day, now=start + 700)["cad"]["rows"]
           if r["item"] == "ESC_Board.PcbDoc"][0]
    tot = row["secs"]
    _rp.split_row(c6, cfg6, day, row["ids"], [(own6, 100), (other6, 0)])
    sp = [r for r in _rp.summary(c6, cfg6, day, now=start + 700)["cad"]["rows"]
          if r["item"] == "ESC_Board.PcbDoc"]
    by = {r["project"]: r["secs"] for r in sp}
    check("split divides the row and keeps the total",
          abs(by.get("ESC_Board_5Vbuck", 0) - 100) < 1 and abs(sum(by.values()) - tot) < 1, str(by))
    jig = [r for r in sp if r["project"] == "Test jig"][0]
    store.delete_splits(c6, jig["split_ids"])
    back = [r for r in _rp.summary(c6, cfg6, day, now=start + 700)["cad"]["rows"]
            if r["item"] == "ESC_Board.PcbDoc"]
    check("undo from one piece restores the whole row",
          len(back) == 1 and abs(back[0]["secs"] - tot) < 1 and not back[0].get("split_ids"),
          str([(r["project"], r["secs"]) for r in back]))
    ok6, g6, w6 = sessionize.check_invariant(report_load(c6, cfg6, day, start + 700)[0],
                                             t0, t1, now=start + 700)
    check("24h accounting exact after split and undo", ok6, "%.0fs vs %.0fs" % (g6, w6))

    # one daily note per project, edited in place, exported per project
    store.set_daily_note(c6, day.isoformat(), other6, "routed power section")
    store.set_daily_note(c6, day.isoformat(), other6, "routed power section, DRC clean")
    store.set_daily_note(c6, day.isoformat(), None, "general: tidied library")
    dn = store.daily_notes(c6, day.isoformat())
    check("daily note is replaced, not duplicated",
          dn.get(other6) == "routed power section, DRC clean" and len(dn) == 2, str(dn))
    rr7 = _rp.range_summary(c6, cfg6, day, day, [other6], now=start + 700)
    md7 = _rp.range_markdown(rr7)
    check("project report carries its daily note under the project",
          "## Test jig" in md7 and "DRC clean" in md7.split("## Test jig")[1], md7[-300:])
    import zipfile, io
    zf = zipfile.ZipFile(io.BytesIO(_rp.range_zip(c6, cfg6, day, day)))
    check("zip has one report per project", "Test_jig.md" in zf.namelist()
          and "all_projects.md" in zf.namelist(), str(zf.namelist()))
    check("day report shows notes per project",
          "**Test jig**" in _rp.markdown(c6, cfg6, day, now=start + 700))
    store.set_daily_note(c6, day.isoformat(), None, "")
    check("saving an empty note removes it", "" not in store.daily_notes(c6, day.isoformat()))

    # danger zone: backup, delete project (time moves), client, stage, range
    bk = store.backup(c6, tmp6)
    check("backup written", os.path.getsize(bk) > 0)
    cl = store.ensure_client(c6, "Acme")
    c6.execute("UPDATE projects SET client_id=? WHERE id=?", (cl, other6))
    store.delete_project(c6, own6, move_to=other6)
    by9 = _rp.summary(c6, cfg6, day, now=start + 700)["by_project"]
    check("deleting a project moves its time", list(by9) == ["Test jig"], str(by9))
    store.delete_client(c6, cl)
    check("deleting a client keeps its projects",
          c6.execute("SELECT client_id FROM projects WHERE id=?", (other6,)).fetchone()[0] is None)
    store.replace_stage(c6, "schematic", "study_existing")
    bs9 = _rp.summary(c6, cfg6, day, now=start + 700)["by_stage"]
    check("removing a stage relabels its time", "schematic" not in bs9 and bs9.get("study_existing", 0) > 0,
          str(bs9))
    t0d, t1d = sessionize.day_window(day)
    store.delete_range(c6, t0d, t1d)
    sm9 = _rp.summary(c6, cfg6, day, now=start + 700)
    check("deleting a day removes its work", sm9["work_s"] == 0, "%.0fs" % sm9["work_s"])
    c6.close()

    # --- merging: a time window, and selected rows ---
    tmp9 = tempfile.mkdtemp()
    cfg9 = config.load()
    cfg9["_data_dir"] = tmp9
    cfg9["port"] = 18888
    s9 = [(120, "X2.EXE", ALT, TD, 2, False, "Buttons.SchDoc", "SCH", "document tab"),
          (120, "msedge.exe", "BTN7960 datasheet.pdf - Microsoft Edge", "Chrome_WidgetWin_1", 2, False),
          (120, "X2.EXE", ALT, TD, 2, False, "ESC_Board.PcbDoc", "PCB", "document tab"),
          (120, "claude.exe", "Claude", "Chrome_WidgetWin_1", 2, False),
          (60, "LockApp.exe", "Windows Default Lock Screen", "Windows.UI.Core.CoreWindow", 2, False)]
    tracker.run(cfg=cfg9, probe=Replay(s9, t0=start),
                max_ticks=sum(x[0] for x in s9) // tick, quiet=True)
    c9 = store.connect(store.db_path(cfg9))
    end9 = start + 480
    pj9 = store.create_project(c9, "Buck converter")
    # window 01:00-05:00 cuts into the first and third blocks
    tools9 = _rp.window_tools(c9, cfg9, start + 60, start + 300)
    print("   window tools:", tools9)
    check("window tools list the software, Altium with its documents",
          tools9.startswith("Altium (") and "Buttons.SchDoc" in tools9 and "ESC_Board.PcbDoc" in tools9
          and "Edge" in tools9 and "Claude" not in tools9, tools9)
    work_before9 = _rp.summary(c9, cfg9, day, now=end9)["work_s"]
    pre = _rp.absorbed(c9, cfg9, start + 60, start + 300)
    check("preview lists the records the window will absorb",
          pre["count"] == 3 and abs(pre["work_s"] - 240) < 1 and not pre["replaces"],
          str([(g["tool"], g["what"], round(g["secs"])) for g in pre["records"]]))
    mid = store.add_manual(c9, start + 60, start + 300, pj9, "library_footprint", "BTN7960 footprint", tools9)
    sm_m = _rp.summary(c9, cfg9, day, now=end9)
    ent = [m for m in sm_m["manual"] if m["id"] == mid][0]
    check("the log keeps its absorbed records for display",
          ent["absorbed"]["count"] == 3 and abs(ent["absorbed"]["work_s"] - 240) < 1)
    check("absorbed records are not counted twice", abs(sm_m["work_s"] - work_before9) < 1,
          "%.0f vs %.0f" % (sm_m["work_s"], work_before9))
    check("a later log in the same window says it replaces the earlier one",
          len(_rp.absorbed(c9, cfg9, start + 200, start + 260)["replaces"]) == 1)
    sm9 = _rp.summary(c9, cfg9, day, now=end9)
    mrow = [r for r in sm9["cad"]["rows"] if r["item"] == "BTN7960 footprint"]
    check("window merge is one Altium row with tools in Detected",
          len(mrow) == 1 and abs(mrow[0]["secs"] - 240) < 1 and mrow[0]["detected"].startswith("Merged: Altium"),
          str([(r["item"], r["detected"], round(r["secs"])) for r in sm9["cad"]["rows"]]))
    left = {r["item"]: round(r["secs"]) for r in sm9["cad"]["rows"]}
    check("blocks crossing the window edges are split, outside parts kept",
          abs(left.get("Buttons.SchDoc", 0) - 60) <= 6 and abs(left.get("ESC_Board.PcbDoc", 0) - 60) <= 6, str(left))
    ok9, g9, w9 = sessionize.check_invariant(report_load(c9, cfg9, day, end9)[0], t0, t1, now=end9)
    check("24h accounting exact after a window merge", ok9, "%.0fs vs %.0fs" % (g9, w9))
    store.delete_manual(c9, mid)
    # row merge: Buttons.SchDoc + ESC_Board.PcbDoc rows into one
    rows9 = _rp.summary(c9, cfg9, day, now=end9)["cad"]["rows"]
    ids9 = [i for r in rows9 if r["item"] in ("Buttons.SchDoc", "ESC_Board.PcbDoc") for i in r["ids"]]
    _rp.merge_rows(c9, cfg9, day, ids9, pj9, "schematic", "power stage rework")
    sm10 = _rp.summary(c9, cfg9, day, now=end9)
    mg = [r for r in sm10["cad"]["rows"] if r["item"] == "power stage rework"]
    check("row merge gives one row, one stage, tools comma list",
          len(mg) == 1 and mg[0]["stage"] == "schematic" and abs(mg[0]["secs"] - 240) <= 10
          and "Buttons.SchDoc, ESC_Board.PcbDoc" in mg[0]["detected"] and mg[0].get("merge_ids"),
          str([(r["item"], r["detected"], round(r["secs"])) for r in sm10["cad"]["rows"]]))
    check("tools list skips windows with no program", "?" not in mg[0]["detected"], mg[0]["detected"])
    store.delete_splits(c9, mg[0]["merge_ids"])
    back9 = {r["item"] for r in _rp.summary(c9, cfg9, day, now=end9)["cad"]["rows"]}
    st9 = _rp.summary(c9, cfg9, day, now=end9 + 60)["states"]
    check("the lock screen counts as locked, not work", st9.get("locked", 0) >= 50, str(st9))
    check("undo merge brings the original rows back",
          {"Buttons.SchDoc", "ESC_Board.PcbDoc"} <= back9 and "power stage rework" not in back9, str(back9))
    # delete a record: gone from tables and totals, time becomes not tracked;
    # restore brings it back
    s_before = _rp.summary(c9, cfg9, day, now=end9)
    edge = [r for r in s_before["other_rows"] if "BTN7960" in r["item"]][0]
    _rp.delete_blocks(c9, cfg9, day, edge["ids"])
    s_del = _rp.summary(c9, cfg9, day, now=end9)
    check("deleted record leaves the tables",
          not [r for r in s_del["other_rows"] if "BTN7960" in r["item"]])
    check("deleted time is not counted as work",
          abs(s_before["work_s"] - s_del["work_s"] - edge["secs"]) < 1,
          "%.0f -> %.0f (row %.0f)" % (s_before["work_s"], s_del["work_s"], edge["secs"]))
    check("deleted records are listed for restore",
          len(s_del["deleted"]) == 1 and "BTN7960" in s_del["deleted"][0]["what"][0], str(s_del["deleted"]))
    ok_d, g_d, w_d = sessionize.check_invariant(report_load(c9, cfg9, day, end9)[0], t0, t1, now=end9)
    check("24h accounting exact after a delete", ok_d, "%.0fs vs %.0fs" % (g_d, w_d))
    store.delete_splits(c9, s_del["deleted"][0]["ids"])
    s_back = _rp.summary(c9, cfg9, day, now=end9)
    check("restore brings the record back",
          abs(s_back["work_s"] - s_before["work_s"]) < 1 and not s_back["deleted"])
    c9.close()

    # a tick error under pythonw (no stderr) must not stop the tracker
    tmp8 = tempfile.mkdtemp()
    cfg8 = config.load()
    cfg8["_data_dir"] = tmp8
    cfg8["port"] = 18877
    rep8 = Replay([(60, "X2.EXE", ALT, TD, 2, False, "Buttons.SchDoc", "SCH", "document tab")],
                  t0=start)
    calls = {"n": 0}

    def flaky(tick=5):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("database is locked")
        return rep8(tick)
    saved_err = sys.stderr
    sys.stderr = None
    try:
        rc8 = tracker.run(cfg=cfg8, probe=flaky, max_ticks=14, quiet=True)
    finally:
        sys.stderr = saved_err
    c8 = store.connect(store.db_path(cfg8))
    n8 = c8.execute("SELECT COUNT(*) FROM obs").fetchone()[0]
    last8 = c8.execute("SELECT MAX(t1) FROM obs").fetchone()[0]
    check("tracker survives a tick error with no stderr",
          rc8 == 0 and calls["n"] >= 12 and last8 >= start + 50, "rc=%s calls=%d rows=%d" % (rc8, calls["n"], n8))
    c8.close()

    print("\n%d check(s) failed" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
