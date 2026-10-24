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


def _row(r, a, b):
    return {
        "id": r["id"], "t0": a, "t1": b, "secs": b - a,
        "state": r["state"], "app": r["app"], "title": r["title"],
        "project_id": r["project_id"], "stage": r["stage"], "doc": r["doc"],
        "confidence": r["confidence"] or 0.0, "source": r["source"] or "auto",
        "guess": r["project_guess"] or 0,
    }


def intervals(conn, t0, t1, join_gap=11.0):
    """Deduplicated, non-overlapping intervals clipped to [t0,t1).

    Overlap happens when more than one collector wrote at once; the baseline
    data from 2026-10-22 had 2-4 writers and was inflated up to 4x. The first
    writer for any instant wins, so a duplicate can never add time.

    A tracked row stores the time of its first and last SAMPLE, so a block
    seen on one tick has t0 == t1 and the tick before the next block is
    missing. Each row is therefore stretched to the next row's start when
    the gap is no more than about two ticks (join_gap). Without this, a short
    look at a schematic counted 0 s and never showed up (fixed 2026-10-24).
    A longer gap is a real outage and stays uncovered.

    Hand-entered rows (collector 'manual') beat tracked time: "14:00-16:00
    studying" replaces whatever the tracker guessed for those minutes."""
    rows = conn.execute(
        "SELECT o.id,o.t0,o.t1,o.state,o.app,o.title,o.wclass,o.collector,"
        "       l.project_id,l.stage,l.doc,l.confidence,l.source,"
        "       COALESCE(l.project_guess,0) project_guess"
        "  FROM obs o LEFT JOIN labels l ON l.obs_id=o.id"
        " WHERE o.t1>=? AND o.t0<? ORDER BY o.t0, o.id",
        (t0 - join_gap, t1)).fetchall()
    manual = [r for r in rows if r["collector"] == "manual"]
    auto = [r for r in rows if r["collector"] != "manual"]

    out = []
    cursor = t0
    for i, r in enumerate(auto):
        end = r["t1"]
        nxt = auto[i + 1]["t0"] if i + 1 < len(auto) else None
        if nxt is not None and end <= nxt <= end + join_gap:
            end = nxt
        a = max(r["t0"], t0, cursor)
        b = min(end, t1)
        if b <= a:
            continue
        out.append(_row(r, a, b))
        cursor = b
    if not manual:
        return out

    spans = []
    mcur = t0
    for r in manual:
        a, b = max(r["t0"], t0, mcur), min(r["t1"], t1)
        if b > a:
            spans.append(_row(r, a, b))
            mcur = b
    for m in spans:
        cut = []
        for x in out:
            if x["t1"] <= m["t0"] or x["t0"] >= m["t1"]:
                cut.append(x)
                continue
            if x["t0"] < m["t0"]:
                cut.append(dict(x, t1=m["t0"], secs=m["t0"] - x["t0"]))
            if x["t1"] > m["t1"]:
                cut.append(dict(x, t0=m["t1"], secs=x["t1"] - m["t1"]))
        out = cut
    out.extend(spans)
    out.sort(key=lambda x: x["t0"])
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
            "doc": None, "confidence": 1.0, "source": "auto", "guess": 0}


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
            x["guess"] = prev.get("guess", 0)
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
