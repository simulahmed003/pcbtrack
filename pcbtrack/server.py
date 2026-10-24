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
    server_version = "pcbtrack"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, default=str).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
                    "SELECT p.id,p.name,p.status,c.name client FROM projects p"
                    " LEFT JOIN clients c ON c.id=p.client_id ORDER BY p.name")]
                s["clients"] = [dict(r) for r in c.execute("SELECT id,name FROM clients")]
                s["stages"] = CFG["stages"]
                s["generated"] = time.time()
                return self._send(200, s)
            if u.path == "/api/markdown":
                return self._send(200, report.markdown(c, CFG, _day(q)),
                                  "text/plain; charset=utf-8")
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
                store.add_note(c, day, body.get("project_id"), body["text"][:2000])
                return self._send(200, {"ok": True})
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
                if body.get("alias"):
                    c.execute("INSERT INTO aliases(project_id,pattern,kind)"
                              " VALUES(?,?,?)", (pid, body["alias"], "user"))
                c.commit()
                return self._send(200, {"ok": True})
            if u.path == "/api/merge_project":
                src, dst = body["from"], body["to"]
                c.execute("UPDATE labels SET project_id=? WHERE project_id=?", (dst, src))
                c.execute("UPDATE aliases SET project_id=? WHERE project_id=?", (dst, src))
                c.execute("DELETE FROM projects WHERE id=?", (src,))
                store.audit(c, "merge_project", src, dst)
                c.commit()
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(400, {"error": str(e)})


def serve(cfg=None, open_browser=True):
    global CFG
    CFG = cfg or config.load()
    srv = ThreadingHTTPServer(("127.0.0.1", CFG["port"]), H)
    url = "http://127.0.0.1:%d" % CFG["port"]
    print("pcbtrack dashboard: %s   (local only)" % url)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0
