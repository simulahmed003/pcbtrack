"""Configuration and data-directory resolution. Standard library only."""
import json, os, sys, copy

APP = "pcbtrack"

DEFAULTS = {
    "tick_seconds": 5,
    "idle_seconds": 180,
    "thinking_grace_seconds": 300,
    "scan_seconds": 60,
    "min_block_seconds": 30,
    "max_interval_seconds": 600,
    "sticky_minutes": 10,
    "port": 8765,
    "day_cutover_hour": 0,
    "private_title_patterns": [
        "(?i)incognito", "(?i)inprivate", "(?i)\\bbank\\b",
        "(?i)password", "(?i)facebook", "(?i)messenger", "(?i)whatsapp",
    ],
    "altium": {
        "processes": ["X2.EXE", "DXP.EXE"],
        "main_window_class": "TDocumentForm",
        "recovery_globs": [
            "%APPDATA%/Altium/Altium Designer */Recovery",
            "%APPDATA%/Altium/Altium Designer*/Recovery",
        ],
        "history_dirnames": ["History", "__History"],
    },
    # the design tools the dashboard puts first; everything else is secondary
    "cad_processes": ["X2.EXE", "DXP.EXE", "kicad.exe", "eeschema.exe",
                      "pcbnew.exe", "EasyEDA Pro.exe", "easyeda.exe"],
    "project_dirs": [],
    "stages": [
        "client_meeting", "study_existing", "study_learning", "library_symbol",
        "library_footprint", "component_search", "schematic", "erc", "eco_sync",
        "bom", "rules_stackup", "pcb_layout", "placement", "routing", "drc",
        "silkscreen", "fab_output", "revision", "firmware", "cam_milling",
        "assembly_testing", "messaging", "admin", "unknown",
    ],
    # stages you add from the dashboard; appended to "stages"
    "custom_stages": [],
    "merge_library_stages_in_report": False,
    "daily_target_hours": 5,
    "doctype_stage": {
        "SCH": "schematic",
        # an open PcbDoc says "PCB work", not which part of it: placement vs
        # routing is the user's call in review
        "PCB": "pcb_layout",
        "SCHLIB": "library_symbol",
        "PCBLIB": "library_footprint",
        "FAB": "fab_output",
    },
    "roll_up_subprojects_in_report": True,
}


def data_dir():
    """Portable if portable.flag sits next to the package, else per-user."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.exists(os.path.join(here, "portable.flag")):
        d = os.path.join(here, "data")
    elif os.environ.get("PCBTRACK_DATA"):
        d = os.environ["PCBTRACK_DATA"]
    elif sys.platform == "win32":
        d = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "pcbtrack")
    else:
        d = os.path.join(os.path.expanduser("~"), ".local", "share", "pcbtrack")
    os.makedirs(d, exist_ok=True)
    return d


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    path = os.path.join(data_dir(), "config.json")
    user = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                user = json.load(f)
        except Exception as e:
            sys.stderr.write("config.json ignored (%s)\n" % e)
    cfg = _merge(DEFAULTS, user)
    cfg["stages"] = all_stages(cfg)
    cfg["_path"] = path
    cfg["_data_dir"] = data_dir()
    return cfg


def all_stages(cfg):
    out = list(cfg["stages"])
    for s in cfg.get("custom_stages") or []:
        if s not in out:
            out.insert(len(out) - 1 if out and out[-1] == "unknown" else len(out), s)
    return out


def save_user(patch):
    """Persist only the keys the user changed, so defaults can evolve."""
    path = os.path.join(data_dir(), "config.json")
    cur = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cur = json.load(f)
    cur = _merge(cur, patch)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2)
    os.replace(tmp, path)
    return path
