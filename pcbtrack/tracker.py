"""The tracking loop.

Hard rules it enforces (see docs/01-requirements.md):
  R1 one writer only - a second instance exits instead of double counting
  R2 one state and at most one project per second
  R4 idle is backdated to the last real input
  R6 locked/asleep/off are gaps, never work
  R7 heartbeat every tick; on restart, open intervals are closed at the
     last heartbeat - time is never invented across an outage
"""
import os, sys, time, uuid, socket, errno
from . import config, store, signals, sessionize
from .classify import Classifier


class Lock:
    """Single instance. A TCP bind on loopback is atomic, needs no cleanup
    after a crash, and works the same on every OS."""

    def __init__(self, port):
        self.port = port
        self.s = None

    def acquire(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.s.bind(("127.0.0.1", self.port))
            self.s.listen(1)
            return True
        except OSError as e:
            if e.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", 10048)):
                return False
            raise

    def release(self):
        if self.s:
            self.s.close()


def run(cfg=None, probe=None, max_ticks=None, quiet=False):
    cfg = cfg or config.load()
    tick = cfg["tick_seconds"]
    idle_after = cfg["idle_seconds"]
    lock = Lock(cfg["port"] + 1)
    if not lock.acquire():
        sys.stderr.write(
            "pcbtrack is already tracking (lock port %d busy). Nothing started.\n"
            % (cfg["port"] + 1))
        return 1
    conn = store.connect(store.db_path(cfg))
    collector = uuid.uuid4().hex[:8]
    closed = store.close_open_intervals(conn, tick)
    if closed and not quiet:
        print("recovered: closed %d interval(s) left open by a previous run" % closed)
    live = probe is None
    probe = probe or __import__("pcbtrack.sysmon", fromlist=["x"]).get_probe()
    cl = Classifier(cfg, conn)
    w = store.ObsWriter(conn, collector, tick * 3,
                        max_span=cfg.get("max_interval_seconds", 600))
    last_scan = 0.0
    prev_state = None
    prev_t = None
    prev_idle = 0.0
    scan_since = float(store.meta_get(conn, "scan_since") or (time.time() - 3600))
    n = 0
    if not quiet:
        print("pcbtrack %s tracking every %ds -> %s"
              % (__import__("pcbtrack").__version__, tick, store.db_path(cfg)))
    try:
        while max_ticks is None or n < max_ticks:
            n += 1
            loop_t = time.time()
            try:
                s = probe(tick)
                if s is None:
                    break
                t = s.t

                # ---- file evidence (cheap scandir, every scan_seconds) ----
                if t - last_scan >= cfg["scan_seconds"]:
                    try:
                        signals.collect(cfg, conn, scan_since)
                        scan_since = t - 5
                        store.meta_set(conn, "scan_since", scan_since)
                    except Exception as e:
                        if not quiet:
                            sys.stderr.write("scan: %s\n" % e)
                    last_scan = t

                # ---- state ----
                if s.locked:
                    state, app, title, wclass = "locked", "", "", ""
                elif s.idle >= idle_after:
                    state, app, title, wclass = "idle", "", "", ""
                else:
                    state = "work"
                    app, title, wclass = s.app, s.title, s.wclass
                    if cl.is_private(title):
                        title = "(private)"

                # ---- R4: backdate the idle start to the last real input ----
                # Two independent estimates of when input last happened:
                #   this tick:      t - s.idle
                #   previous tick:  prev_t - prev_idle
                # With a healthy counter they agree. GetLastInputInfo's tick
                # "is not guaranteed to be incremental" (Microsoft), so when
                # they disagree take the LATER one: backdating must never
                # reach back over activity we actually observed.
                lab = cl.label(t, s.app, title, wclass, state)
                lkey = (lab["project_id"], lab["stage"], lab["doc"])

                if state == "idle" and prev_state != "idle":
                    est = t - min(s.idle, 86400)
                    if prev_t is not None and prev_state == "work":
                        est = max(est, prev_t - min(prev_idle, 86400))
                    idle_start = min(max(est, 0.0), t)
                    w.truncate_current(idle_start)
                    oid = w.begin(idle_start, t, state, app, title, wclass)
                else:
                    oid = w.add(t, state, app, title, wclass, lkey)
                prev_state, prev_t, prev_idle = state, t, s.idle
                store.put_label(conn, oid, lab["project_id"], lab["stage"],
                                lab["doc"], lab["confidence"], lab["source"],
                                lab["reason"])
                store.meta_set(conn, "heartbeat", t)
                store.meta_set(conn, "collector", collector)
                conn.commit()
            except Exception as e:
                sys.stderr.write("tick error: %s\n" % e)
            if live:
                time.sleep(max(0.0, tick - (time.time() - loop_t)))
    except KeyboardInterrupt:
        if not quiet:
            print("\nstopped")
    finally:
        conn.commit()
        conn.close()
        lock.release()
    return 0


def status(cfg=None):
    cfg = cfg or config.load()
    conn = store.connect(store.db_path(cfg))
    hb = store.meta_get(conn, "heartbeat")
    age = (time.time() - float(hb)) if hb else None
    rows = conn.execute("SELECT COUNT(*) n FROM obs").fetchone()["n"]
    ev = conn.execute("SELECT COUNT(*) n FROM evidence").fetchone()["n"]
    size = os.path.getsize(store.db_path(cfg)) if os.path.exists(store.db_path(cfg)) else 0
    running = Lock(cfg["port"] + 1)
    is_running = not running.acquire()
    running.release()
    return {
        "running": is_running,
        "heartbeat_age_s": round(age, 1) if age is not None else None,
        "intervals": rows, "evidence": ev,
        "db_bytes": size, "data_dir": cfg["_data_dir"],
        "recovery_dirs": signals.recovery_dirs(cfg),
    }
