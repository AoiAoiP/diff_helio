# Final package exporter: bolt layout + per-mirror stroke table CSV, and
# surface/slope comparison figures at representative tilt angles (bare gravity
# vs compensated). Parameterized by margin tag:
#
#   python scripts/export_final_package_m04.py [mtag] [bins] [rerun] [out] [layout]
#   default: m04 data_proxy_margin/7x5_margin04 results_g5truth/rerun_m04 \
#            results_final_m04 configs/bolt_layouts/7x5_margin04.json
#   m5 ver.: m05 data_proxy_margin/7x5_margin05_fine results_g5truth/rerun_m05_fine \
#            results_final_m05 configs/bolt_layouts/7x5_margin05.json
#
# Surfaces use pipeline convention: w(x,z;theta) = g_theta(x,z) + sum_b h_b*phi_b
# with h_b = h_pipe from BEST_bolts.txt (renderer-exact). Stroke table lists
# the manufacturing convention (zero-based physical extension, mm).
import os, sys, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from ansys_gravity import load_bolt_layout, bolt_positions

MIRRORS = ["North", "East", "South", "West"]
ANGLES = [10, 30, 58]
MTAG = sys.argv[1] if len(sys.argv) > 1 else "m04"
BINS = os.path.join(ROOT, sys.argv[2] if len(sys.argv) > 2
                    else "data_proxy_margin/7x5_margin04")
RERUN = os.path.join(ROOT, sys.argv[3] if len(sys.argv) > 3
                     else "results_g5truth/rerun_m04")
OUT = os.path.join(ROOT, sys.argv[4] if len(sys.argv) > 4
                   else "results_final_m04")
LAYOUT = os.path.join(ROOT, sys.argv[5] if len(sys.argv) > 5
                      else "configs/bolt_layouts/7x5_margin04.json")
W, L, GS = 12.84, 9.45, 32


def load_bolts(mirror):
    """Return (h_pipe_m, stroke_m) arrays from rerun BEST/STROKE files."""
    best = np.loadtxt(os.path.join(RERUN, f"{mirror}_300m_BEST_bolts.txt"),
                      comments="#", encoding="utf-8")
    stroke = np.loadtxt(os.path.join(RERUN, f"{mirror}_300m_STROKE_bolts.txt"),
                        comments="#", encoding="utf-8")
    return best[:, 1], stroke


def main():
    os.makedirs(OUT, exist_ok=True)
    layout = load_bolt_layout(LAYOUT)
    pos = bolt_positions(layout)

    # ---- 1. layout + stroke table CSV ----
    bolts = {m: load_bolts(m) for m in MIRRORS}
    csv_path = os.path.join(OUT, "bolt_layout_and_strokes.csv")
    with open(csv_path, "w") as fh:
        fh.write(f"# {MTAG} final package: 7x5 layout + truth-reoptimized bolts\n")
        fh.write(f"# source: {RERUN} (ANSYS-truth gravity, 100 iter @110dir)\n")
        fh.write("idx,x_m,z_m," + ",".join(f"{m}_stroke_mm" for m in MIRRORS) + "\n")
        for i, (bx, bz) in enumerate(pos):
            row = [f"{i}", f"{bx:.4f}", f"{bz:.4f}"]
            row += [f"{bolts[m][1][i]*1000:.2f}" for m in MIRRORS]
            fh.write(",".join(row) + "\n")
    print("wrote", csv_path)

    # ---- 2. figures ----
    phi = np.fromfile(os.path.join(BINS, "influence_phi.bin"),
                      dtype=np.float32).reshape(35, GS, GS)
    phi_u = np.fromfile(os.path.join(BINS, "influence_phi_u.bin"),
                        dtype=np.float32).reshape(35, GS, GS)
    phi_v = np.fromfile(os.path.join(BINS, "influence_phi_v.bin"),
                        dtype=np.float32).reshape(35, GS, GS)
    # slope rows need PHYSICAL units (m/m): gravity bin du/dv planes are
    # already physical (generator: central FD / dx,dz), but influence_phi_u/v
    # are NORMALIZED-u/v derivatives (dphi/du = dphi/dx * W, CLAUDE.md 2.1)
    phi_u_phys = phi_u / W
    phi_v_phys = phi_v / L
    xs = (np.arange(GS) + 0.5) / GS * W - W / 2
    zs = (np.arange(GS) + 0.5) / GS * L - L / 2
    extent = [xs[0], xs[-1], zs[0], zs[-1]]
    bx = [p[0] for p in pos]; bz = [p[1] for p in pos]

    for ang in ANGLES:
        g = np.fromfile(os.path.join(BINS, f"gravity_{ang}deg.bin"),
                        dtype=np.float32).reshape(3, GS, GS)
        fig, axes = plt.subplots(2, 5, figsize=(22, 7.5),
                                 sharex=True, sharey=True)
        panels = [("bare (gravity only)", None)] + [(m, m) for m in MIRRORS]
        wlim = [np.inf, -np.inf]; slim = [0, 0]
        surfs = []
        for name, m in panels:
            if m is None:
                w, du, dv = g[0], g[1], g[2]
            else:
                h = bolts[m][0]
                w = g[0] + np.tensordot(h, phi, axes=(0, 0))
                du = g[1] + np.tensordot(h, phi_u_phys, axes=(0, 0))
                dv = g[2] + np.tensordot(h, phi_v_phys, axes=(0, 0))
            slp = np.sqrt(du**2 + dv**2) * 1000
            surfs.append((name, w * 1000, slp))
            wlim = [min(wlim[0], (w*1000).min()), max(wlim[1], (w*1000).max())]
            slim[1] = max(slim[1], slp.max())
        for j, (name, wmm, slp) in enumerate(surfs):
            im0 = axes[0, j].imshow(wmm, extent=extent, origin="lower",
                                    cmap="RdBu_r", vmin=-max(abs(wlim[0]), abs(wlim[1])),
                                    vmax=max(abs(wlim[0]), abs(wlim[1])))
            axes[0, j].plot(bx, bz, "k.", ms=3)
            axes[0, j].set_title(name)
            im1 = axes[1, j].imshow(slp, extent=extent, origin="lower",
                                    cmap="viridis", vmin=0, vmax=slim[1])
            axes[1, j].plot(bx, bz, "w.", ms=3)
            axes[0, j].set_ylabel("z (m)")
            axes[1, j].set_ylabel("z (m)")
            axes[1, j].set_xlabel("x (m)")
        fig.colorbar(im0, ax=axes[0, :].tolist(), shrink=0.8, label="w (mm)")
        fig.colorbar(im1, ax=axes[1, :].tolist(), shrink=0.8,
                     label="|slope| (mrad)")
        fig.suptitle(f"{MTAG} truth field + truth-reoptimized bolts, "
                     f"tilt {ang} deg (ANSYS truth, fine-substep)")
        fig.savefig(os.path.join(OUT, f"fig_surface_{ang}deg.png"),
                    dpi=160, bbox_inches="tight")
        plt.close(fig)
        print(f"wrote fig_surface_{ang}deg.png")


if __name__ == "__main__":
    main()
