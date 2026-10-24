"""Turns raw observations into the day's accounting.

Guarantees (tested in tests/replay_day.py):
  work + idle + locked + off  ==  wall clock of the window, exactly.
Nothing is double counted; a second belongs to one state and one project.
"""
import datetime as dt

STATES = ("work", "idle", "locked", "off")


def day_window(day, cutover=0):
    d0 = dt.datetime.combine(day, dt.time(cutover, 0))
    return d0.timestamp(), (d0 + dt.timedelta(days=1)).timestamp()


def intervals(conn, t0, t1):
    """Deduplicated, non-overlapping intervals clipped to [t0,t1).

    Overlap happens when more than one collector wrote at once; the baseline
    data from 2026-10-22 had 2-4 writers and was inflated up to 4x. The first
    writer for any instant wins, so a duplicate can never add time."""
    rows = conn.execute(
        "SELECT o.id,o.t0,o.t1,o.state,o.app,o.title,o.wclass,"
        "       l.project_id,l.stage,l.doc,l.confidence,l.source"
        "  FROM obs o LEFT JOIN labels l ON l.obs_id=o.id"
        " WHERE o.t1>=? AND o.t0<? ORDER BY o.t0, o.id", (t0, t1)).fetchall()
    out = []
    cursor = t0
    for r in rows:
        a = max(r["t0"], t0, cursor)
        b = min(r["t1"], t1)
        if b <= a:
            continue
        out.append({
            "id": r["id"], "t0": a, "t1": b, "secs": b - a,
            "state": r["state"], "app": r["app"], "title": r["title"],
            "project_id": r["project_id"], "stage": r["stage"], "doc": r["doc"],
            "confidence": r["confidence"] or 0.0, "source": r["source"] or "auto",
        })
        cursor = b
    return out


def with_off(iv, t0, t1, now=None):
    """Fill every uncovered second with 'off' so the day always totals 24h
    (or up to now, for today)."""
    end = min(t1, now) if now else t1
    out = []
    cur = t0
    for x in iv:
        if x["t0"] > cur:
            out.append(_off(cur, min(x["t0"], end)))
        out.append(x)
        cur = max(cur, x["t1"])
    if cur < end:
        out.append(_off(cur, end))
    return [x for x in out if x["secs"] > 0]


def _off(a, b):
    return {"id": None, "t0": a, "t1": b, "secs": b - a, "state": "off",
            "app": "", "title": "", "project_id": None, "stage": "off",
            "doc": None, "confidence": 1.0, "source": "auto"}


def apply_grace(iv, grace):
    """A short idle inside work on the same project stays work: thinking,
    reading a datasheet on paper, talking on the phone. Longer idle splits
    the session."""
    for i, x in enumerate(iv):
        if x["state"] != "idle" or x["secs"] > grace:
            continue
        prev = next((y for y in reversed(iv[:i]) if y["state"] == "work"), None)
        nxt = next((y for y in iv[i + 1:] if y["state"] == "work"), None)
        if prev and nxt and prev["project_id"] and \
                prev["project_id"] == nxt["project_id"]:
            x["state"] = "work"
            x["stage"] = prev["stage"]
            x["project_id"] = prev["project_id"]
            x["source"] = "grace"
    return iv


def rollup(iv, key):
    agg = {}
    for x in iv:
        k = key(x)
        if k is None:
            continue
        agg[k] = agg.get(k, 0.0) + x["secs"]
    return dict(sorted(agg.items(), key=lambda kv: -kv[1]))


def check_invariant(iv, t0, t1, now=None):
    end = min(t1, now) if now else t1
    total = sum(x["secs"] for x in iv)
    return abs(total - (end - t0)) < 1.0, total, end - t0
