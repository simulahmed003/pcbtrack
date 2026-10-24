"""File-system signals - the part that makes Altium legible.

Altium's window caption only ever shows the PROJECT (the option that showed
the active document was removed in Altium Designer 18.1), so schematic, PCB,
symbol-library and footprint-library work cannot be told apart from the title.

Altium does, however, write Auto Save recovery copies of every MODIFIED open
document, named  <doc>.~(n).<ext>  into
    %APPDATA%/Altium/Altium Designer <GUID>/Recovery
and, on every manual save, a timestamped zip into the project's History folder.
The EXTENSION of those files is the answer:
    .SchDoc -> schematic    .PcbDoc -> pcb
    .SchLib -> symbol lib   .PcbLib -> footprint lib
This mirrors how kicad-wakatime solves the same problem for KiCad.
"""
import os, re, glob, time

DOCTYPE = {
    ".schdoc": "SCH", ".pcbdoc": "PCB", ".schlib": "SCHLIB", ".pcblib": "PCBLIB",
    ".kicad_sch": "SCH", ".kicad_pcb": "PCB", ".kicad_sym": "SCHLIB",
    ".kicad_mod": "PCBLIB", ".intlib": "SCHLIB", ".pcbdoclib": "PCBLIB",
}
# Altium autosave decoration:  Sheet.~(3).SchDoc   /  Sheet.~(3).SchDoc.Zip
AUTOSAVE_RE = re.compile(r"^(?P<stem>.+?)\.~\((?P<n>\d+)\)(?P<ext>\.[A-Za-z_]+)(?:\.zip)?$", re.I)
PLAIN_RE = re.compile(r"^(?P<stem>.+?)(?P<ext>\.[A-Za-z_]+)(?:\.zip)?$")


def classify_filename(name):
    """-> (document stem, doctype) or (None, None)."""
    m = AUTOSAVE_RE.match(name) or PLAIN_RE.match(name)
    if not m:
        return None, None
    ext = m.group("ext").lower()
    dt = DOCTYPE.get(ext)
    if not dt:
        return None, None
    return m.group("stem"), dt


def expand(pattern):
    p = os.path.expandvars(os.path.expanduser(pattern))
    return glob.glob(p)


def recovery_dirs(cfg):
    out = []
    for g in cfg["altium"]["recovery_globs"]:
        out.extend(d for d in expand(g) if os.path.isdir(d))
    return sorted(set(out))


def scan_dirs(dirs, since, depth=2, limit=4000):
    """Yield (mtime, doc, doctype, path) for interesting files newer than
    `since`. os.scandir keeps this cheap; depth is capped on purpose."""
    seen = 0
    for root in dirs:
        stack = [(root, 0)]
        while stack:
            d, lvl = stack.pop()
            try:
                it = os.scandir(d)
            except OSError:
                continue
            with it:
                for e in it:
                    seen += 1
                    if seen > limit:
                        return
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if lvl < depth:
                                stack.append((e.path, lvl + 1))
                            continue
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if st.st_mtime <= since:
                        continue
                    doc, dt = classify_filename(e.name)
                    if dt:
                        yield (st.st_mtime, doc, dt, e.path)


def collect(cfg, conn, since):
    """Record new file evidence. Returns the number of new rows."""
    dirs = recovery_dirs(cfg)
    kinds = {d: "recovery" for d in dirs}
    for p in cfg.get("project_dirs", []):
        for d in expand(p):
            if os.path.isdir(d):
                dirs.append(d)
                kinds[d] = "save"
    n = 0
    for root in dirs:
        kind = kinds.get(root, "save")
        for mt, doc, dt, path in scan_dirs([root], since):
            k = "history" if re.search(r"[\\/]_{0,2}History[\\/]", path, re.I) else kind
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO evidence(t,kind,doc,doctype,path)"
                    " VALUES(?,?,?,?,?)", (mt, k, doc, dt, path))
                n += cur.rowcount if cur.rowcount > 0 else 0
            except Exception:
                pass
    conn.commit()
    return n
