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
CREATE TABLE IF NOT EXISTS doc_projects(
  doc TEXT PRIMARY KEY COLLATE NOCASE,  -- e.g. ESC_Board.PcbDoc
  project_id TEXT, seen REAL);          -- learned from the .PrjPcb caption
"""


def connect(path):
    """Open the database (WAL mode), create tables and run the small
    in-place migrations older databases need."""
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
    ocols = {r["name"] for r in c.execute("PRAGMA table_info(obs)")}
    if "tools" not in ocols:
        # hand entries and merges list the software used in their window,
        # e.g. "Altium (ESC_Board.PcbDoc), Edge"
        c.execute("ALTER TABLE obs ADD COLUMN tools TEXT")
    lcols = {r["name"] for r in c.execute("PRAGMA table_info(labels)")}
    if "project_guess" not in lcols:
        # 1 = no signal named the project; it was guessed from nearby work and
        # is shown in a reminder colour until the user confirms or changes it
        c.execute("ALTER TABLE labels ADD COLUMN project_guess INTEGER DEFAULT 0")
    ncols = {r["name"] for r in c.execute("PRAGMA table_info(notes)")}
    if "day_to" not in ncols:
        # a note can cover a period ("all week: footprints for the buck stage")
        # and several projects at once (comma-separated ids in project_ids)
        c.execute("ALTER TABLE notes ADD COLUMN day_to TEXT")
        c.execute("ALTER TABLE notes ADD COLUMN project_ids TEXT")
    if "kind" not in {r["name"] for r in c.execute("PRAGMA table_info(notes)")}:
        # 'daily'  - the one note per project per day, edited in place
        # 'period' - a note over several days and/or projects
        c.execute("ALTER TABLE notes ADD COLUMN kind TEXT DEFAULT 'period'")
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
    n = c.execute("UPDATE obs SET t1=? WHERE t1>? AND t0<=?"
                  " AND COALESCE(collector,'') NOT IN ('manual','split','merge','deleted')", (hb, hb, hb)).rowcount
    c.commit()
    return n


# ---------- clients / projects (stable id, editable name) ----------
def new_id(prefix):
    return "%s_%s" % (prefix, uuid.uuid4().hex[:8])


def ensure_client(c, name):
    """Id of the client with this name, created if needed."""
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
def put_label(c, obs_id, project_id, stage, doc, confidence, source, reason,
              guess=0):
    """Automation never overwrites a human decision. A human save clears the
    'guessed project' flag (guess defaults to 0)."""
    r = c.execute("SELECT source FROM labels WHERE obs_id=?", (obs_id,)).fetchone()
    if r and r["source"] in ("confirmed", "manual", "corrected") and source == "auto":
        return False
    c.execute(
        "INSERT INTO labels(obs_id,project_id,stage,doc,confidence,source,reason,updated,"
        "project_guess) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(obs_id) DO UPDATE SET"
        " project_id=excluded.project_id, stage=excluded.stage, doc=excluded.doc,"
        " confidence=excluded.confidence, source=excluded.source,"
        " reason=excluded.reason, updated=excluded.updated,"
        " project_guess=excluded.project_guess",
        (obs_id, project_id, stage, doc, confidence, source, reason, time.time(),
         1 if guess else 0))
    return True


# words too common in project and file names to tie the two together
_GENERIC = {"board", "project", "projects", "main", "test", "design", "copy",
            "final", "new", "pcb", "schematic", "sheet", "rev", "version",
            "microsoft", "edge", "chrome", "google", "altium", "designer",
            "page", "pages", "personal", "home", "untitled", "document"}


def _tokens(s):
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower())
            if len(t) >= 4 and t not in _GENERIC and not t.isdigit()}


def fuzzy_project(c, *texts):
    """A project whose name shares a distinctive word with the window title or
    the open document: "Buck converter" <- Buck_Regulator.PcbDoc. Returns the
    project with the most shared words, or None when no word is shared or two
    projects tie."""
    have = set()
    for t in texts:
        have |= _tokens(t)
    if not have:
        return None
    best, score, tie = None, 0, False
    for r in c.execute("SELECT id,name FROM projects WHERE COALESCE(status,'')<>'closed'"):
        n = len(_tokens(r["name"]) & have)
        if n > score:
            best, score, tie = r["id"], n, False
        elif n and n == score:
            tie = True
    return None if tie else best


def learn_doc_project(c, doc, project_id):
    """Remember which project a document belongs to, learned whenever Altium's
    caption names the .PrjPcb while that document is the active tab."""
    c.execute("INSERT INTO doc_projects(doc,project_id,seen) VALUES(?,?,?)"
              " ON CONFLICT(doc) DO UPDATE SET project_id=excluded.project_id,"
              " seen=excluded.seen", (doc, project_id, time.time()))


def doc_project(c, doc):
    if not doc:
        return None
    r = c.execute("SELECT project_id FROM doc_projects WHERE doc=?", (doc,)).fetchone()
    return r["project_id"] if r else None


def recent_project(c, before=None, apps=None):
    """The project of the latest block a real signal (or the user) named,
    optionally only in the given applications. Used to guess a project when
    nothing on screen says which one."""
    sql = ("SELECT l.project_id FROM labels l JOIN obs o ON o.id=l.obs_id"
           " WHERE l.project_id IS NOT NULL AND COALESCE(l.project_guess,0)=0"
           " AND o.t0<=?")
    args = [before if before is not None else time.time()]
    if apps:
        sql += " AND UPPER(o.app) IN (%s)" % ",".join("?" * len(apps))
        args += [a.upper() for a in apps]
    r = c.execute(sql + " ORDER BY o.t1 DESC LIMIT 1", args).fetchone()
    return r["project_id"] if r else None


def audit(c, what, before, after):
    c.execute("INSERT INTO audit(t,what,before,after) VALUES(?,?,?,?)",
              (time.time(), what, json.dumps(before, default=str),
               json.dumps(after, default=str)))


def add_note(c, day, project_id, text, day_to=None, project_ids=None):
    """day/day_to are ISO dates; project_ids is a list (may be empty)."""
    ids = [p for p in (project_ids or ([project_id] if project_id else [])) if p]
    c.execute("INSERT INTO notes(day,day_to,project_id,project_ids,text,created)"
              " VALUES(?,?,?,?,?,?)",
              (day, day_to if day_to and day_to > day else None,
               ids[0] if ids else None, ",".join(ids) or None, text, time.time()))
    c.commit()


def notes_between(c, d0, d1):
    """Notes whose period overlaps [d0, d1] (ISO date strings, inclusive)."""
    names = project_names(c)
    out = []
    for n in c.execute(
            "SELECT id,day,day_to,project_id,project_ids,text,"
            "       COALESCE(kind,'period') kind FROM notes"
            " WHERE day<=? AND COALESCE(day_to,day)>=? ORDER BY day,created",
            (d1, d0)):
        ids = [p for p in (n["project_ids"] or n["project_id"] or "").split(",") if p]
        out.append({"id": n["id"], "day": n["day"], "day_to": n["day_to"],
                    "project_ids": ids,
                    "projects": [names.get(p, p) for p in ids],
                    "project": ", ".join(names.get(p, p) for p in ids),
                    "text": n["text"], "kind": n["kind"]})
    return out


def set_daily_note(c, day, project_id, text):
    """The one note for (day, project); '' or None project = general note.
    Saving again replaces it; saving empty text removes it."""
    pid = project_id or None
    text = (text or "").strip()
    old = c.execute("SELECT id,text FROM notes WHERE kind='daily' AND day=?"
                    " AND COALESCE(project_id,'')=?", (day, pid or "")).fetchone()
    if old:
        if text:
            c.execute("UPDATE notes SET text=?, created=? WHERE id=?",
                      (text[:4000], time.time(), old["id"]))
        else:
            c.execute("DELETE FROM notes WHERE id=?", (old["id"],))
        audit(c, "daily_note:%s:%s" % (day, pid), old["text"], text)
    elif text:
        c.execute("INSERT INTO notes(day,project_id,project_ids,text,created,kind)"
                  " VALUES(?,?,?,?,?,'daily')", (day, pid, pid, text[:4000], time.time()))
    c.commit()


def daily_notes(c, day):
    """{project_id or '': text} for one day."""
    return {(r["project_id"] or ""): r["text"] for r in c.execute(
        "SELECT project_id,text FROM notes WHERE kind='daily' AND day=?", (day,))}


def create_project(c, name, client=None, parent_id=None, status="active"):
    """A project the user declares up front, before any file is seen."""
    name = name.strip()
    r = c.execute("SELECT id FROM projects WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    if r:
        return r["id"]
    pid = new_id("pj")
    cid = ensure_client(c, client.strip()) if client and client.strip() else None
    c.execute("INSERT INTO projects(id,name,client_id,status,created,parent_id)"
              " VALUES(?,?,?,?,?,?)",
              (pid, name, cid, status, time.time(), parent_id or None))
    c.execute("INSERT INTO aliases(project_id,pattern,kind) VALUES(?,?,?)",
              (pid, re.escape(name), "user"))
    audit(c, "create_project:" + pid, None, name)
    c.commit()
    return pid


def add_manual(c, t0, t1, project_id, stage, text, tools=None):
    """Hand-entered work for a time window: off-PC work (meeting, milling,
    soldering, study on paper), or a MERGE of whatever was tracked in that
    window into one block with one project and stage. It outranks tracked
    time for the same minutes (see sessionize.intervals); blocks crossing the
    window edges are split there. `tools` keeps the software that was used
    in the window, comma-separated."""
    if t1 <= t0:
        raise ValueError("end must be after start")
    cur = c.execute("INSERT INTO obs(t0,t1,state,app,title,wclass,collector,tools)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (t0, t1, "work", "manual", (text or "")[:200], "", "manual",
                     (tools or None)))
    put_label(c, cur.lastrowid, project_id or None, stage or "unknown", None,
              1.0, "manual", "entered by hand")
    audit(c, "manual:%s" % cur.lastrowid, None,
          {"t0": t0, "t1": t1, "project_id": project_id, "stage": stage})
    c.commit()
    return cur.lastrowid


def manual_between(c, t0, t1):
    names = project_names(c)
    return [{"id": r["id"], "t0": r["t0"], "t1": r["t1"], "text": r["title"],
             "tools": r["tools"] or "",
             "stage": r["stage"], "project_id": r["project_id"],
             "project": names.get(r["project_id"], "")}
            for r in c.execute(
                "SELECT o.id,o.t0,o.t1,o.title,o.tools,l.stage,l.project_id FROM obs o"
                " LEFT JOIN labels l ON l.obs_id=o.id"
                " WHERE o.collector='manual' AND o.t1>? AND o.t0<? ORDER BY o.t0",
                (t0, t1))]


def add_split(c, t0, t1, app, title, wclass, project_id, stage, doc, group=""):
    """A piece of tracked time moved to a project by the user. Copies what
    was observed (app, title, document) so it still shows as Altium work."""
    cur = c.execute("INSERT INTO obs(t0,t1,state,app,title,wclass,collector)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (t0, t1, "work", app, title, wclass, "split"))
    put_label(c, cur.lastrowid, project_id or None, stage, doc, 1.0,
              "confirmed", "split by user #%s" % group)
    return cur.lastrowid


def add_deleted(c, t0, t1, what, group):
    """One piece of a delete: hides [t0,t1) everywhere (it counts as not
    tracked). The tracked rows stay underneath, so it can be restored."""
    cur = c.execute("INSERT INTO obs(t0,t1,state,app,title,wclass,collector)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (t0, t1, "work", "deleted", (what or "")[:200], "", "deleted"))
    put_label(c, cur.lastrowid, None, "unknown", None, 1.0, "confirmed",
              "deleted by user #%s" % group)
    return cur.lastrowid


def deleted_between(c, t0, t1):
    """Deletes overlapping [t0,t1), one entry per delete action."""
    groups = {}
    for r in c.execute(
            "SELECT o.id,o.t0,o.t1,o.title,l.reason FROM obs o JOIN labels l ON l.obs_id=o.id"
            " WHERE o.collector='deleted' AND o.t1>? AND o.t0<? ORDER BY o.t0", (t0, t1)):
        g = groups.setdefault(r["reason"], {"ids": [], "t0": r["t0"], "t1": r["t1"],
                                            "secs": 0.0, "what": []})
        g["ids"].append(r["id"])
        g["t0"], g["t1"] = min(g["t0"], r["t0"]), max(g["t1"], r["t1"])
        g["secs"] += r["t1"] - r["t0"]
        if r["title"] and r["title"] not in g["what"]:
            g["what"].append(r["title"])
    return sorted(groups.values(), key=lambda g: g["t0"])


def add_merge(c, t0, t1, project_id, stage, note, tools, group):
    """One piece of a row merge: the user joined several rows into one
    block. Same overlay idea as a split; `tools` lists everything merged."""
    cur = c.execute("INSERT INTO obs(t0,t1,state,app,title,wclass,collector,tools)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (t0, t1, "work", "merged", (note or "")[:200], "", "merge", tools))
    put_label(c, cur.lastrowid, project_id or None, stage or "unknown", None, 1.0,
              "confirmed", "merged by user #%s" % group)
    return cur.lastrowid


def delete_splits(c, ids):
    """Undo a split or a merge: removes only 'split' / 'merge' overlay rows;
    what was tracked underneath shows again. Every piece made by the same
    action goes, so the whole row comes back, not just one piece."""
    n = 0
    groups = {r["reason"] for r in c.execute(
        "SELECT l.reason FROM labels l JOIN obs o ON o.id=l.obs_id"
        " WHERE o.collector IN ('split','merge','deleted') AND o.id IN (%s)"
        % ",".join("?" * len(ids)), list(ids))
        if (r["reason"] or "").split("#")[0] in ("split by user ", "merged by user ",
                                                 "deleted by user ")
        and not (r["reason"] or "").endswith("#")}
    if groups:
        ids = list(ids) + [r["obs_id"] for r in c.execute(
            "SELECT obs_id FROM labels WHERE reason IN (%s)" % ",".join("?" * len(groups)),
            list(groups))]
    for oid in dict.fromkeys(ids):
        r = c.execute("SELECT * FROM obs WHERE id=? AND collector IN ('split','merge','deleted')",
                      (oid,)).fetchone()
        if r:
            audit(c, "delete_split:%s" % oid, dict(r), None)
            c.execute("DELETE FROM labels WHERE obs_id=?", (oid,))
            c.execute("DELETE FROM obs WHERE id=?", (oid,))
            n += 1
    c.commit()
    return n


def delete_manual(c, oid):
    """Only hand-entered rows can be removed; tracked observations are
    immutable."""
    r = c.execute("SELECT * FROM obs WHERE id=? AND collector='manual'", (oid,)).fetchone()
    if not r:
        return False
    audit(c, "delete_manual:%s" % oid, dict(r), None)
    c.execute("DELETE FROM labels WHERE obs_id=?", (oid,))
    c.execute("DELETE FROM obs WHERE id=?", (oid,))
    c.commit()
    return True


# ---------- destructive actions (dashboard "Danger zone") ----------
def backup(c, data_dir, keep=10):
    """Copy the whole database before anything is deleted. Keeps the newest
    `keep` copies in <data dir>/backups. Returns the backup path."""
    d = os.path.join(data_dir, "backups")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "activity-%s.db" % time.strftime("%Y%m%d-%H%M%S"))
    dst = sqlite3.connect(path)
    c.commit()
    c.backup(dst)
    dst.close()
    old = sorted(f for f in os.listdir(d) if f.startswith("activity-") and f.endswith(".db"))
    for f in old[:-keep]:
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass
    return path


def delete_project(c, pid, move_to=None):
    """Remove a project. Its time moves to `move_to`, or becomes unassigned;
    the observed time itself is never deleted here."""
    old = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not old:
        return False
    move_to = move_to if move_to and move_to != pid else None
    c.execute("UPDATE labels SET project_id=?, project_guess=0 WHERE project_id=?", (move_to, pid))
    if move_to:
        c.execute("UPDATE aliases SET project_id=? WHERE project_id=?", (move_to, pid))
        c.execute("UPDATE doc_projects SET project_id=? WHERE project_id=?", (move_to, pid))
    else:
        c.execute("DELETE FROM aliases WHERE project_id=?", (pid,))
        c.execute("DELETE FROM doc_projects WHERE project_id=?", (pid,))
    c.execute("UPDATE projects SET parent_id=NULL WHERE parent_id=?", (pid,))
    for n in c.execute("SELECT id,project_ids FROM notes WHERE project_id=? OR"
                       " ','||COALESCE(project_ids,'')||',' LIKE ?",
                       (pid, "%," + pid + ",%")).fetchall():
        ids = [x for x in (n["project_ids"] or "").split(",") if x and x != pid]
        if move_to and move_to not in ids:
            ids.append(move_to)
        c.execute("UPDATE notes SET project_ids=?, project_id=? WHERE id=?",
                  (",".join(ids) or None, ids[0] if ids else None, n["id"]))
    c.execute("DELETE FROM projects WHERE id=?", (pid,))
    audit(c, "delete_project:" + pid, dict(old), {"time_moved_to": move_to})
    c.commit()
    return True


def delete_client(c, cid):
    """Remove a client; its projects stay, without a client."""
    old = c.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    if not old:
        return False
    c.execute("UPDATE projects SET client_id=NULL WHERE client_id=?", (cid,))
    c.execute("DELETE FROM clients WHERE id=?", (cid,))
    audit(c, "delete_client:" + cid, dict(old), None)
    c.commit()
    return True


def replace_stage(c, stage, to="unknown"):
    """Every block labelled `stage` gets `to` instead; learned rules too."""
    n = c.execute("UPDATE labels SET stage=? WHERE stage=?", (to, stage)).rowcount
    c.execute("UPDATE rules SET value=? WHERE field='stage' AND value=?", (to, stage))
    audit(c, "replace_stage:" + stage, stage, {"to": to, "blocks": n})
    c.commit()
    return n


def delete_range(c, t0, t1):
    """Permanently delete everything recorded between t0 and t1: tracked
    blocks, hand entries, splits, file evidence. Blocks that cross an edge
    are trimmed, not removed."""
    ids = [r["id"] for r in c.execute(
        "SELECT id FROM obs WHERE t0>=? AND t1<=?", (t0, t1))]
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        q = ",".join("?" * len(part))
        c.execute("DELETE FROM labels WHERE obs_id IN (%s)" % q, part)
        c.execute("DELETE FROM obs WHERE id IN (%s)" % q, part)
    c.execute("UPDATE obs SET t1=? WHERE t0<? AND t1>? AND t1<=?", (t0, t0, t0, t1))
    c.execute("UPDATE obs SET t0=? WHERE t0>=? AND t0<? AND t1>?", (t1, t0, t1, t1))
    ev = c.execute("DELETE FROM evidence WHERE t>=? AND t<?", (t0, t1)).rowcount
    audit(c, "delete_range", None, {"t0": t0, "t1": t1, "blocks": len(ids), "evidence": ev})
    c.commit()
    return len(ids)

