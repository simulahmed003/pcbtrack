"""Platform probe. Returns one Sample per tick.

Windows implementation uses only ctypes + Win32 calls that are cheap and
hook-free:
  GetForegroundWindow / GetWindowTextW / GetClassNameW
  GetWindowThreadProcessId / OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)
  QueryFullProcessImageNameW
  GetLastInputInfo        (idle, no hooks, no keylogging)
  OpenInputDesktop        (workstation locked?)
A Replay backend lets the whole pipeline be tested off-Windows.
"""
import sys, os, time, collections

Sample = collections.namedtuple(
    "Sample", "t app title wclass idle locked doc doctype docsrc")
Sample.__new__.__defaults__ = (None, None, None)


class Replay:
    """Feeds a scripted list of (seconds, app, title, wclass, idle, locked)."""

    def __init__(self, script, t0=None):
        self.t = t0 or time.time()
        self.q = []
        for row in script:
            secs, app, title, wclass, idle, locked = row[:6]
            doc, doctype, docsrc = (list(row[6:]) + [None, None, None])[:3]
            self.q.append((secs, app, title, wclass, idle, locked,
                           doc, doctype, docsrc))
        self.i = 0
        self.left = self.q[0][0] if self.q else 0

    def __call__(self, tick=5):
        if self.i >= len(self.q):
            return None
        (secs, app, title, wclass, idle, locked,
         doc, doctype, docsrc) = self.q[self.i]
        s = Sample(self.t, app, title, wclass, idle, locked,
                   doc, doctype, docsrc)
        self.t += tick
        self.left -= tick
        if self.left <= 0:
            self.i += 1
            if self.i < len(self.q):
                self.left = self.q[self.i][0]
        return s


def win_probe(altium_procs=("x2.exe", "dxp.exe")):
    """Build the live Windows probe: a function returning one Sample
    (foreground app, title, class, idle seconds, locked, Altium document)."""
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    u32.GetForegroundWindow.restype = wintypes.HWND
    u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    k32.GetTickCount.restype = wintypes.DWORD
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def locked():
        # OpenInputDesktop fails when the secure (locked) desktop is active.
        h = u32.OpenInputDesktop(0, False, 0x0100)
        if h:
            u32.CloseDesktop(h)
            return False
        return True

    def probe(tick=5):
        li = LASTINPUTINFO()
        li.cbSize = ctypes.sizeof(li)
        idle = 0.0
        if u32.GetLastInputInfo(ctypes.byref(li)):
            idle = max(0.0, (k32.GetTickCount() - li.dwTime) / 1000.0)
        hwnd = u32.GetForegroundWindow()
        title = app = wclass = ""
        if hwnd:
            n = u32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value
            cb = ctypes.create_unicode_buffer(256)
            u32.GetClassNameW(hwnd, cb, 256)
            wclass = cb.value
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                ph = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
                if ph:
                    size = wintypes.DWORD(1024)
                    pb = ctypes.create_unicode_buffer(1024)
                    if k32.QueryFullProcessImageNameW(ph, 0, pb, ctypes.byref(size)):
                        app = os.path.basename(pb.value)
                    k32.CloseHandle(ph)
        # Only for Altium: one EnumChildWindows pass to learn which document
        # is actually open. The caption never says (see pcbtrack/altium.py).
        doc = doctype = docsrc = None
        if hwnd and app.lower() in altium_procs:
            try:
                from .altium import read_active_document
                doc, doctype, docsrc = read_active_document(hwnd)
                if not doctype:
                    # A dialog is in front: ask its owner, the main window.
                    u32.GetAncestor.restype = wintypes.HWND
                    owner = u32.GetAncestor(hwnd, 3)      # GA_ROOTOWNER
                    if owner and owner != hwnd:
                        doc, doctype, docsrc = read_active_document(owner)
            except Exception:
                pass
        return Sample(time.time(), app, title, wclass, idle, locked(),
                      doc, doctype, docsrc)

    return probe


def get_probe(cfg=None):
    if sys.platform == "win32":
        procs = tuple(p.lower() for p in
                      (cfg or {}).get("altium", {}).get("processes", ["X2.EXE"]))
        return win_probe(procs or ("x2.exe",))
    raise RuntimeError(
        "Live tracking needs Windows. Use the Replay backend for tests, "
        "or run 'pcbtrack probe' on the Windows machine.")
