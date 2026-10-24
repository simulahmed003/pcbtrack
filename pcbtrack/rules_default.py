"""Default classification rules.

DIALOGS: Altium's modal/child window captions. These are the one thing the
window title DOES reveal reliably, and in the 2026-10-22/23 baseline they
accounted for ~1.2 h that the old tracker filed as "Other".
Entries marked OBSERVED were seen in that baseline; the rest are standard
Altium dialogs and are marked UNVERIFIED until seen in the wild.
"""

# caption regex -> (stage, confidence, verified)
DIALOGS = [
    # --- observed in the baseline data ---
    (r"^Polygon Pour Manager", "routing", 0.95, "OBSERVED"),
    (r"^Design Rule Checker", "drc", 0.95, "OBSERVED"),
    (r"^Engineering Change Order", "eco_sync", 0.95, "OBSERVED"),
    (r"^Bill of Materials for Project", "bom", 0.95, "OBSERVED"),
    (r"^Replace\b", "component_search", 0.85, "OBSERVED"),
    (r"^Update From Library", "library_symbol", 0.9, "OBSERVED"),
    (r"^\s*PCB Model", "library_footprint", 0.9, "OBSERVED"),
    (r"^Confirm Designator Changes", "erc", 0.8, "OBSERVED"),
    (r"^Smart PDF", "fab_output", 0.9, "OBSERVED"),
    (r"^Measure Distance", "routing", 0.6, "OBSERVED"),
    (r"^\s*Align Objects", "placement", 0.7, "OBSERVED"),
    # --- standard Altium dialogs, not yet confirmed on this machine ---
    (r"Footprint Wizard|IPC.*Footprint", "library_footprint", 0.95, "UNVERIFIED"),
    (r"^Symbol Wizard|^Component Editor|Single Component Editing",
     "library_symbol", 0.9, "UNVERIFIED"),
    (r"^Library Splitter|^Browse Libraries|^Libraries$", "library_symbol", 0.8, "UNVERIFIED"),
    (r"^Place Component|^Component Placement", "placement", 0.8, "UNVERIFIED"),
    (r"Layer Stack Manager", "rules_stackup", 0.95, "UNVERIFIED"),
    (r"Rules and Constraints|^Net Class|^Differential Pair",
     "rules_stackup", 0.9, "UNVERIFIED"),
    (r"^Choose Preferred Width|Teardrop", "routing", 0.9, "UNVERIFIED"),
    (r"Gerber Setup|NC Drill Setup|Pick and Place|^ODB|Output Job",
     "fab_output", 0.95, "UNVERIFIED"),
    (r"Annotate|^Reset Designators", "erc", 0.85, "UNVERIFIED"),
    (r"Messages$", "erc", 0.4, "UNVERIFIED"),
]

# window title / app regex -> (stage, confidence)
APPS = [
    (r"(?i)\blcsc\b|\beasyeda\b|\bsnapeda\b|ultralibrarian|octopart"
     r"|\bdigikey\b|\bmouser\b|componentsearchengine|\bjlcpcb\b",
     "component_search", 0.85),
    (r"(?i)\.pdf\b|datasheet|reference manual", "study_existing", 0.7),
    (r"(?i)^zoom|microsoft teams|google meet|\bskype\b", "client_meeting", 0.7),
    (r"(?i)flatcam|candle|bcnc|grbl|coppercam|cirqoid|mach3", "cam_milling", 0.9),
    (r"(?i)vscode|code\.exe|pycharm|cubeide|keil|arduino|platformio",
     "firmware", 0.85),
    (r"(?i)\bexcel\b|\.xlsx", "bom", 0.6),
    (r"(?i)whatsapp|telegram|slack|discord|outlook|thunderbird|\bgmail\b",
     "messaging", 0.55),
    (r"(?i)explorer\.exe", "admin", 0.3),
]

# Document extension found inside a window title -> doctype
TITLE_DOC = [
    (r"(?i)([\w.\-]+\.SchLib)\b", "SCHLIB"),
    (r"(?i)([\w.\-]+\.PcbLib)\b", "PCBLIB"),
    (r"(?i)([\w.\-]+\.SchDoc)\b", "SCH"),
    (r"(?i)([\w.\-]+\.PcbDoc)\b", "PCB"),
    (r"(?i)([\w.\-]+\.kicad_sch)\b", "SCH"),
    (r"(?i)([\w.\-]+\.kicad_pcb)\b", "PCB"),
]

# Project name sources inside a window title
PROJECT_IN_TITLE = [
    r"([\w.\-]+)\.PrjPcb\b",
    r"([\w.\-]+)\.kicad_pro\b",
    r"([\w.\-]+)\.(?:SchDoc|PcbDoc|kicad_sch|kicad_pcb)\b",
]
