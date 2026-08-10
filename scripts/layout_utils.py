# Shared bolt-layout JSON parsing for the data pipeline (Phase 5.4).
#
# Three coordinate forms (priority order):
#   1. "bolt_positions": [[x, z], ...]          — free per-bolt coordinates
#   2. "positions_x": [...], "positions_z": [...] — x/z bolt-line coordinates
#      (Cartesian product, row-major z-outer/x-inner)
#   3. "bolts_x"/"bolts_z"/"margin"             — legacy uniform grid
#
# Explicit coordinates are plate-local meters with origin at the plate CENTER
# (x in [-W/2, W/2], z in [-L/2, L/2]), matching bolt_positions_from_layout().
# All forms share the plate parameter keys (plate_width_m, ...).
import json
import numpy as np

PLATE_KEYS = ["plate_width_m", "plate_length_m", "plate_thickness_m"]


def layout_form(layout):
    if "bolt_positions" in layout:
        return "free"
    if "positions_x" in layout and "positions_z" in layout:
        return "lines"
    return "grid"


def load_layout(path):
    """Load and validate a bolt layout JSON. Accepts all three forms."""
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    form = layout_form(cfg)
    required = list(PLATE_KEYS)
    if form == "grid":
        required += ["bolts_x", "bolts_z", "margin"]
    for k in required:
        if k not in cfg:
            raise ValueError(f"Bolt layout config missing key: {k}")
    return cfg


def bolt_positions(layout):
    """Bolt (x,z) arrays (plate-local, center-origin, meters).
    grid/lines forms are row-major (z outer, x inner); free form is as given."""
    form = layout_form(layout)
    if form == "free":
        pts = np.asarray(layout["bolt_positions"], dtype=float).reshape(-1, 2)
        return pts[:, 0].copy(), pts[:, 1].copy()
    pW, pL = layout["plate_width_m"], layout["plate_length_m"]
    if form == "lines":
        px = np.asarray(layout["positions_x"], dtype=float)
        pz = np.asarray(layout["positions_z"], dtype=float)
    else:
        nx, nz, m = layout["bolts_x"], layout["bolts_z"], layout["margin"]
        bu = m + (1.0 - 2.0 * m) * np.arange(nx) / (nx - 1)
        bv = m + (1.0 - 2.0 * m) * np.arange(nz) / (nz - 1)
        px = (bu - 0.5) * pW
        pz = (bv - 0.5) * pL
    bx = np.array([x for z in pz for x in px])
    bz = np.array([z for z in pz for x in px])
    return bx, bz


def positions_lines(layout):
    """Bolt-line coordinates for the ROM tensor mesh: (px, pz) sorted ascending,
    corner-origin ([0, W] x [0, L], meters). Free form -> sorted unique union."""
    pW, pL = layout["plate_width_m"], layout["plate_length_m"]
    form = layout_form(layout)
    if form == "grid":
        nx, nz, m = layout["bolts_x"], layout["bolts_z"], layout["margin"]
        px = (m + (1.0 - 2.0 * m) * np.arange(nx) / (nx - 1)) * pW
        pz = (m + (1.0 - 2.0 * m) * np.arange(nz) / (nz - 1)) * pL
        return px, pz
    bx, bz = bolt_positions(layout)
    px = np.unique(np.round(bx + pW / 2.0, decimals=9))
    pz = np.unique(np.round(bz + pL / 2.0, decimals=9))
    return px, pz


def layout_description(layout):
    """Short human-readable layout summary (form-aware)."""
    form = layout_form(layout)
    if form == "free":
        n = len(layout["bolt_positions"])
        return f"free ({n} bolts)"
    if form == "lines":
        return (f"lines {len(layout['positions_x'])}x{len(layout['positions_z'])} "
                f"= {len(layout['positions_x']) * len(layout['positions_z'])} bolts")
    return (f"grid {layout['bolts_x']}x{layout['bolts_z']} "
            f"= {layout['bolts_x'] * layout['bolts_z']} bolts, "
            f"margin={layout['margin']}")
