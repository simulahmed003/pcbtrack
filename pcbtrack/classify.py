"""Project + work-stage inference.

The stage is always a RECOMMENDATION with a confidence and a reason.
It is never presented as fact: the daily review is where it becomes
confirmed, and a human label is never overwritten by automation.

Signal ladder, strongest first:
  1. a confirmed/manual label           (enforced in store.put_label)
  2. a learned correction rule
  3. an Altium dialog in the foreground (what you are doing TO the document)
  4. the ACTIVE DOCUMENT read from Altium's child windows (pcbtrack/altium.py)
     - names the document and its type, and sees viewing, not just editing
  5. a document extension visible in the window title
  6. Altium Auto Save / History file evidence  -> doctype (proves editing)
  7. app / domain rules (LCSC, PDF, Zoom, Excel, ...)
  8. sticky carry-over from the previous known activity
  9. unknown -> review queue, never silently assigned
"""
import re, time
from . import rules_default as RD
from . import store

PRIVATE = "(private)"


class Classifier:
    def __init__(self, cfg, conn):
        self.cfg = cfg
        self.c = conn
        self.priv = [re.compile(p) for p in cfg["private_title_patterns"]]
        self.dialogs = [(re.compile(p), s, k, v) for p, s, k, v in RD.DIALOGS]
        self.apps = [(re.compile(p), s, k) for p, s, k in RD.APPS]
        self.titledoc = [(re.compile(p), d) for p, d in RD.TITLE_DOC]
        self.projpat = [re.compile(p, re.I) for p in RD.PROJECT_IN_TITLE]
        self.doc2stage = cfg["doctype_stage"]
        self.altium_procs = {a.lower() for a in cfg["altium"]["processes"]}
        self.main_class = cfg["altium"]["main_window_class"].lower()
        self.sticky = None          # (project_id, stage, t, app)
        self.last_project = None    # last project a real signal named
        self.altium_project = None  # .PrjPcb last seen in Altium's caption
        self._docmap = {}           # doc name (lower) -> project id
        self.reload_rules()

    def reload_rules(self):
        self.learned = []
        for r in self.c.execute("SELECT match,field,value FROM rules").fetchall():
            try:
                self.learned.append((re.compile(r["match"], re.I), r["field"], r["value"]))
            except re.error:
                pass

    # ---------- helpers ----------
    def is_private(self, title):
        return any(p.search(title or "") for p in self.priv)

    def project_from_title(self, title):
        for rx in self.projpat:
            m = rx.search(title or "")
            if m:
                return m.group(1)
        return None

    def doc_from_title(self, title):
        for rx, dt in self.titledoc:
            m = rx.search(title or "")
            if m:
                return m.group(1), dt
        return None, None

    def recent_evidence(self, t, window):
        """Most recent Altium Auto Save / save evidence just before t."""
        r = self.c.execute(
            "SELECT doc,doctype,kind,t FROM evidence WHERE t<=? AND t>=?"
            " ORDER BY t DESC LIMIT 1", (t + window, t - window)).fetchone()
        return r

    # ---------- main ----------
    def label(self, t, app, title, wclass, state, sample=None):
        """-> dict(project_id, stage, doc, confidence, source, reason)"""
        out = {"project_id": None, "stage": None, "doc": None,
               "confidence": 0.0, "source": "auto", "reason": "",
               "project_guess": 0}
        if state != "work":
            out["stage"] = state
            out["confidence"] = 1.0
            out["reason"] = "state=" + state
            return out

        shown = PRIVATE if self.is_private(title) else (title or "")
        appl = (app or "").lower()
        hay = "%s | %s" % (app or "", shown)

        # 2. learned corrections
        for rx, field, value in self.learned:
            if rx.search(hay):
                if field == "stage":
                    out.update(stage=value, confidence=0.9, source="corrected",
                               reason="learned rule")
                elif field == "project":
                    out["project_id"] = value
                    out["reason"] = "learned rule"

        # --- project ---
        pid = out["project_id"]
        if not pid:
            name = self.project_from_title(shown)
            if name:
                pid = store.propose_project(self.c, name)
                out["reason"] = (out["reason"] + " title-project").strip()
        if appl in self.altium_procs and shown != PRIVATE:
            adoc = getattr(sample, "doc", None) or self.doc_from_title(shown)[0]
            if pid:
                self.altium_project = pid
                if adoc and self._docmap.get(adoc.lower()) != pid:
                    store.learn_doc_project(self.c, adoc, pid)
                    self._docmap[adoc.lower()] = pid
            else:
                # The caption shows a document, not the project: use the
                # project that document was last seen under, else the project
                # already open in this Altium session.
                known = self._docmap.get((adoc or "").lower()) or \
                    store.doc_project(self.c, adoc)
                if known:
                    pid = known
                    out["reason"] = (out["reason"] + " doc-project").strip()
                else:
                    if self.altium_project is None:
                        self.altium_project = store.recent_project(
                            self.c, t, apps=self.altium_procs) or ""
                    if self.altium_project:
                        pid = self.altium_project
                        out["reason"] = (out["reason"] + " altium-session-project").strip()
        if not pid:
            pid = store.match_project(self.c, shown)
        if not pid and sample is not None and getattr(sample, "doc", None):
            pid = store.match_project(self.c, sample.doc)
        if not pid and shown != PRIVATE:
            # "Buck converter" project <- Buck_Regulator.PcbDoc in front
            pid = store.fuzzy_project(self.c, shown, getattr(sample, "doc", None))
            if pid:
                out["reason"] = (out["reason"] + " name-match").strip()

        # --- stage ---
        if is_dialog_pre(wclass, self.main_class) and is_altium_pre(appl, self.altium_procs):
            for rx, stg, conf, ver in self.dialogs:
                if rx.search(shown):
                    # The dialog names the activity; the document underneath it
                    # is still known, so keep it.
                    out.update(stage=stg, confidence=conf,
                               doc=getattr(sample, "doc", None),
                               reason="dialog %r [%s]" % (shown[:40], ver))
                    break
        if not out["stage"]:
            is_altium = appl in self.altium_procs
            is_dialog = bool(wclass) and wclass.lower() != self.main_class

            # 2.5 THE ACTIVE DOCUMENT, read straight out of Altium's child
            #     windows (pcbtrack/altium.py). This is the strongest automatic
            #     signal: it names the open document and its type, and unlike
            #     Auto Save it also sees plain viewing. A dialog still wins,
            #     because a dialog says what you are doing to that document.
            if sample is not None and getattr(sample, "doctype", None) \
                    and not is_dialog:
                st = self.doc2stage.get(sample.doctype)
                if st:
                    out.update(stage=st, doc=sample.doc, confidence=0.92,
                               reason="active document %s [%s]" % (
                                   sample.doc or sample.doctype,
                                   sample.docsrc or "child window"))

            # 3. a document extension visible in the title
            if not out["stage"]:
                doc, dt = self.doc_from_title(shown)
                if dt:
                    out.update(stage=self.doc2stage.get(dt), doc=doc,
                               confidence=0.75, reason="title doc " + doc)
            # 4. Altium Auto Save / History evidence - this is what rescues
            #    the bare "<project>.PrjPcb" title that reveals nothing
            if not out["stage"] and is_altium:
                ev = self.recent_evidence(t, self.cfg["sticky_minutes"] * 60)
                if ev:
                    st = self.doc2stage.get(ev["doctype"])
                    if st:
                        out.update(stage=st, doc=ev["doc"], confidence=0.8,
                                   reason="autosave/%s %s%s" % (
                                       ev["kind"], ev["doc"], _ext(ev["doctype"])))
            # 5. any other caption that matches a known dialog
            if not out["stage"]:
                for rx, stg, conf, ver in self.dialogs:
                    if rx.search(shown):
                        out.update(stage=stg, confidence=conf * 0.8,
                                   reason="caption %r" % shown[:40])
                        break
            # 6. app / domain rules
            if not out["stage"]:
                for rx, stg, conf in self.apps:
                    if rx.search(hay):
                        out.update(stage=stg, confidence=conf, reason="app rule")
                        break
            # 7. sticky carry-over - only inside the SAME application (an
            #    untitled Altium dialog keeps Altium's stage). A browser or a
            #    chat window never inherits "routing": that labelled 7 minutes
            #    of chatting as PCB work on 2026-10-24.
            if not out["stage"] and self.sticky:
                sp, ss, stt, sapp = self.sticky
                if t - stt <= self.cfg["sticky_minutes"] * 60 and sapp == appl:
                    out.update(stage=ss, confidence=0.35,
                               reason="carried from previous activity")
                    pid = pid or sp
            # 8. give up honestly
            if not out["stage"]:
                out.update(stage="unknown", confidence=0.0,
                           reason="no signal - needs review")

        out["project_id"] = pid
        if not pid and out["stage"] not in (None, "unknown"):
            if self.sticky and t - self.sticky[2] <= self.cfg["sticky_minutes"] * 60:
                out["project_id"] = self.sticky[0]
                out["project_guess"] = 1
                out["reason"] += " +carried project"
        if out["project_id"] and out["stage"] not in ("unknown", None):
            self.sticky = (out["project_id"], out["stage"], t, appl)
        if out["project_id"]:
            if not out["project_guess"]:
                self.last_project = out["project_id"]
        elif shown != PRIVATE:
            # 9. Nothing on screen names a project: guess the one you last
            #    worked on, flagged so the dashboard shows it in a reminder
            #    colour. If you never change it, it stays as recorded.
            if self.last_project is None:
                self.last_project = store.recent_project(self.c, t)
            if self.last_project:
                out["project_id"] = self.last_project
                out["project_guess"] = 1
                out["reason"] += " +guessed project (last worked on)"
        return out


def is_dialog_pre(wclass, main_class):
    return bool(wclass) and wclass.lower() != main_class


def is_altium_pre(appl, procs):
    return appl in procs


def _ext(dt):
    return {"SCH": " (.SchDoc)", "PCB": " (.PcbDoc)",
            "SCHLIB": " (.SchLib)", "PCBLIB": " (.PcbLib)"}.get(dt, "")


def learn(conn, match, field, value, scope="global"):
    conn.execute("INSERT INTO rules(match,field,value,scope,created)"
                 " VALUES(?,?,?,?,?)", (match, field, value, scope, time.time()))
    conn.commit()


def guess_projects(conn, t0, t1):
    """Give every unassigned automatic work block in [t0,t1) a project: the
    nearest block in time whose project was named by a real signal or by the
    user, else the last such project before the window. Flagged
    project_guess=1 so it shows in a reminder colour; a human label is never
    touched, and private titles are left alone."""
    rows = conn.execute(
        "SELECT o.id,o.t0,o.t1,o.title,l.project_id,l.source,"
        "       COALESCE(l.project_guess,0) g"
        "  FROM obs o JOIN labels l ON l.obs_id=o.id"
        " WHERE o.state='work' AND o.t1>=? AND o.t0<? ORDER BY o.t0", (t0, t1)).fetchall()
    known = [(r["t0"], r["t1"], r["project_id"]) for r in rows
             if r["project_id"] and not r["g"]]
    fallback = None
    n = 0
    for r in rows:
        if r["project_id"] or r["source"] != "auto" or r["title"] == PRIVATE:
            continue
        best, dist = None, None
        for a, b, p in known:
            d = r["t0"] - b if b <= r["t0"] else (a - r["t1"] if a >= r["t1"] else 0)
            if dist is None or d < dist:
                best, dist = p, d
        if not best:
            if fallback is None:
                fallback = store.recent_project(conn, t0) or ""
            best = fallback or None
        if not best:
            continue
        conn.execute("UPDATE labels SET project_id=?, project_guess=1,"
                     " reason=COALESCE(reason,'')||' +guessed project (nearest work)'"
                     " WHERE obs_id=? AND source='auto' AND project_id IS NULL",
                     (best, r["id"]))
        n += 1
    if n:
        conn.commit()
    return n


def backfill(conn, cfg, t0, t1):
    """Retroactively label the start of a work session.

    Live, the order of events is: you open a schematic and work for five
    minutes, THEN Altium writes its first Auto Save copy. So the first
    segments of a session are labelled before any evidence exists and come
    out as low-confidence carry-over or unknown. Once the evidence lands,
    those earlier segments can be filled in.

    Only auto labels below 0.5 confidence are touched, and only inside the
    same contiguous run of the same application and project. A human label is
    never changed.
    """
    rows = conn.execute(
        "SELECT o.id,o.t0,o.t1,o.app,l.project_id,l.stage,l.doc,l.confidence,l.source"
        "  FROM obs o JOIN labels l ON l.obs_id=o.id"
        " WHERE o.state='work' AND o.t1>=? AND o.t0<? ORDER BY o.t0", (t0, t1)).fetchall()
    reach = cfg.get("sticky_minutes", 10) * 60
    fixed = 0
    for i, r in enumerate(rows):
        if r["source"] != "auto" or (r["confidence"] or 0) >= 0.5:
            continue
        donor = None
        for j in range(i + 1, len(rows)):
            n = rows[j]
            if n["t0"] - r["t1"] > reach:
                break
            if (n["app"] or "") != (r["app"] or ""):
                break
            if (n["confidence"] or 0) >= 0.7 and n["stage"] not in (None, "unknown"):
                donor = n
                break
        if not donor:
            continue
        conn.execute(
            "UPDATE labels SET project_id=COALESCE(?,project_id), stage=?, doc=?,"
            " confidence=?, source='auto', reason=? WHERE obs_id=? AND source='auto'",
            (donor["project_id"], donor["stage"], donor["doc"],
             min(0.65, (donor["confidence"] or 0.7) - 0.1),
             "backfilled from %s at %s" % (donor["doc"] or donor["stage"],
                                           int(donor["t0"])), r["id"]))
        fixed += 1
    if fixed:
        conn.commit()
    return fixed
