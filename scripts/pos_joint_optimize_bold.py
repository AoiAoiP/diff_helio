# Phase 6 bold driver: top-K bold position moves with deterministic fixed-h acceptance.
#
# Per mirror, per step:
#   1. dump at current (layout, h) -> surface grads -> dL/dpi (TPS sensitivity)
#   2. rank coordinates by |dL|, take top-K (default 8, may be x or z per bolt)
#   3. ladder of move sizes DELTA (default 0.05..0.30 m): move top-K only,
#      each by -DELTA * dL_k/max|dL|; clamp constraints
#   4. evaluate each candidate at FIXED h (1-iter eval, deterministic) -> pick best
#   5. accept iff best Loss improves > accept_thresh; then re-optimize h (inner 100-iter)
#      stop when no ladder candidate improves.
#
#   python scripts/pos_joint_optimize_bold.py --mirror North --steps 8
import os, sys, json, csv, shutil, argparse, subprocess, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "build", "src", "Release", "bezier_opt.exe")
SUMMARY = "optimization_summary.csv"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_utils as lu
import generate_proxy_model as gpm
import tps_position_sensitivity as tps
from pos_joint_optimize import (render, read_best, read_s95, write_init,
                                project_constraints, max_edge_span,
                                perimeter_indices, load_G_total, W, L, GRAV_SRC)

S_PI = 0.3


def make_phi(layout_path, out_dir):
    os.makedirs(os.path.join(ROOT, out_dir), exist_ok=True)
    lay = lu.load_layout(layout_path)
    bx, bz = lu.bolt_positions(lay)
    gpm.generate_influence_data(os.path.join(ROOT, out_dir), bolt_xz=(bx, bz))
    for f in os.listdir(os.path.join(ROOT, GRAV_SRC)):
        if f.startswith("gravity_") and (f.endswith("deg.bin") or f == "gravity_y.bin"):
            shutil.copy2(os.path.join(ROOT, GRAV_SRC, f),
                         os.path.join(ROOT, out_dir, f))


def eval_loss(layout_path_unused, bins_dir, out_dir, mirror, template, init_file):
    """1-iter eval at fixed h; returns (loss_last_iter0, S95)."""
    cfg = dict(template)
    lay = lu.load_layout(layout_path_unused)
    bx, bz = lu.bolt_positions(lay)
    cfg["ellipse_file"] = f"data/ellipse_single/{mirror}_300m.txt"
    cfg["num_bolts"] = len(bx)
    cfg["influence_data_path"] = bins_dir.replace(os.sep, "/")
    cfg["output_dir"] = out_dir.replace(os.sep, "/")
    cfg["iterations"] = 1
    cfg["learning_rate"] = 0.0
    cfg["min_learning_rate"] = 0.0
    cfg["bolt_init_file"] = init_file.replace(os.sep, "/")
    cfg["bolt_init_dir"] = ""
    os.makedirs(os.path.join(ROOT, out_dir), exist_ok=True)
    cfg_path = os.path.join(ROOT, out_dir, "config.json")
    json.dump(cfg, open(cfg_path, "w"), indent=2)
    log = os.path.join(ROOT, out_dir, "run.log")
    with open(log, "w") as lf:
        p = subprocess.run([EXE, "--config", cfg_path], cwd=ROOT,
                           stdout=lf, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        raise RuntimeError(f"eval failed in {out_dir}")
    loss = None
    for line in open(log, encoding="utf-8", errors="ignore"):
        if "Loss=" in line and "Iter" in line:
            loss = float(line.split("Loss=")[1].split(",")[0])
    s95 = read_s95(out_dir, mirror)
    return loss, s95


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mirror", required=True, choices=["North", "East", "South", "West"])
    ap.add_argument("--start-layout", default="configs/bolt_layouts/density/9x7_margin05.json")
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--topk", type=int, default=8)
    ap.add_argument("--ladder", default="0.30,0.20,0.10,0.05")
    ap.add_argument("--accept", type=float, default=0.001,
                    help="min relative Loss improvement to accept a move")
    ap.add_argument("--sundir", choices=["36", "110"], default="36")
    ap.add_argument("--template", default="configs/_fw_tanh_a0_110.json")
    ap.add_argument("--out-root", default="results_pos_bold")
    args = ap.parse_args()

    template = json.load(open(os.path.join(ROOT, args.template)))
    sun = "data/36_sundir_fast.txt" if args.sundir == "36" else "data/110_sundir_paper.txt"
    template["sun_train_file"] = sun
    template["sun_validation_file"] = sun
    template["bolt_l1_lambda"] = 0.0

    ladder = [float(x) for x in args.ladder.split(",")]
    mir = args.mirror
    layout_path = os.path.join(ROOT, args.start_layout)
    _bx0, _bz0 = lu.bolt_positions(lu.load_layout(layout_path))
    peri_idx = perimeter_indices(_bx0, _bz0)
    history = []

    # step 0: inner h-opt from zero init
    bins0 = os.path.join("data_pos_bold", mir, "s00")
    make_phi(layout_path, bins0)
    inner0 = os.path.join(args.out_root, mir, "s00_inner")
    render(layout_path, bins0, inner0, mir, 100, template)
    h_best = read_best(inner0, mir)
    loss0 = None
    for line in open(os.path.join(ROOT, inner0, "run.log"), encoding="utf-8", errors="ignore"):
        if "Loss=" in line:
            loss0 = float(line.split("Loss=")[1].split(",")[0])
    s95_best = read_s95(inner0, mir)
    print(f"[{mir} s0] inner best S95={s95_best:.3f} loss={loss0:.1f}", flush=True)
    history.append({"step": 0, "s95": s95_best, "loss": loss0, "move": "", "accepted": 1})

    best_layout = layout_path
    best_loss = loss0
    for step in range(1, args.steps + 1):
        t0 = time.time()
        # (1) gradient at current state
        bins_dir = os.path.join("data_pos_bold", mir, f"s{step-1:02d}")
        dump_dir = os.path.join(args.out_root, mir, f"s{step:02d}_dump")
        init_file = os.path.join(args.out_root, mir, f"s{step:02d}_init.txt")
        write_init(args.out_root, mir, h_best, os.path.join(ROOT, init_file))
        render(best_layout, bins_dir, dump_dir, mir, 1, template,
               init_file=init_file, dump=True)
        GLy, GLyu, GLyv = load_G_total(dump_dir, mir)
        lay = lu.load_layout(best_layout)
        bx, bz = lu.bolt_positions(lay)
        dL = tps.position_sensitivity(bx, bz, h_best, GLy, GLyu, GLyv)
        n = len(bx)
        order = np.argsort(-np.abs(dL))[:args.topk]
        print(f"[{mir} s{step}] top-{args.topk} grads: "
              + ", ".join(f"{'x' if i < n else 'z'}:{i % n}={dL[i]:+.1e}" for i in order[:4]),
              flush=True)
        # (2) ladder of bold moves at fixed h
        cand_best = None
        for delta in ladder:
            dpi = np.zeros(2 * n)
            dpi[order] = -delta * dL[order] / np.abs(dL[order]).max()
            nbx = bx + dpi[:n]
            nbz = bz + dpi[n:]
            nbx, nbz = project_constraints(nbx, nbz)
            if max_edge_span(nbx, nbz, peri_idx) > 1.8:
                continue
            cand_layout = os.path.join(ROOT, "configs/bolt_layouts/free",
                                       f"p6b_{mir.lower()}_s{step:02d}_{int(delta*1000):03d}.json")
            json.dump({"bolt_positions": [[float(x), float(z)] for x, z in zip(nbx, nbz)],
                       "plate_width_m": W, "plate_length_m": L, "plate_thickness_m": 0.004,
                       "youngs_modulus_pa": 70000000000.0, "poisson_ratio": 0.22,
                       "density_kg_m3": 2500, "gravity_m_s2": 9.81,
                       "mesh_ndiv_x": 64, "mesh_ndiv_z": 48},
                      open(cand_layout, "w"))
            cand_bins = os.path.join("data_pos_bold", mir, f"s{step:02d}_{int(delta*1000):03d}")
            make_phi(cand_layout, cand_bins)
            ev_dir = os.path.join(args.out_root, mir, f"s{step:02d}_{int(delta*1000):03d}_eval")
            loss_c, s95_c = eval_loss(cand_layout, cand_bins, ev_dir, mir, template,
                                      init_file)
            print(f"    delta={delta:.2f}m -> loss={loss_c:.1f} S95={s95_c:.3f}", flush=True)
            if cand_best is None or loss_c < cand_best[0]:
                cand_best = (loss_c, s95_c, delta, cand_layout)
        # (3) acceptance
        if cand_best is None or cand_best[0] > best_loss * (1.0 - args.accept):
            print(f"  no bold candidate improves (best_loss={best_loss:.1f}), stop", flush=True)
            break
        loss_c, s95_c, delta, cand_layout = cand_best
        print(f"  ACCEPT delta={delta:.2f}m loss {best_loss:.1f} -> {loss_c:.1f}", flush=True)
        # (4) re-optimize h at the accepted layout
        best_layout = cand_layout
        best_loss = loss_c
        bins_new = os.path.join("data_pos_bold", mir, f"s{step:02d}")
        shutil.rmtree(os.path.join(ROOT, bins_new), ignore_errors=True)
        make_phi(best_layout, bins_new)
        inner_out = os.path.join(args.out_root, mir, f"s{step:02d}_inner")
        render(best_layout, bins_new, inner_out, mir, 100, template,
               init_file=init_file)
        h_best = read_best(inner_out, mir)
        for line in open(os.path.join(ROOT, inner_out, "run.log"),
                         encoding="utf-8", errors="ignore"):
            if "Loss=" in line:
                best_loss = float(line.split("Loss=")[1].split(",")[0])
        s95_best = read_s95(inner_out, mir)
        history.append({"step": step, "s95": s95_best, "loss": best_loss,
                        "move": f"{delta:.2f}m top{args.topk}", "accepted": 1})
        print(f"  inner best S95={s95_best:.3f} loss={best_loss:.1f} "
              f"[{time.time()-t0:.0f}s]", flush=True)

    out_csv = os.path.join(ROOT, "analysis", f"pos_joint_bold_path_{mir.lower()}.csv")
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["step", "s95", "loss", "move", "accepted"])
        w.writeheader(); w.writerows(history)
    print(f"\n[{mir}] done -> {out_csv}")
    print(f"[{mir}] best layout: {best_layout}  best S95={s95_best:.3f} loss={best_loss:.1f}")


if __name__ == "__main__":
    main()
