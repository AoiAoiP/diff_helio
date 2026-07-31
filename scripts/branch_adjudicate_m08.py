# FEA (d) branch adjudication: does m08 zero-stroke flip at 42-58deg when the
# load is applied with FINE substeps? Baseline ansys_gravity.py solves with
# NSUBST,1,10,1 (single initial increment) which can step over a snap-through
# limit point; GUI Workbench m08 bins flipped at 46deg, script m08 did not.
# Rerun the identical APDL (same geometry/mesh/BCs) with NSUBST,50,500,50 and
# compare plate-normal w = uy*cos(t)+uz*sin(t) stats against:
#   coarse  = data_proxy_margin/7x5_margin08/ansys_csv (script, no flip)
#   GUI     = data_proxy/ansys_csv                     (Workbench, flips 46deg)
# If the fine run flips (mean_w sign change / PV collapse-regrow), the coarse
# stepping skipped a real limit point; if it stays smooth, the script m08
# smooth branch is a converged stable equilibrium and the GUI flip comes from
# Workbench-specific solver settings.
import os, sys, tempfile, shutil
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ansys_gravity import (generate_apdl_input, load_bolt_layout,
                           bolt_positions, run_ansys, ANSYS_EXE, ROOT)

ANGLES = [38, 42, 46, 50, 54, 58]
PATCH_FROM = "NSUBST,1,10,1"
PATCH_TO = "NSUBST,50,500,50"
# --rotfix: additionally fix rotations at bolt patches (Workbench "Fixed
# Support" fixes all 6 DOF; script template fixes translations only).
# --meshfine: 128x96 mapped mesh (mesh-convergence check of the branch).
ROTFIX = "--rotfix" in sys.argv
MESHFINE = "--meshfine" in sys.argv
if MESHFINE:
    ANGLES = [46, 50, 58]


def w_stats(csv_path, ang):
    d = np.loadtxt(str(csv_path), delimiter=',', skiprows=1)
    c, s = np.cos(np.radians(ang)), np.sin(np.radians(ang))
    w = d[:, 4] * c + d[:, 5] * s
    return w.mean() * 1000, np.ptp(w) * 1000


def main():
    layout = load_bolt_layout(str(ROOT / "configs/bolt_layouts/7x5_default.json"))
    if MESHFINE:
        layout["mesh_ndiv_x"] = 128
        layout["mesh_ndiv_z"] = 96
    positions = bolt_positions(layout)
    out_dir = ROOT / "validation" / "branch_m08"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{'ang':>4} | {'fine_mean':>9} {'fine_PV':>8} {'bisect':>6} | "
          f"{'coarse_mean':>11} {'PV':>6} | {'GUI_mean':>8} {'PV':>6}   (mm)")
    for ang in ANGLES:
        work = tempfile.mkdtemp(prefix=f"branch_{ang}deg_", dir=str(ROOT / "build"))
        try:
            dat, csv = generate_apdl_input(layout, float(ang), positions, "", work)
            txt = open(dat).read()
            assert PATCH_FROM in txt, "NSUBST line not found in generated APDL"
            txt = txt.replace(PATCH_FROM, PATCH_TO)
            if ROTFIX:
                txt = txt.replace(
                    "D,ALL,UZ,0.0",
                    "D,ALL,UZ,0.0\n"
                    "D,ALL,ROTX,0.0            ! rotfix variant: full fixed support\n"
                    "D,ALL,ROTY,0.0\n"
                    "D,ALL,ROTZ,0.0")
                assert "ROTZ" in txt
            with open(dat, "w") as fh:
                fh.write(txt)
            tag = "rotfix" if ROTFIX else ("meshfine" if MESHFINE else "fine")
            ok = run_ansys(dat, work, ANSYS_EXE)
            if not ok or not os.path.exists(csv):
                print(f"{ang:4d} | ANSYS FAILED ok={ok}", flush=True)
                continue
            shutil.copy(csv, out_dir / f"node_dump_{ang}deg_{tag}.csv")
            jobname = os.path.splitext(os.path.basename(dat))[0]
            outlog = os.path.join(work, f"{jobname}.out")
            bis = -1
            if os.path.exists(outlog):
                bis = open(outlog, errors="ignore").read().lower().count("bisection")
            fm, fp = w_stats(csv, ang)
            cm, cp = w_stats(ROOT / "data_proxy_margin/7x5_margin08/ansys_csv"
                             f"/node_dump_{ang}deg.csv", ang)
            gm, gp = w_stats(ROOT / f"data_proxy/ansys_csv/node_dump_{ang}deg.csv", ang)
            print(f"{ang:4d} | {fm:9.3f} {fp:8.2f} {bis:6d} | "
                  f"{cm:11.3f} {cp:6.2f} | {gm:8.3f} {gp:6.2f}", flush=True)
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
