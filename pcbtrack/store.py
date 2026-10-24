"""SQLite store. Two layers:
   obs/evidence  - immutable observations, never rewritten
   labels        - mutable interpretation, freely editable by the user
Renaming a project or client changes a name only; history follows the stable id.
"""
import sqlite3, os, time, json, re, uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS obs(
  id INTEGER PRIMARY KEY,
  t0 REAL NOT NULL, t1 REAL NOT NULL,
  state TEXT NOT NULL,              -- work | idle | locked | off
  app TEXT, title TEXT, wclass TEXT,
  collector TEXT
);
CREATE INDEX IF NOT EXISTS obs_t0 ON obs(t0);
CREATE TABLE IF NOT EXISTS evidence(
  id INTEGER PRIMARY KEY,
  t REAL NOT NULL, kind TEXT,       -- recovery | history | save
  doc TEXT, doctype TEXT,           -- SCH | PCB | SCHLIB | PCBLIB | OTHER
  path TEXT,
  UNIQUE(kind, path, t)
);
CREATE INDEX IF NOT EXISTS ev_t ON evidence(t);
CREATE TABLE IF NOT EXISTS labels(
  obs_id INTEGER PRIMARY KEY,
  project_id TEXT, stage TEXT, doc TEXT,
  confidence REAL, source TEXT,     -- auto | confirmed | manual | corrected
  reason TEXT, updated REAL
);
CREATE INDEX IF NOT EXISTS lab_proj ON labels(project_id);
CREATE TABLE IF NOT EXISTS clients(
  id TEXT PRIMARY KEY, name TEXT, created REAL);
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY, name TEXT, client_id TEXT,
  status TEXT,                      -- proposed | active | hold | closed
  created REAL,
  parent_id TEXT);                   -- one client job, several Altium projects
CREATE TABLE IF NOT EXISTS aliases(
  id INTEGER PRIMARY KEY, project_id TEXT, pattern TEXT, kind TEXT);
CREATE TABLE IF NOT EXISTS notes(
  id INTEGER PRIMARY KEY, day TEXT, project_id TEXT, text TEXT, created REAL);
CREATE TABLE IF NOT EXISTS rules(
  id INTEGER PRIMARY KEY, match TEXT, field TEXT, value TEXT,
  scope TEXT, created REAL);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, t REAL, what TEXT, before TEXT, after TEXT);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path):
    first = not os.path.exists(path)
    c = sqlite3.connect(path, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.executescript(SCHEMA)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(projects)")}
    if "parent_id" not in cols:
        # one client job can hold several Altium projects (main board + test jig)
        c.execute("ALTER TABLE projects ADD COLUMN parent_id TEXT")
    if first:
        c.execute("INSERT OR IGNORE INTO meta(k,v) VALUES('schema','1')")
    c.commit()
    return c


def db_path(cfg):
    return os.path.join(cfg["_data_dir"], "activity.db")


# ---------- meta / heartbeat ----------
def meta_get(c, k, default=None):
    r = c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def meta_set(c, k, v):
    c.execute("INSERT INTO meta(k,v) VALUES(?,?)"
              " ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


# ---------- observations ----------
class ObsWriter:
    """Appends intervals, merging consecutive identical observations.
    One row per contiguous state, not one row per sample: this keeps the
    database 1-2 orders of magnitude smaller than per-tick logging."""

    def __init__(self, conn, collector, max_gap, max_span=600):
        self.c = conn
        self.collector = collector
        self.max_gap = max_gap
        self.max_span = max_span
        self.key = None
        self.rowid = None
        self.last_t = None
        self.row_t0 = None

    def add(self, t, state, app, title, wclass, labelkey=None):
        """labelkey is part of the merge key on purpose. A long Altium session
        keeps one unchanging caption for hours, so without it the whole stretch
        would collapse into a single row and could carry only ONE stage - the
        per-document breakdown would be lost. max_span also caps a row so the
        review stays granular."""
        key = (state, app, title, wclass, labelkey)
        if (self.key == key and self.last_t is not None
                and t - self.last_t <= self.max_gap
                and (self.row_t0 is None or t - self.row_t0 <= self.max_span)):
            self.c.execute("UPDATE obs SET t1=? WHERE id=?", (t, self.rowid))
        else:
            cur = self.c.execute(
                "INSERT INTO obs(t0,t1,state,app,title,wclass,collector)"
                " VALUES(?,?,?,?,?,?,?)",
                (t, t, state, app, title, wclass, self.collector))
            self.rowid = cur.lastrowid
            self.key = key
            self.row_t0 = t
        self.last_t = t
        return self.rowid

    def begin(self, t0, t1, state, app, title, wclass):
        """Start a new interval with an explicit span. Used when idle is
        backdated to the last real input."""
        cur = self.c.execute(
            "INSERT INTO obs(t0,t1,state,app,title,wclass,collector)"
            " VALUES(?,?,?,?,?,?,?)",
            (t0, t1, state, app, title, wclass, self.collector))
        self.rowid = cur.lastrowid
        self.key = (state, app, title, wclass, None)
        self.row_t0 = t0
        self.last_t = t1
        return self.rowid

    def truncate_current(self, t):
        """Pull the open interval's end back, so a backdated idle start never
        overlaps the work that preceded it."""
        if self.rowid is None:
            return
        r = self.c.execute("SELECT t0 FROM obs WHERE id=?", (self.rowid,)).fetchone()
        if r is not None and t >= r["t0"]:
            self.c.execute("UPDATE obs SET t1=? WHERE id=?", (t, self.rowid))

    def close_stale(self):
        self.key = None


def close_open_intervals(c, tick):
    """After a crash or power loss, close anything left open at the last
    heartbeat. Never extrapolate across an outage."""
    hb = meta_get(c, "heartbeat")
    if not hb:
        return 0
    hb = float(hb)
    n = c.execute("UPDATE obs SET t1=? WHERE t1>?", (hb, hb)).rowcount
    c.commit()
    return n


# ---------- clients / projects (stable id, editable name) ----------
def new_id(prefix):
    return "%s_%s" % (prefix, uuid.uuid4().hex[:8])


def ensure_client(c, name):
    r = c.execute("SELECT id FROM clients WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    if r:
        return r["id"]
    cid = new_id("cl")
    c.execute("INSERT INTO clients(id,name,created) VALUES(?,?,?)",
              (cid, name, time.time()))
    return cid


def propose_project(c, name, client_id=None):
    """Create a project candidate from something observed. Status 'proposed'
    until the user confirms. Name is editable; the id never changes."""
    r = c.execute("SELECT id FROM projects WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    if r:
        return r["id"]
    for a in c.execute("SELECT project_id, pattern FROM aliases").fetchall():
        try:
            if re.search(a["pattern"], name, re.I):
                return a["project_id"]
        except re.error:
            pass
    pid = new_id("pj")
    c.execute("INSERT INTO projects(id,name,client_id,status,created)"
              " VALUES(?,?,?,?,?)",
              (pid, name, client_id, "proposed", time.time()))
    c.execute("INSERT INTO aliases(project_id,pattern,kind) VALUES(?,?,?)",
              (pid, re.escape(name), "auto"))
    return pid


def match_project(c, text):
    if not text:
        return None
    for a in c.execute("SELECT project_id, pattern FROM aliases").fetchall():
        try:
            if re.search(a["pattern"], text, re.I):
                return a["project_id"]
        except re.error:
            pass
    return None


def rename_project(c, pid, name):
    old = c.execute("SELECT name FROM projects WHERE id=?", (pid,)).fetchone()
    c.execute("UPDATE projects SET name=? WHERE id=?", (name, pid))
    audit(c, "rename_project:" + pid, old["name"] if old else None, name)


def project_names(c):
    return {r["id"]: r["name"] for r in c.execute("SELECT id,name FROM projects")}


def project_parents(c):
    """child project id -> parent project id, for report roll-up."""
    try:
        return {r["id"]: r["parent_id"] for r in
                c.execute("SELECT id,parent_id FROM projects WHERE parent_id IS NOT NULL")}
    except Exception:
        return {}


def roll_up(pid, parents, depth=4):
    seen = set()
    while pid in parents and parents[pid] and depth > 0:
        if pid in seen:
            break
        seen.add(pid)
        pid = parents[pid]
        depth -= 1
    return pid


# ---------- labels ----------
def put_label(c, obs_id, project_id, stage, doc, confidence, source, reason):
    """Automation never overwrites a human decision."""
    r = c.execute("SELECT source FROM labels WHERE obs_id=?", (obs_id,)).fetchone()
    if r and r["source"] in ("confirmed", "manual", "corrected") and source == "auto":
        return False
    c.execute(
        "INSERT INTO labels(obs_id,project_id,stage,doc,confidence,source,reason,updated)"
        " VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(obs_id) DO UPDATE SET"
        " project_id=excluded.project_id, stage=excluded.stage, doc=excluded.doc,"
        " confidence=excluded.confidence, source=excluded.source,"
        " reason=excluded.reason, updated=excluded.updated",
        (obs_id, project_id, stage, doc, confidence, source, reason, time.time()))
    return True


def audit(c, what, before, after):
    c.execute("INSERT INTO audit(t,what,before,after) VALUES(?,?,?,?)",
              (time.time(), what, json.dumps(before, default=str),
               json.dumps(after, default=str)))


def add_note(c, day, project_id, text):
    c.execute("INSERT INTO notes(day,project_id,text,created) VALUES(?,?,?,?)",
              (day, project_id, text, time.time()))
    c.commit()
