"""One-off discovery probe. Run on the Windows machine:  pcbtrack probe

It answers the questions that no amount of reading can settle, by looking at
this particular Altium install:
  1. what every Altium top-level window reports as its caption and class
  2. whether child-window classes differ between the four editors
  3. where the Auto Save Recovery folder is and how it names files
Paste the output back into the chat and the rules get tightened for your setup.
"""
import os, sys, time, json
from . import config, signals


def windows_snapshot():
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    rows = []

    def text(h):
        n = u32.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(h, b, n + 1)
        return b.value

    def cls(h):
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, b, 256)
        return b.value

    def proc(h):
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        ph = k32.OpenProcess(0x1000, False, pid.value)
        name = ""
        if ph:
            size = wintypes.DWORD(1024)
            pb = ctypes.create_unicode_buffer(1024)
            if k32.QueryFullProcessImageNameW(ph, 0, pb, ctypes.byref(size)):
                name = os.path.basename(pb.value)
            k32.CloseHandle(ph)
        return name

    def on_top(h, _):
        if u32.IsWindowVisible(h):
            rows.append({"hwnd": h, "proc": proc(h), "class": cls(h),
                         "title": text(h), "children": []})
        return True

    u32.EnumWindows(CB(on_top), 0)
    for r in rows:
        kids = []

        def on_child(h, _):
            c, t = cls(h), text(h)
            if c or t:
                kids.append({"class": c, "title": t[:60]})
            return True
        u32.EnumChildWindows(r["hwnd"], CB(on_child), 0)
        seen, uniq = set(), []
        for k in kids:
            if k["class"] not in seen:
                seen.add(k["class"])
                uniq.append(k)
        r["children"] = uniq[:40]
    return rows


def run(seconds=120, interval=10):
    cfg = config.load()
    print("pcbtrack probe - watching for %ds\n" % seconds)
    print("While this runs, please switch Altium between, holding each ~20s:")
    print("  1) a schematic sheet (.SchDoc)")
    print("  2) the PCB (.PcbDoc)")
    print("  3) a schematic library (.SchLib)")
    print("  4) a PCB/footprint library (.PcbLib)\n")
    recs = signals.recovery_dirs(cfg)
    print("Recovery folders found: %s" % (recs or "NONE - set Auto Save on (see docs)"))
    for d in recs:
        try:
            names = sorted(os.listdir(d))[:15]
            print("  %s -> %s" % (d, names))
        except OSError as e:
            print("  %s -> %s" % (d, e))
    print()
    out = {"recovery_dirs": recs, "samples": []}
    procs = {p.lower() for p in cfg["altium"]["processes"]}
    t_end = time.time() + seconds
    while time.time() < t_end:
        snap = [w for w in windows_snapshot() if (w["proc"] or "").lower() in procs]
        for w in snap:
            print("[%s] proc=%s class=%s\n     title=%r" % (
                time.strftime("%H:%M:%S"), w["proc"], w["class"], w["title"]))
            if w["children"]:
                print("     child classes: %s" % ", ".join(
                    c["class"] for c in w["children"][:12]))
        if not snap:
            print("[%s] no Altium window visible" % time.strftime("%H:%M:%S"))
        out["samples"].append({"t": time.time(), "windows": snap})
        time.sleep(interval)
    path = os.path.join(cfg["_data_dir"], "probe_%s.json" % time.strftime("%Y%m%d_%H%M"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    print("\nSaved: %s\nSend that file (or the text above) back to tighten the rules." % path)
    return path
