"""Local dashboard. Binds 127.0.0.1 only: nothing is exposed to the network
and nothing is ever uploaded."""
import os, json, time, datetime as dt, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from . import config, store, report, classify

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = None


def _day(q):
    v = (q.get("date") or [None])[0]
    return dt.date.fromisoformat(v) if v else dt.date.today()


class H(BaseHTTPRequestHandler):
    """The JSON API behind web/dashboard.html.

    GET  /                 the dashboard page
    GET  /api/day?date=    everything for one day (report.summary + lists)
    GET  /api/now          small live status, polled every 5 s
    GET  /api/range        period report: fmt=json|md|csv|csvdetail|zip|brief
    GET  /api/markdown     day report text;  /api/export  write day files
    POST /api/label        set project / stage for block ids
    POST /api/split        split a row between projects; /api/split/undo
    POST /api/merge        join selected rows into one; /api/merge/undo
    POST /api/manual       hand entry; /api/manual/delete
    POST /api/daynote      the one note per project per day
    POST /api/note         period note; /api/note/delete
    POST /api/project      edit project; /api/project/create; /api/merge_project
    POST /api/stage        add a custom stage
    POST /api/setting      daily target, project folders, report switches
    POST /api/tracker      start / stop tracking; /api/autostart
    POST /api/danger       deletions, behind typed confirmation + backup
    POST /api/quit         close the dashboard"""
    server_version = "pcbtrack"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", filename=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, default=str).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % filename)
        self.end_headers()
        self.wfile.write(body)

    def _conn(self):
        return store.connect(store.db_path(CFG))

    # ---------------- GET ----------------
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                with open(os.path.join(HERE, "web", "dashboard.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            c = self._conn()
            if u.path == "/api/day":
                s = report.summary(c, CFG, _day(q))
                s["review"] = report.review_queue(c, CFG, _day(q))
                s["projects"] = [dict(r) for r in c.execute(
                    "SELECT p.id,p.name,p.status,p.parent_id,c.name client"
                    " FROM projects p LEFT JOIN clients c ON c.id=p.client_id"
                    " ORDER BY p.name")]
                s["merge_library"] = bool(CFG.get("merge_library_stages_in_report"))
                s["clients"] = [dict(r) for r in c.execute("SELECT id,name FROM clients")]
                s["stages"] = CFG["stages"]
                s["generated"] = time.time()
                s["version"] = __import__("pcbtrack").__version__
                return self._send(200, s)
            if u.path == "/api/now":
                from . import tracker
                n = report.now_snapshot(c, CFG)
                n["running"] = tracker.is_running(CFG)
                n["autostart"] = os.path.exists(tracker.startup_file())
                n["stopped_by_user"] = _stopped_by_user(c)
                return self._send(200, n)
            if u.path == "/api/markdown":
                return self._send(200, report.markdown(c, CFG, _day(q)),
                                  "text/plain; charset=utf-8")
            if u.path == "/api/range":
                d0 = dt.date.fromisoformat(q["from"][0])
                d1 = dt.date.fromisoformat((q.get("to") or q["from"])[0])
                pids = [p for p in (q.get("projects") or [""])[0].split(",") if p]
                r = report.range_summary(c, CFG, d0, d1, pids)
                f = (q.get("fmt") or ["json"])[0]
                stem = "pcbtrack_%s_to_%s" % (r["from"], r["to"])
                dl = (q.get("download") or ["0"])[0] == "1"
                if f == "md":
                    return self._send(200, report.range_markdown(r), "text/markdown; charset=utf-8",
                                      stem + ".md" if dl else None)
                if f == "zip":
                    return self._send(200, report.range_zip(c, CFG, d0, d1, pids),
                                      "application/zip", stem + "_by_project.zip")
                if f == "brief":
                    return self._send(200, report.AI_PROMPT + report.range_markdown(r),
                                      "text/plain; charset=utf-8")
                if f in ("csv", "csvdetail"):
                    return self._send(200, report.range_csv(r, f == "csvdetail"),
                                      "text/csv; charset=utf-8",
                                      stem + ("_detail" if f == "csvdetail" else "") + ".csv")
                r.pop("rows", None)
                return self._send(200, r)
            if u.path == "/api/export":
                base = report.export(c, CFG, _day(q))
                return self._send(200, {"ok": True, "base": base})
            if u.path == "/api/status":
                from . import tracker
                return self._send(200, tracker.status(CFG))
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    # ---------------- POST ----------------
    def do_POST(self):
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            c = self._conn()
            if u.path == "/api/label":
                ids = body.get("ids") or ([body["id"]] if "id" in body else [])
                for oid in ids:
                    before = c.execute("SELECT * FROM labels WHERE obs_id=?",
                                       (oid,)).fetchone()
                    pid = body.get("project_id", before["project_id"] if before else None)
                    stage = body.get("stage", before["stage"] if before else None)
                    store.put_label(c, oid, pid, stage,
                                    before["doc"] if before else None,
                                    1.0, body.get("source", "confirmed"), "user review")
                    store.audit(c, "label:%s" % oid,
                                dict(before) if before else None,
                                {"project_id": pid, "stage": stage})
                if body.get("learn") and body.get("match"):
                    classify.learn(c, body["match"], "stage", body.get("stage"))
                c.commit()
                return self._send(200, {"ok": True, "n": len(ids)})
            if u.path == "/api/note":
                day = body.get("day") or dt.date.today().isoformat()
                store.add_note(c, day, body.get("project_id"), body["text"][:2000],
                               day_to=body.get("day_to") or None,
                               project_ids=body.get("project_ids"))
                return self._send(200, {"ok": True})
            if u.path == "/api/daynote":
                store.set_daily_note(c, body["day"], body.get("project_id") or None,
                                     body.get("text") or "")
                return self._send(200, {"ok": True})
            if u.path == "/api/note/delete":
                c.execute("DELETE FROM notes WHERE id=?", (int(body["id"]),))
                c.commit()
                return self._send(200, {"ok": True})
            if u.path == "/api/project/create":
                name = (body.get("name") or "").strip()[:120]
                if not name:
                    return self._send(400, {"error": "name required"})
                pid = store.create_project(c, name, body.get("client"),
                                           body.get("parent_id") or None)
                return self._send(200, {"ok": True, "id": pid})
            if u.path == "/api/stage":
                import re as _re
                name = _re.sub(r"[^a-z0-9_]+", "_", (body.get("name") or "").strip().lower()).strip("_")[:40]
                if not name:
                    return self._send(400, {"error": "name required"})
                custom = list(CFG.get("custom_stages") or [])
                if name not in custom and name not in CFG["stages"]:
                    custom.append(name)
                    config.save_user({"custom_stages": custom})
                    CFG["custom_stages"] = custom
                    CFG["stages"] = config.all_stages(CFG)
                return self._send(200, {"ok": True, "stage": name})
            if u.path == "/api/manual":
                day = dt.date.fromisoformat(body["date"])
                a = dt.datetime.combine(day, dt.time.fromisoformat(body["start"]))
                b = dt.datetime.combine(day, dt.time.fromisoformat(body["end"]))
                if b <= a:
                    b += dt.timedelta(days=1)          # past midnight
                tools = report.window_tools(c, CFG, a.timestamp(), b.timestamp())
                oid = store.add_manual(c, a.timestamp(), b.timestamp(),
                                       body.get("project_id") or None,
                                       body.get("stage") or "unknown",
                                       (body.get("text") or "")[:200], tools)
                return self._send(200, {"ok": True, "id": oid})
            if u.path == "/api/tracker":
                from . import tracker
                if body.get("action") == "stop":
                    ok = tracker.request_stop(CFG)
                elif body.get("action") == "start":
                    ok = tracker.is_running(CFG) or tracker.start_detached(CFG)
                else:
                    return self._send(400, {"error": "action must be start or stop"})
                return self._send(200, {"ok": ok, "running": tracker.is_running(CFG)})
            if u.path == "/api/autostart":
                from . import tracker
                on = tracker.set_autostart(bool(body.get("on")))
                return self._send(200, {"ok": True, "autostart": on})
            if u.path == "/api/quit":
                self._send(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if u.path == "/api/split":
                day = dt.date.fromisoformat(body["date"])
                parts = [(p.get("project_id") or None, float(p.get("minutes", 0)) * 60)
                         for p in body.get("parts", [])]
                n = report.split_row(c, CFG, day, [int(i) for i in body["ids"]], parts)
                return self._send(200, {"ok": n > 0, "pieces": n})
            if u.path == "/api/merge":
                day = dt.date.fromisoformat(body["date"])
                n = report.merge_rows(c, CFG, day, [int(i) for i in body["ids"]],
                                      body.get("project_id") or None,
                                      body.get("stage") or "unknown",
                                      (body.get("note") or "").strip())
                return self._send(200, {"ok": n > 0, "pieces": n})
            if u.path in ("/api/split/undo", "/api/merge/undo"):
                n = store.delete_splits(c, [int(i) for i in body["ids"]])
                return self._send(200, {"ok": True, "removed": n})
            if u.path == "/api/split/undo":
                n = store.delete_splits(c, [int(i) for i in body["ids"]])
                return self._send(200, {"ok": True, "removed": n})
            if u.path == "/api/danger":
                return self._danger(c, body)
            if u.path == "/api/manual/delete":
                ok = store.delete_manual(c, int(body["id"]))
                return self._send(200 if ok else 404, {"ok": ok})
            if u.path == "/api/project":
                pid = body["id"]
                if "name" in body:
                    store.rename_project(c, pid, body["name"][:120])
                if "status" in body:
                    c.execute("UPDATE projects SET status=? WHERE id=?",
                              (body["status"], pid))
                if body.get("client"):
                    cid = store.ensure_client(c, body["client"][:120])
                    c.execute("UPDATE projects SET client_id=? WHERE id=?", (cid, pid))
                if "parent_id" in body:
                    pv = body["parent_id"] or None
                    if pv != pid:
                        c.execute("UPDATE projects SET parent_id=? WHERE id=?", (pv, pid))
                if body.get("alias"):
                    c.execute("INSERT INTO aliases(project_id,pattern,kind)"
                              " VALUES(?,?,?)", (pid, body["alias"], "user"))
                c.commit()
                return self._send(200, {"ok": True})
            if u.path == "/api/setting":
                from . import config as _cfg
                key, val = body["key"], body["value"]
                if key in ("merge_library_stages_in_report",
                           "roll_up_subprojects_in_report"):
                    val = bool(val)
                elif key == "daily_target_hours":
                    val = max(0.0, min(24.0, float(val)))
                elif key == "project_dirs":
                    val = [str(v).strip() for v in (val or []) if str(v).strip()][:20]
                    missing = [v for v in val if not os.path.isdir(os.path.expandvars(v))]
                    if missing:
                        return self._send(400, {"error": "folder not found: " + ", ".join(missing)})
                else:
                    return self._send(400, {"error": "not a settable key"})
                _cfg.save_user({key: val})
                CFG[key] = val
                return self._send(200, {"ok": True, key: val})
            if u.path == "/api/merge_project":
                src, dst = body["from"], body["to"]
                c.execute("UPDATE labels SET project_id=? WHERE project_id=?", (dst, src))
                c.execute("UPDATE aliases SET project_id=? WHERE project_id=?", (dst, src))
                c.execute("UPDATE doc_projects SET project_id=? WHERE project_id=?", (dst, src))
                c.execute("UPDATE projects SET parent_id=? WHERE parent_id=?", (dst, src))
                c.execute("DELETE FROM projects WHERE id=?", (src,))
                store.audit(c, "merge_project", src, dst)
                c.commit()
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(400, {"error": str(e)})


def _danger(self, c, body):
    """Deleting things. Every action needs the exact confirmation text the
    dashboard asked for, and backs up the database first."""
    act = body.get("action")
    confirm = (body.get("confirm") or "").strip()
    if act == "delete_project":
        r = c.execute("SELECT name FROM projects WHERE id=?", (body.get("id"),)).fetchone()
        if not r or confirm != r["name"]:
            return self._send(400, {"error": "type the project name exactly to confirm"})
        bk = store.backup(c, CFG["_data_dir"])
        store.delete_project(c, body["id"], body.get("move_to") or None)
    elif act == "delete_client":
        r = c.execute("SELECT name FROM clients WHERE id=?", (body.get("id"),)).fetchone()
        if not r or confirm != r["name"]:
            return self._send(400, {"error": "type the client name exactly to confirm"})
        bk = store.backup(c, CFG["_data_dir"])
        store.delete_client(c, body["id"])
    elif act == "delete_stage":
        st, to = body.get("stage"), body.get("move_to") or "unknown"
        if st == "unknown" or st not in CFG["stages"] or to == st:
            return self._send(400, {"error": "that stage cannot be removed"})
        if confirm != st:
            return self._send(400, {"error": "type the stage name exactly to confirm"})
        bk = store.backup(c, CFG["_data_dir"])
        store.replace_stage(c, st, to)
        custom = [x for x in CFG.get("custom_stages") or [] if x != st]
        hidden = list(CFG.get("hidden_stages") or [])
        if st in config.DEFAULTS["stages"] and st not in hidden:
            hidden.append(st)
        config.save_user({"custom_stages": custom, "hidden_stages": hidden})
        CFG["custom_stages"], CFG["hidden_stages"] = custom, hidden
        CFG["stages"] = config.all_stages(CFG)
    elif act == "delete_range":
        if confirm != "DELETE":
            return self._send(400, {"error": "type DELETE to confirm"})
        d0 = dt.date.fromisoformat(body["from"])
        d1 = dt.date.fromisoformat(body.get("to") or body["from"])
        if d1 < d0:
            d0, d1 = d1, d0
        t0 = dt.datetime.combine(d0, dt.time(0)).timestamp()
        t1 = dt.datetime.combine(d1 + dt.timedelta(days=1), dt.time(0)).timestamp()
        bk = store.backup(c, CFG["_data_dir"])
        n = store.delete_range(c, t0, t1)
        c.execute("DELETE FROM notes WHERE day>=? AND COALESCE(day_to,day)<=?",
                  (d0.isoformat(), d1.isoformat()))
        c.commit()
        return self._send(200, {"ok": True, "deleted_blocks": n, "backup": bk})
    else:
        return self._send(400, {"error": "unknown action"})
    return self._send(200, {"ok": True, "backup": bk})


H._danger = _danger


def _stopped_by_user(c):
    """True when the last stop was asked for (Stop tracking / pcbtrack stop),
    False when the tracker went away on its own."""
    started = float(store.meta_get(c, "started") or 0)
    req = float(store.meta_get(c, "stop_request") or 0)
    return req > started


def _watchdog(every=30):
    """While the dashboard runs, bring back a tracker that stopped without
    being asked to. At most one restart per 5 minutes, logged."""
    from . import tracker
    last = 0.0
    while True:
        time.sleep(every)
        try:
            if tracker.is_running(CFG) or time.time() - last < 300:
                continue
            c = store.connect(store.db_path(CFG))
            try:
                if store.meta_get(c, "heartbeat") and not _stopped_by_user(c):
                    last = time.time()
                    tracker._log("watchdog: tracker was not running, restarting")
                    tracker.start_detached(CFG)
            finally:
                c.close()
        except Exception as e:
            tracker._log("watchdog: %r" % (e,))


def serve(cfg=None, open_browser=True):
    """Run the dashboard until closed. One copy only: a second launch just
    opens the browser on the running one."""
    global CFG
    CFG = cfg or config.load()
    from .tracker import guard_streams
    guard_streams(CFG, "dashboard.log")
    url = "http://127.0.0.1:%d" % CFG["port"]

    class Server(ThreadingHTTPServer):
        # ThreadingHTTPServer sets SO_REUSEADDR, which on Windows lets several
        # dashboards bind the same port; an old copy then answers with old
        # code. One dashboard only: a second launch just opens the browser.
        # (SO_EXCLUSIVEADDRUSE was tried and rejected: it refuses to bind
        # while the previous dashboard's connections sit in TIME_WAIT, so a
        # quick restart failed for minutes.)
        allow_reuse_address = False
    srv = None
    for _ in range(8):          # a dashboard that is just closing frees the port
        try:
            srv = Server(("127.0.0.1", CFG["port"]), H)
            break
        except OSError:
            time.sleep(0.5)
    if srv is None:
        print("dashboard already running: %s" % url)
        if open_browser:
            webbrowser.open(url)
        return 0
    print("pcbtrack dashboard: %s   (local only)" % url)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        if CFG.get("watchdog", True):     # off for test dashboards on copied data
            threading.Thread(target=_watchdog, daemon=True).start()
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0
