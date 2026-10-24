"""Aggregation, the daily review queue, and exports.

Every report separates CONFIRMED from AUTO-GUESSED time. A report that hides
that distinction would be dishonest, and this project exists because the
first version of it was.
"""
import os, re, csv, json, datetime as dt
from . import sessionize, store, config, classify

REVIEW_CONF = 0.6


def fmt(secs):
    if 0 < secs < 59.5:
        return "%ds" % round(secs)      # a quick look at a sheet is not "0m"
    m = int(round(secs / 60.0))
    return ("%dh %02dm" % (m // 60, m % 60)) if m >= 60 else "%dm" % m


def load_day(conn, cfg, day, now=None, backfill=True):
    t0, t1 = sessionize.day_window(day, cfg["day_cutover_hour"])
    now = now or __import__("time").time()
    if backfill:
        try:
            classify.backfill(conn, cfg, t0, t1)
            classify.guess_projects(conn, t0, min(t1, now))
        except Exception:
            pass
    iv = sessionize.intervals(conn, t0, max(t0, min(t1, now)),
                              join_gap=cfg["tick_seconds"] * 2 + 1)
    iv = sessionize.with_off(iv, t0, t1, now=now)
    iv = sessionize.apply_grace(iv, cfg["thinking_grace_seconds"])
    return iv, t0, t1


def now_snapshot(conn, cfg):
    """Tiny payload for the live view - a few hundred bytes, read from the
    last couple of rows rather than a whole-day rebuild."""
    import time as _t
    r = conn.execute(
        "SELECT o.t0,o.t1,o.state,o.app,o.title,l.stage,l.doc,l.project_id,"
        "       l.confidence,l.reason"
        "  FROM obs o LEFT JOIN labels l ON l.obs_id=o.id"
        " ORDER BY o.t1 DESC LIMIT 1").fetchone()
    hb = store.meta_get(conn, "heartbeat")
    names = store.project_names(conn)
    if not r:
        return {"live": False, "heartbeat_age": None}
    age = _t.time() - float(hb) if hb else None
    t0, t1 = sessionize.day_window(dt.date.today(), cfg["day_cutover_hour"])
    cad = [a.upper() for a in cfg.get("cad_processes", [])]
    # same arithmetic as the day view (gap joining, manual entries win), so
    # the live strip and the cards never disagree; one day is a few
    # thousand rows at most
    iv = [x for x in sessionize.intervals(conn, t0, min(t1, _t.time()),
                                          join_gap=cfg["tick_seconds"] * 2 + 1)
          if x["state"] == "work"]
    tot = sum(x["secs"] for x in iv)
    cad_today = sum(x["secs"] for x in iv if (x["app"] or "").upper() in cad)
    lc = conn.execute(
        "SELECT o.t1,o.app,l.stage,l.doc,l.project_id FROM obs o"
        " LEFT JOIN labels l ON l.obs_id=o.id WHERE o.state='work'"
        " AND UPPER(o.app) IN (%s) ORDER BY o.t1 DESC LIMIT 1"
        % ",".join("?" * len(cad)), cad).fetchone() if cad else None
    return {
        "last_cad": {"t": lc["t1"], "app": lc["app"], "stage": lc["stage"],
                     "doc": lc["doc"], "project": names.get(lc["project_id"], ""),
                     "ago_s": round(_t.time() - lc["t1"])} if lc else None,
        "cad_today_s": max(0.0, cad_today),
        "live": age is not None and age < cfg["tick_seconds"] * 4,
        "heartbeat_age": round(age, 1) if age is not None else None,
        "state": r["state"], "app": r["app"],
        "stage": r["stage"], "doc": r["doc"],
        "project": names.get(r["project_id"], ""),
        "confidence": round(r["confidence"] or 0, 2),
        "reason": r["reason"] or "",
        "since": r["t0"], "work_today_s": max(0.0, tot),
    }


EDITOR = {"SCH": "Schematic editor", "PCB": "PCB editor",
          "SCHLIB": "Schematic library", "PCBLIB": "PCB library", "FAB": "Output job"}
_EXT = {"schdoc": "SCH", "pcbdoc": "PCB", "schlib": "SCHLIB", "pcblib": "PCBLIB",
        "intlib": "SCHLIB", "outjob": "FAB", "kicad_sch": "SCH", "kicad_pcb": "PCB",
        "kicad_sym": "SCHLIB", "kicad_mod": "PCBLIB"}
_BROWSER_TAIL = re.compile(
    r"(\s+and \d+ more pages?)?(\s+-\s+(Personal|Work|Profile \d+))?"
    r"\s+-\s+(Microsoft\W*Edge|Google Chrome|Mozilla Firefox|Brave|Opera)\s*$", re.I)


def doctype_of(doc):
    ext = (doc or "").rsplit(".", 1)[-1].lower() if doc and "." in doc else ""
    return _EXT.get(ext)


def detected_of(x, cadset):
    """What was observably on screen - a fact, never edited by the user."""
    app = (x["app"] or "")
    if app == "manual":
        return "Added by hand"
    if app.upper() in cadset:
        reason = x.get("reason") or ""
        if reason.startswith("dialog") and x["title"]:
            return "Dialog: " + x["title"].strip()[:40]
        dt = doctype_of(x["doc"])
        return EDITOR.get(dt, "Altium (no document)" if not x["doc"] else "Altium")
    return re.sub(r"(?i)\.exe$", "", app) or "(unknown)"


def clean_title(title):
    t = (title or "").replace("​", "").strip()
    t = _BROWSER_TAIL.sub("", t)
    return t[:70] or "(no title)"


def detail_rows(xs, cadset, names, proj_of, stage_of, saves=None):
    """Rows of (project, item, detected, stage) with time and block ids, so
    one dropdown can relabel a whole row."""
    rows = {}
    for x in xs:
        cad = (x["app"] or "").upper() in cadset
        item = (x["doc"] or "(no document)") if cad else (
            x["title"] if x["app"] == "manual" else clean_title(x["title"]))
        key = (names.get(proj_of(x), "(unassigned)"), item, detected_of(x, cadset), stage_of(x))
        r = rows.setdefault(key, {"project": key[0], "item": key[1], "detected": key[2],
                                  "stage": key[3], "secs": 0.0, "ids": [],
                                  "confirmed": True, "app": x["app"]})
        r["secs"] += x["secs"]
        r["first"] = min(r.get("first", x["t0"]), x["t0"])
        r["last"] = max(r.get("last", x["t1"]), x["t1"])
        if x["id"] is not None and x["id"] not in r["ids"]:
            r["ids"].append(x["id"])
        if x["source"] not in ("confirmed", "manual", "corrected"):
            r["confirmed"] = False
        if x.get("collector") == "split":
            r["split_ids"] = r.get("split_ids", []) + [x["id"]]
    out = sorted(rows.values(), key=lambda r: (r["project"] == "(unassigned)", r["project"], -r["secs"]))
    if saves is not None:
        for r in out:
            r["saves"] = saves.get((r["item"].rsplit(".", 1)[0].lower(),
                                    doctype_of(r["item"])), 0)
    return out


def split_row(conn, cfg, day, ids, parts):
    """Divide the time of one table row between projects.

    parts: [(project_id, seconds), ...]; the last part takes whatever is left,
    so the row total never changes. Time is handed out in time order: the
    first part gets the earliest minutes. Each piece becomes a 'split'
    overlay that copies the tracked app, document and stage."""
    want = set(ids)
    iv, _, _ = load_day(conn, cfg, day, backfill=False)
    sel = sorted((x for x in iv if x["id"] in want and x["state"] == "work"),
                 key=lambda x: x["t0"])
    if not sel or not parts:
        return 0
    total = sum(x["secs"] for x in sel)
    alloc = [[pid, max(0.0, float(sec))] for pid, sec in parts]
    alloc[-1][1] = max(0.0, total - sum(a[1] for a in alloc[:-1]))
    src = {r["id"]: r for r in conn.execute(
        "SELECT id,app,title,wclass FROM obs WHERE id IN (%s)" % ",".join("?" * len(want)),
        list(want))}
    made = 0
    group = "%d" % (__import__("time").time() * 1000)
    k, left = 0, alloc[0][1]
    for x in sel:
        a = x["t0"]
        while a < x["t1"] - 1e-6 and k < len(alloc):
            if left <= 1e-6:
                k += 1
                if k >= len(alloc):
                    break
                left = alloc[k][1]
                continue
            b = min(x["t1"], a + left)
            o = src.get(x["id"])
            store.add_split(conn, a, b, o["app"] if o else x["app"],
                            o["title"] if o else x["title"], o["wclass"] if o else "",
                            alloc[k][0], x["stage"], x["doc"], group)
            made += 1
            left -= b - a
            a = b
    store.audit(conn, "split_row", list(ids), [list(p) for p in alloc])
    conn.commit()
    return made


def saves_by_doc(conn, t0, t1):
    """Distinct save times per (document stem, doctype) from project folders
    and Altium History; proof of progress, not just an open window."""
    out = {}
    for r in conn.execute(
            "SELECT doc,doctype,COUNT(DISTINCT CAST(t AS INTEGER)) n FROM evidence"
            " WHERE kind IN ('save','history') AND t>=? AND t<? GROUP BY doc,doctype",
            (t0, t1)):
        out[((r["doc"] or "").lower(), r["doctype"])] = r["n"]
    return out


def focus_stats(work, cadset, max_gap=120):
    """Altium focus: share of work time in the design tool, and the longest
    stretch of it where any break was shorter than max_gap seconds."""
    cad = [x for x in work if (x["app"] or "").upper() in cadset]
    best = cur = 0.0
    last_end = None
    for x in cad:
        if last_end is not None and x["t0"] - last_end <= max_gap:
            cur += x["secs"] + max(0.0, x["t0"] - last_end)
        else:
            cur = x["secs"]
        best = max(best, cur)
        last_end = x["t1"]
    tot = sum(x["secs"] for x in work)
    return {"focus_pct": round(100.0 * sum(x["secs"] for x in cad) / tot) if tot else 0,
            "longest_s": best}


def week_totals(conn, cfg, day, now=None):
    cadset = {a.upper() for a in cfg.get("cad_processes", [])}
    start = day - dt.timedelta(days=day.weekday())
    work = cad = 0.0
    d = start
    while d <= day:
        iv, _, _ = load_day(conn, cfg, d, now, backfill=(d == day))
        for x in iv:
            if x["state"] == "work":
                work += x["secs"]
                if (x["app"] or "").upper() in cadset:
                    cad += x["secs"]
        d += dt.timedelta(days=1)
    return {"from": start.isoformat(), "work_s": work, "cad_s": cad}


def summary(conn, cfg, day, now=None):
    iv, t0, t1 = load_day(conn, cfg, day, now)
    names = store.project_names(conn)
    parents = store.project_parents(conn) if cfg.get(
        "roll_up_subprojects_in_report", True) else {}
    work = [x for x in iv if x["state"] == "work"]

    def proj_of(x):
        return store.roll_up(x["project_id"], parents) if parents else x["project_id"]
    by_state = sessionize.rollup(iv, lambda x: x["state"])
    merge = cfg.get("merge_library_stages_in_report")

    def stage_of(x):
        s = x["stage"]
        if merge and s in ("library_symbol", "library_footprint", "component_search"):
            return "library_management"
        return s

    confirmed = sum(x["secs"] for x in work if x["source"] in ("confirmed", "manual", "corrected"))
    total_work = sum(x["secs"] for x in work)
    unknown = sum(x["secs"] for x in work if x["stage"] == "unknown")
    unassigned = sum(x["secs"] for x in work if not x["project_id"])
    guessed = sum(x["secs"] for x in work if x.get("guess"))
    cadset = {a.upper() for a in cfg.get("cad_processes", [])}
    cadw = [x for x in work if (x["app"] or "").upper() in cadset]
    cad_docs = {}
    for x in cadw:
        p = names.get(proj_of(x), "(unassigned)")
        d = cad_docs.setdefault(p, {}).setdefault(x["doc"] or "(no document / dialog)",
                                                   {"secs": 0.0, "stages": {}})
        d["secs"] += x["secs"]
        d["stages"][stage_of(x)] = d["stages"].get(stage_of(x), 0.0) + x["secs"]
    for p in cad_docs:
        cad_docs[p] = dict(sorted(cad_docs[p].items(), key=lambda kv: -kv[1]["secs"]))
    notes = store.notes_between(conn, day.isoformat(), day.isoformat())
    by_pd = {}
    for x in work:
        if x["doc"]:
            p = names.get(proj_of(x), "(unassigned)")
            by_pd.setdefault(p, {})
            by_pd[p][x["doc"]] = by_pd[p].get(x["doc"], 0.0) + x["secs"]
    return {
        "day": day.isoformat(),
        "states": by_state,
        "work_s": total_work,
        "confirmed_s": confirmed,
        "unknown_s": unknown,
        "unassigned_s": unassigned,
        "guessed_s": guessed,
        "cad": {"work_s": sum(x["secs"] for x in cadw),
                "by_stage": sessionize.rollup(cadw, stage_of),
                "by_project": {names.get(k, "(unassigned)"): v for k, v in
                               sessionize.rollup(cadw, proj_of).items()},
                "docs": cad_docs,
                "rows": detail_rows(cadw, cadset, names, proj_of, stage_of,
                                    saves_by_doc(conn, t0, t1)),
                "switches": sum(1 for a, b in zip(cadw, cadw[1:]) if a["doc"] != b["doc"]),
                **focus_stats(work, cadset)},
        "other_rows": detail_rows([x for x in work if (x["app"] or "").upper() not in cadset],
                                  cadset, names, proj_of, stage_of),
        "week": week_totals(conn, cfg, day, now),
        "target_s": float(cfg.get("daily_target_hours", 5)) * 3600,
        "project_dirs": cfg.get("project_dirs", []),
        "by_stage": sessionize.rollup(work, stage_of),
        "by_project": {names.get(k, "(unassigned)"): v for k, v in
                       sessionize.rollup(work, proj_of).items()},
        "by_app": sessionize.rollup(work, lambda x: x["app"] or "(none)"),
        "by_doc": sessionize.rollup(work, lambda x: x["doc"]),
        "by_project_doc": {p: dict(sorted(d.items(), key=lambda kv: -kv[1]))
                           for p, d in by_pd.items()},
        "notes": [n for n in notes if n["kind"] != "daily"],
        "daily_notes": store.daily_notes(conn, day.isoformat()),
        "manual": store.manual_between(conn, t0, t1),
        "timeline": [{"t0": x["t0"], "t1": x["t1"], "state": x["state"],
                      "stage": x["stage"], "project": names.get(x["project_id"], ""),
                      "doc": x["doc"], "app": x["app"],
                      "conf": round(x["confidence"], 2), "source": x["source"],
                      "guess": x.get("guess", 0), "id": x["id"],
                      "cad": (x["app"] or "").upper() in cadset} for x in iv],
    }


def review_queue(conn, cfg, day, limit=60, now=None):
    """Blocks worth a human glance: unknown stage, no project, or low
    confidence. Biggest first, so two minutes fixes most of the day."""
    iv, _, _ = load_day(conn, cfg, day, now)
    names = store.project_names(conn)
    cadset = {a.upper() for a in cfg.get("cad_processes", [])}
    out = []
    for x in iv:
        if x["state"] != "work" or x["id"] is None:
            continue
        if x["source"] in ("confirmed", "manual"):
            continue
        if (x["stage"] == "unknown" or not x["project_id"] or x.get("guess")
                or x["confidence"] < REVIEW_CONF):
            out.append({
                "id": x["id"], "t0": x["t0"], "t1": x["t1"], "secs": x["secs"],
                "app": x["app"], "title": x["title"], "doc": x["doc"],
                "stage": x["stage"], "project": names.get(x["project_id"], ""),
                "project_id": x["project_id"], "conf": round(x["confidence"], 2),
                "guess": x.get("guess", 0),
                "cad": (x["app"] or "").upper() in cadset,
            })
    # design-tool blocks first, then biggest first
    out.sort(key=lambda r: (not r["cad"], -r["secs"]))
    return out[:limit]


def markdown(conn, cfg, day, now=None):
    s = summary(conn, cfg, day, now)
    L = []
    A = L.append
    A("# Work report - %s" % s["day"])
    A("")
    st = s["states"]
    A("Day accounted in full: work %s | idle %s | locked %s | PC off %s" % (
        fmt(st.get("work", 0)), fmt(st.get("idle", 0)),
        fmt(st.get("locked", 0)), fmt(st.get("off", 0))))
    pct = (100.0 * s["confirmed_s"] / s["work_s"]) if s["work_s"] else 0
    A("")
    A("Confirmed by me: %s of %s (%.0f%%). Stage still unknown: %s. "
      "Not assigned to a project: %s." % (
          fmt(s["confirmed_s"]), fmt(s["work_s"]), pct,
          fmt(s["unknown_s"]), fmt(s["unassigned_s"])))
    if s["guessed_s"]:
        A("")
        A("Project guessed automatically (not confirmed): %s." % fmt(s["guessed_s"]))
    if s["cad"]["work_s"]:
        A("")
        A("## Altium / CAD - %s" % fmt(s["cad"]["work_s"]))
        A("")
        A("| Project | Document | Work stage | Time |")
        A("| --- | --- | --- | --- |")
        for p, docs in s["cad"]["docs"].items():
            for d, v in docs.items():
                A("| %s | %s | %s | %s |" % (p, d, ", ".join(v["stages"]), fmt(v["secs"])))
    for title, d in (("By project", s["by_project"]), ("By work stage", s["by_stage"]),
                     ("By software", s["by_app"]), ("By document", s["by_doc"])):
        if not d:
            continue
        A("")
        A("## %s" % title)
        A("")
        A("| %s | Time |" % title.replace("By ", "").capitalize())
        A("| --- | --- |")
        for k, v in d.items():
            A("| %s | %s |" % (k, fmt(v)))
    names = store.project_names(conn)
    dn = s["daily_notes"]
    if dn or s["notes"]:
        A("")
        A("## What I actually did")
        A("")
        for pid, text in sorted(dn.items(), key=lambda kv: (kv[0] == "", names.get(kv[0], ""))):
            A("**%s**" % (names.get(pid, pid) if pid else "General"))
            A("")
            A(text)
            A("")
        for n in s["notes"]:
            period = (" (%s to %s)" % (n["day"], n["day_to"])) if n["day_to"] else ""
            A("- %s%s%s" % (("**%s** - " % n["project"]) if n["project"] else "",
                            n["text"], period))
    return "\n".join(L) + "\n"


def _add(d, k, v):
    d[k] = d.get(k, 0.0) + v


def _sorted(d):
    return dict(sorted(d.items(), key=lambda kv: -kv[1]))


def range_summary(conn, cfg, d0, d1, project_ids=None, now=None):
    """Totals for an inclusive date range, optionally for chosen projects only.
    A chosen parent project also takes its sub-projects."""
    if d1 < d0:
        d0, d1 = d1, d0
    names = store.project_names(conn)
    parents = store.project_parents(conn) if cfg.get(
        "roll_up_subprojects_in_report", True) else {}
    want = set(project_ids or [])
    merge = cfg.get("merge_library_stages_in_report")
    allp = store.project_parents(conn)

    def keep(pid):
        if not want:
            return True
        return pid in want or store.roll_up(pid, allp) in want

    def proj(x):
        pid = store.roll_up(x["project_id"], parents) if parents else x["project_id"]
        return names.get(pid, "(unassigned)")

    def stage(x):
        s = x["stage"]
        if merge and s in ("library_symbol", "library_footprint", "component_search"):
            return "library_management"
        return s

    agg = {k: {} for k in ("project", "stage", "doc", "app", "day")}
    ps, pd = {}, {}
    rows = []
    tot = conf = unknown = unassigned = guessed = 0.0
    day = d0
    while day <= d1:
        iv, _, _ = load_day(conn, cfg, day, now)
        for x in iv:
            if x["state"] != "work" or not keep(x["project_id"]):
                continue
            s = x["secs"]
            tot += s
            if x["source"] in ("confirmed", "manual", "corrected"):
                conf += s
            if x["stage"] == "unknown":
                unknown += s
            if not x["project_id"]:
                unassigned += s
            if x.get("guess"):
                guessed += s
            p, st = proj(x), stage(x)
            _add(agg["project"], p, s)
            _add(agg["stage"], st, s)
            _add(agg["app"], x["app"] or "(none)", s)
            _add(agg["day"], day.isoformat(), s)
            if x["doc"]:
                _add(agg["doc"], x["doc"], s)
                _add(pd.setdefault(p, {}), x["doc"], s)
            _add(ps.setdefault(p, {}), st, s)
            rows.append({"day": day.isoformat(), "t0": x["t0"], "t1": x["t1"],
                         "project": p, "stage": st, "doc": x["doc"] or "",
                         "app": x["app"] or "", "source": x["source"],
                         "text": x["title"] if x["app"] == "manual" else ""})
        day += dt.timedelta(days=1)

    notes = [n for n in store.notes_between(conn, d0.isoformat(), d1.isoformat())
             if not want or not n["project_ids"] or set(n["project_ids"]) & want]
    return {
        "from": d0.isoformat(), "to": d1.isoformat(),
        "projects_filter": [names.get(p, p) for p in want],
        "work_s": tot, "confirmed_s": conf, "unknown_s": unknown,
        "unassigned_s": unassigned, "guessed_s": guessed,
        "by_project": _sorted(agg["project"]), "by_stage": _sorted(agg["stage"]),
        "by_doc": _sorted(agg["doc"]), "by_app": _sorted(agg["app"]),
        "by_day": dict(sorted(agg["day"].items())),
        "by_project_stage": {p: _sorted(v) for p, v in ps.items()},
        "by_project_doc": {p: _sorted(v) for p, v in pd.items()},
        "notes": notes, "rows": rows,
    }


AI_PROMPT = (
    "Below is a local work-time report from pcbtrack for a PCB designer. Times "
    "marked confirmed were checked by the designer; the rest are automatic "
    "guesses. Please (1) summarise where the time went per project and work "
    "stage, (2) point out patterns that cost time (fragmented sessions, long "
    "library or component-search time, rework), and (3) suggest three concrete "
    "changes for next week. Be brief.\n\n")


def range_markdown(r):
    L = []
    A = L.append
    A("# Work report %s to %s" % (r["from"], r["to"]))
    if r["projects_filter"]:
        A("")
        A("Projects: %s" % ", ".join(r["projects_filter"]))
    pct = (100.0 * r["confirmed_s"] / r["work_s"]) if r["work_s"] else 0
    A("")
    A("Total work: **%s**. Confirmed or entered by me: %s (%.0f%%). "
      "Stage unknown: %s. Not assigned to a project: %s." % (
          fmt(r["work_s"]), fmt(r["confirmed_s"]), pct,
          fmt(r["unknown_s"]), fmt(r["unassigned_s"])))
    if r["guessed_s"]:
        A("")
        A("Project guessed automatically (not confirmed): %s." % fmt(r["guessed_s"]))
    sections = dict(r["by_project_stage"])
    # a project with notes but no tracked time in the period still gets a section
    for n in r["notes"]:
        for p in n["projects"]:
            if p not in sections and (not r["projects_filter"] or p in r["projects_filter"]):
                sections[p] = {}
    r = dict(r, by_project_stage=sections)
    for p, stages in sorted(sections.items(), key=lambda kv: -sum(kv[1].values())):
        A("")
        A("## %s - %s" % (p, fmt(sum(stages.values()))))
        if stages:
            A("")
            A("| Work stage | Time |")
            A("| --- | --- |")
        for k, v in stages.items():
            A("| %s | %s |" % (k, fmt(v)))
        docs = r["by_project_doc"].get(p)
        if docs:
            A("")
            A("| Document | Time |")
            A("| --- | --- |")
            for k, v in docs.items():
                A("| %s | %s |" % (k, fmt(v)))
        _notes_md(A, [n for n in r["notes"] if p in n["projects"]])
    for title, d in (("By day", r["by_day"]), ("By software", r["by_app"])):
        if d:
            A("")
            A("## %s" % title)
            A("")
            A("| %s | Time |" % title[3:].capitalize())
            A("| --- | --- |")
            for k, v in d.items():
                A("| %s | %s |" % (k, fmt(v)))
    shown = set(r["by_project_stage"])
    rest = [n for n in r["notes"] if not n["projects"] or not (set(n["projects"]) & shown)]
    if rest:
        A("")
        A("## Other notes")
        _notes_md(A, rest, heading=False)
    return "\n".join(L) + "\n"


def _notes_md(A, notes, heading=True):
    """Notes in date order: '- 2026-10-24: text' (multi-line text indented)."""
    if not notes:
        return
    A("")
    if heading:
        A("**What I did**")
        A("")
    for n in notes:
        when = n["day"] + ((" to " + n["day_to"]) if n["day_to"] else "")
        extra = "" if heading or not n["project"] else " (%s)" % n["project"]
        lines = (n["text"] or "").splitlines() or [""]
        A("- %s%s: %s" % (when, extra, lines[0]))
        for ln in lines[1:]:
            A("  " + ln)


def range_zip(conn, cfg, d0, d1, project_ids=None):
    """One Markdown report per project (plus an all-projects one), zipped."""
    import io, zipfile
    names = store.project_names(conn)
    ids = project_ids or list(names)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("all_projects.md",
                   range_markdown(range_summary(conn, cfg, d0, d1, project_ids)))
        for pid in ids:
            r = range_summary(conn, cfg, d0, d1, [pid])
            if r["work_s"] or r["notes"]:
                safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", names.get(pid, pid)).strip("_") or pid
                z.writestr("%s.md" % safe, range_markdown(r))
    return buf.getvalue()


def range_csv(r, detail=False):
    import io
    f = io.StringIO()
    w = csv.writer(f)
    if detail:
        w.writerow(["date", "start", "end", "minutes", "project", "stage",
                    "document", "software", "label_source", "note"])
        for x in r["rows"]:
            w.writerow([x["day"],
                        dt.datetime.fromtimestamp(x["t0"]).strftime("%H:%M:%S"),
                        dt.datetime.fromtimestamp(x["t1"]).strftime("%H:%M:%S"),
                        round((x["t1"] - x["t0"]) / 60.0, 2), x["project"],
                        x["stage"], x["doc"], x["app"], x["source"], x["text"]])
    else:
        w.writerow(["project", "stage", "hours", "minutes"])
        for p, stages in r["by_project_stage"].items():
            for k, v in stages.items():
                w.writerow([p, k, round(v / 3600.0, 2), round(v / 60.0, 1)])
        w.writerow([])
        w.writerow(["project", "document", "hours", "minutes"])
        for p, docs in r["by_project_doc"].items():
            for k, v in docs.items():
                w.writerow([p, k, round(v / 3600.0, 2), round(v / 60.0, 1)])
    return "﻿" + f.getvalue()


def export(conn, cfg, day, outdir=None, now=None):
    outdir = outdir or os.path.join(cfg["_data_dir"], "reports")
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, "day_%s" % day.isoformat())
    s = summary(conn, cfg, day, now)
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(markdown(conn, cfg, day, now))
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1)
    with open(base + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["start", "end", "minutes", "state", "project", "stage",
                    "document", "software", "confidence", "label_source"])
        for x in s["timeline"]:
            w.writerow([
                dt.datetime.fromtimestamp(x["t0"]).isoformat(timespec="seconds"),
                dt.datetime.fromtimestamp(x["t1"]).isoformat(timespec="seconds"),
                round((x["t1"] - x["t0"]) / 60.0, 2), x["state"], x["project"],
                x["stage"], x["doc"] or "", x["app"], x["conf"], x["source"]])
    return base
