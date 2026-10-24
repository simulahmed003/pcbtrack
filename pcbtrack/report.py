"""Aggregation, the daily review queue, and exports.

Every report separates CONFIRMED from AUTO-GUESSED time. A report that hides
that distinction would be dishonest, and this project exists because the
first version of it was.
"""
import os, csv, json, datetime as dt
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
    tot = conn.execute(
        "SELECT COALESCE(SUM(MIN(o.t1,?)-MAX(o.t0,?)),0) s FROM obs o"
        " WHERE o.state='work' AND o.t1>=? AND o.t0<?",
        (min(t1, _t.time()), t0, t0, t1)).fetchone()["s"]
    return {
        "live": age is not None and age < cfg["tick_seconds"] * 4,
        "heartbeat_age": round(age, 1) if age is not None else None,
        "state": r["state"], "app": r["app"],
        "stage": r["stage"], "doc": r["doc"],
        "project": names.get(r["project_id"], ""),
        "confidence": round(r["confidence"] or 0, 2),
        "reason": r["reason"] or "",
        "since": r["t0"], "work_today_s": max(0.0, tot),
    }


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
        "by_stage": sessionize.rollup(work, stage_of),
        "by_project": {names.get(k, "(unassigned)"): v for k, v in
                       sessionize.rollup(work, proj_of).items()},
        "by_app": sessionize.rollup(work, lambda x: x["app"] or "(none)"),
        "by_doc": sessionize.rollup(work, lambda x: x["doc"]),
        "by_project_doc": {p: dict(sorted(d.items(), key=lambda kv: -kv[1]))
                           for p, d in by_pd.items()},
        "notes": notes,
        "manual": store.manual_between(conn, t0, t1),
        "timeline": [{"t0": x["t0"], "t1": x["t1"], "state": x["state"],
                      "stage": x["stage"], "project": names.get(x["project_id"], ""),
                      "doc": x["doc"], "app": x["app"],
                      "conf": round(x["confidence"], 2), "source": x["source"],
                      "id": x["id"]} for x in iv],
    }


def review_queue(conn, cfg, day, limit=25, now=None):
    """Blocks worth a human glance: unknown stage, no project, or low
    confidence. Biggest first, so two minutes fixes most of the day."""
    iv, _, _ = load_day(conn, cfg, day, now)
    names = store.project_names(conn)
    out = []
    for x in iv:
        if x["state"] != "work" or x["id"] is None:
            continue
        if x["source"] in ("confirmed", "manual"):
            continue
        if x["stage"] == "unknown" or not x["project_id"] or x["confidence"] < REVIEW_CONF:
            out.append({
                "id": x["id"], "t0": x["t0"], "t1": x["t1"], "secs": x["secs"],
                "app": x["app"], "title": x["title"], "doc": x["doc"],
                "stage": x["stage"], "project": names.get(x["project_id"], ""),
                "project_id": x["project_id"], "conf": round(x["confidence"], 2),
            })
    out.sort(key=lambda r: -r["secs"])
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
    if s["notes"]:
        A("")
        A("## What I actually did")
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
    tot = conf = unknown = unassigned = 0.0
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
        "unassigned_s": unassigned,
        "by_project": _sorted(agg["project"]), "by_stage": _sorted(agg["stage"]),
        "by_doc": _sorted(agg["doc"]), "by_app": _sorted(agg["app"]),
        "by_day": dict(sorted(agg["day"].items())),
        "by_project_stage": {p: _sorted(v) for p, v in ps.items()},
        "by_project_doc": {p: _sorted(v) for p, v in pd.items()},
        "notes": notes, "rows": rows,
    }


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
    for p, stages in sorted(r["by_project_stage"].items(),
                            key=lambda kv: -sum(kv[1].values())):
        A("")
        A("## %s - %s" % (p, fmt(sum(stages.values()))))
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
    for title, d in (("By day", r["by_day"]), ("By software", r["by_app"])):
        if d:
            A("")
            A("## %s" % title)
            A("")
            A("| %s | Time |" % title[3:].capitalize())
            A("| --- | --- |")
            for k, v in d.items():
                A("| %s | %s |" % (k, fmt(v)))
    if r["notes"]:
        A("")
        A("## What I actually did")
        A("")
        for n in r["notes"]:
            when = n["day"] + ((" to " + n["day_to"]) if n["day_to"] else "")
            A("- %s%s: %s" % (when, (" (%s)" % n["project"]) if n["project"] else "",
                              n["text"]))
    return "\n".join(L) + "\n"


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
