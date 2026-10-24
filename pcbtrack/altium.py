"""Reading the ACTIVE DOCUMENT out of a running Altium Designer.

Discovered by probe on 24 Oct 2026 against Altium Designer 26.7.1 (process
X2.EXE, main window class TDocumentForm). Altium's *caption* usually shows
only the project, but two of its child windows give the answer directly:

  TdxTabSheet / TViewComponent   their caption IS the active document tab,
                                 e.g. "[1] ESC_PCB.SchDoc", "ESC_Board.PcbDoc",
                                 or "Home Page" when no document is open.
  T*View_GraphicalForm           one editor form per open document; the
                                 VISIBLE one is the active editor, which gives
                                 the document type independently.

Both are plain Win32: EnumChildWindows + GetClassNameW + GetWindowTextW +
IsWindowVisible. No UI Automation, no COM, no timeouts, no plugin.

This beats watching Auto Save files because it sees *viewing*, not only
editing, and it is instant rather than lagging the autosave interval. Auto
Save stays as the corroborating signal and as proof that editing happened.
"""
import re

# Child window classes whose caption carries the active document tab name.
TAB_CLASSES = ("TdxTabSheet", "TViewComponent")

# One per open document; the visible one is the active editor.
EDITOR_CLASSES = {
    "TSCHView_GraphicalForm": "SCH",
    "TPCBView_GraphicalForm": "PCB",
    "TSCHView_LibraryGraphicalForm": "SCHLIB",
    "TPCBView_LibraryGraphicalForm": "PCBLIB",   # not yet seen; verify
    "TPCBLibView_GraphicalForm": "PCBLIB",       # not yet seen; verify
}

# Never read these as the active document: the doc bar lists OTHER open files.
IGNORE_CLASSES = ("TGUIDocBarButton", "TXPDocBarPopupPanel", "TCaptionSearchEdit")

EXT_DOCTYPE = {
    "schdoc": "SCH", "pcbdoc": "PCB", "schlib": "SCHLIB", "pcblib": "PCBLIB",
    "intlib": "SCHLIB", "outjob": "FAB", "prjpcb": None, "harness": None,
}

# "[1] ESC_PCB.SchDoc"  ->  ESC_PCB.SchDoc     (the [n] prefix is the sheet no.)
TAB_RE = re.compile(r"^\s*(?:\[\s*\d+\s*\]\s*)?(?P<name>[^\\/:*?\"<>|]+?\.(?P<ext>[A-Za-z]+))\s*\*?\s*$")

NON_DOCUMENT_TABS = {"home page", "start page", "storage manager", "projects"}


def parse_tab_title(title):
    """-> (document name, doctype) or (None, None).

    >>> parse_tab_title("[1] ESC_PCB.SchDoc")
    ('ESC_PCB.SchDoc', 'SCH')
    >>> parse_tab_title("ESC_Board.PcbDoc")
    ('ESC_Board.PcbDoc', 'PCB')
    >>> parse_tab_title("Home Page")
    (None, None)
    """
    if not title:
        return None, None
    if title.strip().lower() in NON_DOCUMENT_TABS:
        return None, None
    m = TAB_RE.match(title)
    if not m:
        return None, None
    dt = EXT_DOCTYPE.get(m.group("ext").lower())
    if not dt:
        return None, None
    return m.group("name"), dt


def pick_active(children):
    """children: iterable of (wclass, title, visible).

    Returns (document, doctype, how) with `how` naming the evidence, or
    (None, None, None). A visible tab wins; an invisible tab is a fallback;
    the visible editor form class is used to confirm or to supply the type.
    """
    vis_tab = invis_tab = None
    editor = None
    for wclass, title, visible in children:
        if wclass in IGNORE_CLASSES:
            continue
        if wclass in TAB_CLASSES:
            doc, dt = parse_tab_title(title)
            if doc:
                if visible and vis_tab is None:
                    vis_tab = (doc, dt)
                elif invis_tab is None:
                    invis_tab = (doc, dt)
        elif wclass in EDITOR_CLASSES and visible and editor is None:
            editor = EDITOR_CLASSES[wclass]

    tab = vis_tab or invis_tab
    if tab:
        doc, dt = tab
        if editor and editor != dt:
            # The editor form is the more direct evidence of which editor is
            # on screen; keep the document name but trust the editor's type.
            return doc, editor, "tab+editor(%s)" % editor
        return doc, dt, "document tab" + ("" if vis_tab else " (hidden)")
    if editor:
        return None, editor, "visible editor form"
    return None, None, None


def read_active_document(hwnd):
    """Live read against a real Altium main window. Windows only.
    One EnumChildWindows pass over roughly 40 children: a few hundred
    microseconds, which is why this can run every tick."""
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    kids = []

    def on_child(h, _):
        cb = ctypes.create_unicode_buffer(128)
        u32.GetClassNameW(h, cb, 128)
        wclass = cb.value
        if wclass in TAB_CLASSES or wclass in EDITOR_CLASSES:
            n = u32.GetWindowTextLengthW(h)
            tb = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(h, tb, n + 1)
            kids.append((wclass, tb.value, bool(u32.IsWindowVisible(h))))
        return True

    u32.EnumChildWindows(hwnd, CB(on_child), 0)
    return pick_active(kids)
