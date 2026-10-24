"""Aggregation, the daily review queue, and exports.

Every report separates CONFIRMED from AUTO-GUESSED time. A report that hides
that distinction would be dishonest, and this project exists because the
first version of it was.
"""
import os, csv, json, datetime as dt
from . import sessionize, store, config, classify

REVIEW_CONF = 0.6


def fmt(secs):
    m = int(round(secs / 60.0))
    return ("%dh %02dm" % (m // 60, m % 60)) if m >= 60 else "%dm" % m


def load_day(conn, cfg, day, now=None, backfill=True):
    t0, t1 = sessionize.day_window(day, cfg["day_cutover_hour"])
    if backfill:
        try:
            classify.backfill(conn, cfg, t0, t1)
        except Exception:
            pass
    iv = sessionize.intervals(conn, t0, t1)
    iv = sessionize.with_off(iv, t0, t1, now=now or __import__("time").time())
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
    notes = conn.execute(
        "SELECT project_id,text,created FROM notes WHERE day=? ORDER BY created",
        (day.isoformat(),)).fetchall()
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
        "notes": [{"project": names.get(n["project_id"], ""), "text": n["text"]} for n in notes],
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
            A("- %s%s" % (("**%s** - " % n["project"]) if n["project"] else "", n["text"]))
    return "\n".join(L) + "\n"


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
