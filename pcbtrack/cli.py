"""Command line. Run:  python -m pcbtrack <command>"""
import sys, os, json, time, datetime as dt
from . import config, store, report, tracker, __version__

USAGE = """pcbtrack %s - local work-hour tracker for PCB/EDA work

  python -m pcbtrack track            start tracking (one instance only)
  python -m pcbtrack serve            open the dashboard (http://127.0.0.1:8765)
  python -m pcbtrack report [DATE]    write md/csv/json for a day (default today)
  python -m pcbtrack note "text" [--project NAME]
                                      log what you actually did today
  python -m pcbtrack log MIN "text" [--project NAME] [--stage STAGE]
                                      add off-PC work (meeting, milling, soldering)
  python -m pcbtrack stop [--all]     stop tracking (--all also closes the dashboard)
  python -m pcbtrack autostart on|off start tracking when you log in, or not
  python -m pcbtrack portable         keep data next to the program (USB drive)
  python -m pcbtrack status           is it running, how big is the data
  python -m pcbtrack selfcheck        append a performance line to perf.log
  python -m pcbtrack probe            inspect Altium windows (run while Altium is open)
  python -m pcbtrack projects         list projects
  python -m pcbtrack doctor           check the setup and say what is missing
""" % __version__


def _argval(args, flag, default=None):
    return args[args.index(flag) + 1] if flag in args and len(args) > args.index(flag) + 1 else default


def cmd_note(cfg, args):
    """`pcbtrack note "text" [--project NAME]`: a note for today."""
    if not args:
        print("need text"); return 2
    c = store.connect(store.db_path(cfg))
    pid = None
    name = _argval(args, "--project")
    if name:
        pid = store.propose_project(c, name)
    store.add_note(c, dt.date.today().isoformat(), pid, args[0][:2000])
    print("noted")
    return 0


def cmd_log(cfg, args):
    """`pcbtrack log MIN "text" [--project NAME] [--stage STAGE]`: hand
    entry for off-PC work that ended now."""
    if len(args) < 2:
        print('need: log <minutes> "<what>"'); return 2
    mins = float(args[0]); text = args[1]
    stage = _argval(args, "--stage", "client_meeting")
    name = _argval(args, "--project")
    c = store.connect(store.db_path(cfg))
    pid = store.propose_project(c, name) if name else None
    t1 = time.time(); t0 = t1 - mins * 60
    store.add_manual(c, t0, t1, pid, stage, text)
    print("logged %.0f min as %s" % (mins, stage))
    return 0


def cmd_selfcheck(cfg):
    """Appends one line per run so performance can be reviewed week to week."""
    c = store.connect(store.db_path(cfg))
    st = tracker.status(cfg)
    day = dt.date.today()
    s = report.summary(c, cfg, day)
    work = s["work_s"] or 1
    line = {
        "t": dt.datetime.now().isoformat(timespec="seconds"),
        "version": __version__,
        "db_mb": round(st["db_bytes"] / 1e6, 3),
        "intervals": st["intervals"],
        "evidence": st["evidence"],
        "running": st["running"],
        "recovery_dirs": len(st["recovery_dirs"]),
        "work_h": round(work / 3600.0, 2),
        "pct_unknown_stage": round(100.0 * s["unknown_s"] / work, 1),
        "pct_unassigned_project": round(100.0 * s["unassigned_s"] / work, 1),
        "pct_confirmed": round(100.0 * s["confirmed_s"] / work, 1),
    }
    path = os.path.join(cfg["_data_dir"], "perf.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
    print(json.dumps(line, indent=1))
    print("appended -> %s" % path)
    return 0


def cmd_doctor(cfg):
    """`pcbtrack doctor`: check Python, platform, Altium Recovery folder and
    whether tracking runs. Exit code 1 when something needs fixing."""
    from . import signals
    ok = True
    print("pcbtrack %s" % __version__)
    print("data dir      : %s" % cfg["_data_dir"])
    print("python        : %s" % sys.version.split()[0])
    if sys.version_info < (3, 8):
        print("  ! needs Python 3.8+"); ok = False
    print("platform      : %s%s" % (sys.platform,
          "" if sys.platform == "win32" else "   ! live tracking needs Windows"))
    recs = signals.recovery_dirs(cfg)
    if recs:
        print("Altium Recovery: %s" % recs[0])
        try:
            files = [f for f in os.listdir(recs[0]) if signals.classify_filename(f)[1]]
            print("  recovery files: %d  %s" % (len(files), files[:4]))
            if not files:
                print("  ! none yet - turn Auto Save on in Altium (see docs/07-install-windows.md)")
                ok = False
        except OSError as e:
            print("  ! %s" % e); ok = False
    else:
        print("Altium Recovery: NOT FOUND")
        print("  ! without it, schematic / PCB / symbol / footprint cannot be told apart")
        ok = False
    st = tracker.status(cfg)
    print("tracking now  : %s" % ("yes" if st["running"] else "no"))
    print("intervals     : %d   db %.2f MB" % (st["intervals"], st["db_bytes"] / 1e6))
    print("\n%s" % ("Setup looks good." if ok else "Fix the ! lines above."))
    return 0 if ok else 1


def main(argv=None):
    """Entry point for `python -m pcbtrack <command>`; see USAGE."""
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE); return 0
    cmd, args = argv[0], argv[1:]
    cfg = config.load()
    if cmd == "track":
        return tracker.run(cfg)
    if cmd == "serve":
        from . import server
        return server.serve(cfg)
    if cmd == "report":
        day = dt.date.fromisoformat(args[0]) if args else dt.date.today()
        c = store.connect(store.db_path(cfg))
        base = report.export(c, cfg, day)
        print(report.markdown(c, cfg, day))
        print("wrote %s.md / .csv / .json" % base)
        return 0
    if cmd == "stop":
        if tracker.is_running(cfg):
            print("tracker stopped" if tracker.request_stop(cfg) else "tracker did not stop in 10 s")
        else:
            print("tracker was not running")
        if "--all" in args:
            import urllib.request
            try:
                urllib.request.urlopen(urllib.request.Request(
                    "http://127.0.0.1:%d/api/quit" % cfg["port"], data=b"{}"), timeout=3)
                import socket
                for _ in range(20):         # wait until the port is really free
                    try:
                        socket.create_connection(("127.0.0.1", cfg["port"]), 0.3).close()
                        time.sleep(0.25)
                    except OSError:
                        break
                print("dashboard closed")
            except Exception:
                print("dashboard was not running")
        return 0
    if cmd == "portable":
        # Move to portable mode: data next to the program (USB drive friendly).
        import sqlite3, shutil
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        flag = os.path.join(root, "portable.flag")
        if os.path.exists(flag):
            print("already portable: data in %s" % os.path.join(root, "data")); return 0
        if tracker.is_running(cfg):
            tracker.request_stop(cfg)
        dst = os.path.join(root, "data")
        os.makedirs(dst, exist_ok=True)
        src_db = store.db_path(cfg)
        if os.path.exists(src_db) and not os.path.exists(os.path.join(dst, "activity.db")):
            s, d = sqlite3.connect(src_db), sqlite3.connect(os.path.join(dst, "activity.db"))
            s.backup(d); d.close(); s.close()
        src_cfg = os.path.join(cfg["_data_dir"], "config.json")
        if os.path.exists(src_cfg) and not os.path.exists(os.path.join(dst, "config.json")):
            shutil.copy(src_cfg, dst)
        open(flag, "w").close()
        print("portable mode on: data in %s (your old data is still in %s)"
              % (dst, cfg["_data_dir"]))
        print("delete portable.flag to go back")
        return 0
    if cmd == "autostart":
        on = (args[:1] or ["on"])[0] != "off"
        tracker.set_autostart(on)
        print("start at login: %s" % ("on" if on else "off"))
        return 0
    if cmd == "note":
        return cmd_note(cfg, args)
    if cmd == "log":
        return cmd_log(cfg, args)
    if cmd == "status":
        print(json.dumps(tracker.status(cfg), indent=1)); return 0
    if cmd == "selfcheck":
        return cmd_selfcheck(cfg)
    if cmd == "doctor":
        return cmd_doctor(cfg)
    if cmd == "probe":
        from . import probe
        return 0 if probe.run() else 0
    if cmd == "projects":
        c = store.connect(store.db_path(cfg))
        for r in c.execute("SELECT p.id,p.name,p.status,c.name cl FROM projects p"
                           " LEFT JOIN clients c ON c.id=p.client_id ORDER BY p.name"):
            print("%-14s %-28s %-10s %s" % (r["id"], r["name"], r["status"], r["cl"] or "-"))
        return 0
    print("unknown command %r\n\n%s" % (cmd, USAGE))
    return 2
