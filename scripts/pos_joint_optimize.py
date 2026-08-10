# Phase 6 driver: joint (pos, height) end-to-end optimization, per mirror.
#
# Per mirror, per outer step:
#   1. inner h-opt (renderer, 100-iter Adam, warm start from prev BEST)
#   2. dump run (1 iter, lr=0, dump_surface_grad=1, warm from BEST)
#   3. aggregate per-sun surface grads -> G_total (equal annual weights)
#   4. dL/d pi via TPS direct sensitivity (tps_position_sensitivity)
#   5. Adam step on scaled positions (s_pi=0.3m) + constraint projection
#   6. regenerate TPS phi bins; frozen gravity bins copied from truth set
# Acceptance: next inner best S95 must not regress >1%; else halve step.
#
#   python scripts/pos_joint_optimize.py --mirror North --steps 10 --sundir 36
import os, sys, json, csv, shutil, argparse, subprocess, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "build", "src", "Release", "bezier_opt.exe")
SUMMARY = "optimization_summary.csv"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_utils as lu
import generate_proxy_model as gpm
import tps_position_sensitivity as tps

W, L = 12.84, 9.45
S_PI = 0.3          # position scaling (m)
MIN_GAP = 0.8       # min bolt spacing
EDGE_MIN = 0.35     # min distance from plate edge
GRAV_SRC = "data_proxy_truth/9x7_margin05"


def run(cmd, log_path):
    with open(log_path, "w") as lf:
        p = subprocess.run(cmd, cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT)
    return p.returncode


def make_bins(layout_path, out_dir):
    """phi bins for current layout + frozen gravity bins copied in.
    ALWAYS regenerate phi (TPS is <1s — stale-cache reuse once scrambled
    layout<->bins correspondence across driver versions)."""
    os.makedirs(os.path.join(ROOT, out_dir), exist_ok=True)
    lay = lu.load_layout(layout_path)
    bx, bz = lu.bolt_positions(lay)
    gpm.generate_influence_data(os.path.join(ROOT, out_dir), bolt_xz=(bx, bz))
    for f in os.listdir(os.path.join(ROOT, GRAV_SRC)):
        if f.startswith("gravity_") and (f.endswith("deg.bin") or f == "gravity_y.bin"):
            shutil.copy2(os.path.join(ROOT, GRAV_SRC, f),
                         os.path.join(ROOT, out_dir, f))


def render(layout_path_unused, bins_dir, out_dir, mirror, iters, template,
           init_file=None, dump=False):
    cfg = dict(template)
    lay = lu.load_layout(layout_path_unused)
    bx, bz = lu.bolt_positions(lay)
    cfg["ellipse_file"] = f"data/ellipse_single/{mirror}_300m.txt"
    cfg["num_bolts"] = len(bx)
    cfg["num_bolts_x"] = 0
    cfg["num_bolts_z"] = 0
    cfg["influence_data_path"] = bins_dir.replace(os.sep, "/")
    cfg["output_dir"] = out_dir.replace(os.sep, "/")
    cfg["iterations"] = iters
    cfg["bolt_l1_lambda"] = 0.0
    if init_file:
        cfg["bolt_init_file"] = init_file.replace(os.sep, "/")
        cfg["bolt_init_dir"] = ""
    else:
        cfg["bolt_init_file"] = ""
    if dump:
        cfg["dump_surface_grad"] = 1
        cfg["learning_rate"] = 0.0
        cfg["min_learning_rate"] = 0.0
    os.makedirs(os.path.join(ROOT, out_dir), exist_ok=True)
    cfg_path = os.path.join(ROOT, out_dir, "config.json")
    json.dump(cfg, open(cfg_path, "w"), indent=2)
    rc = run([EXE, "--config", cfg_path], os.path.join(ROOT, out_dir, "run.log"))
    if rc != 0:
        raise RuntimeError(f"renderer failed rc={rc} in {out_dir}")


def read_best(out_dir, mirror):
    path = os.path.join(ROOT, out_dir, f"{mirror}_300m_BEST_bolts.txt")
    vals = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = line.split()
            vals[int(p[0])] = float(p[1])
    return np.array([vals[i] for i in sorted(vals)])


def read_s95(out_dir, mirror):
    with open(os.path.join(ROOT, out_dir, SUMMARY)) as fh:
        for row in csv.DictReader(fh):
            if row["Position"] == mirror:
                return float(row["Best_S95(m2)"])
    raise RuntimeError(f"no summary for {mirror} in {out_dir}")


def write_init(out_dir, mirror, h, path):
    lines = ["# warm start", "# idx  h_pipe(m)"]
    lines += [f"{i} {v:.8g}" for i, v in enumerate(h)]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def load_G_total(dump_dir, mirror, gs=32):
    bin_path = os.path.join(ROOT, dump_dir, f"surface_grad_{mirror}.bin")
    n = os.path.getsize(bin_path) // (3 * gs * gs * 4)
    data = np.fromfile(bin_path, dtype=np.float32).reshape(n, 3, gs * gs)
    return (data[:, 0, :].sum(0).astype(np.float64),
            data[:, 1, :].sum(0).astype(np.float64),
            data[:, 2, :].sum(0).astype(np.float64))


def project_constraints(bx, bz):
    """Clamp to plate bounds + min gap (simple iterative projection)."""
    bx = np.clip(bx, -W / 2 + EDGE_MIN, W / 2 - EDGE_MIN)
    bz = np.clip(bz, -L / 2 + EDGE_MIN, L / 2 - EDGE_MIN)
    for _ in range(50):
        dx = bx[:, None] - bx[None, :]
        dz = bz[:, None] - bz[None, :]
        d = np.sqrt(dx * dx + dz * dz + np.eye(len(bx)))
        viol = (d < MIN_GAP) & (~np.eye(len(bx), dtype=bool))
        if not viol.any():
            break
        i, j = np.argwhere(viol)[0]
        ux = (bx[i] - bx[j]) / max(d[i, j], 1e-6)
        uz = (bz[i] - bz[j]) / max(d[i, j], 1e-6)
        push = (MIN_GAP - d[i, j]) / 2 + 1e-4
        bx[i] += ux * push; bx[j] -= ux * push
        bz[i] += uz * push; bz[j] -= uz * push
        bx = np.clip(bx, -W / 2 + EDGE_MIN, W / 2 - EDGE_MIN)
        bz = np.clip(bz, -L / 2 + EDGE_MIN, L / 2 - EDGE_MIN)
    return bx, bz


def max_edge_span(bx, bz, peri_idx):
    """Max nearest-neighbor gap among PERIMETER bolts (tracked by index from
    the initial grid — robust to bolts moving off their original lines).
    A bolt isolated from its perimeter neighbors = edge-gap precursor."""
    px, pz = bx[peri_idx], bz[peri_idx]
    dx = px[:, None] - px[None, :]
    dz = pz[:, None] - pz[None, :]
    d = np.sqrt(dx * dx + dz * dz) + np.eye(len(px)) * 1e9
    return float(d.min(axis=1).max()) if len(px) > 1 else 0.0


def perimeter_indices(bx, bz):
    """Perimeter bolt indices of a grid layout (outermost lines)."""
    ux = np.sort(np.unique(np.round(bx, 6)))
    uz = np.sort(np.unique(np.round(bz, 6)))
    return np.array([k for k in range(len(bx))
                     if abs(bx[k] - ux[0]) < 1e-6 or abs(bx[k] - ux[-1]) < 1e-6
                     or abs(bz[k] - uz[0]) < 1e-6 or abs(bz[k] - uz[-1]) < 1e-6])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mirror", required=True, choices=["North", "East", "South", "West"])
    ap.add_argument("--start-layout", default="configs/bolt_layouts/density/9x7_margin05.json")
    ap.add_argument("--steps", type=int, default=10)
    ap.add_argument("--sundir", choices=["36", "110"], default="36")
    ap.add_argument("--iters", type=int, default=100)
    ap.add_argument("--lr-pi", type=float, default=0.05, help="Adam lr on scaled positions")
    ap.add_argument("--template", default="configs/_fw_tanh_a0_110.json")
    ap.add_argument("--out-root", default="results_pos")
    args = ap.parse_args()

    template = json.load(open(os.path.join(ROOT, args.template)))
    sun = "data/36_sundir_fast.txt" if args.sundir == "36" else "data/110_sundir_paper.txt"
    template["sun_train_file"] = sun
    template["sun_validation_file"] = sun

    mir = args.mirror
    layout_path = os.path.join(ROOT, args.start_layout)
    _bx0, _bz0 = lu.bolt_positions(lu.load_layout(layout_path))
    peri_idx = perimeter_indices(_bx0, _bz0)   # tracked by index across steps
    history = []
    best_total = None
    best_layout = layout_path
    step_m = args.lr_pi * S_PI  # nominal first-step size (m); Adam handles the rest
    m1 = None; m2 = None
    b1, b2, eps = 0.9, 0.999, 1e-8

    for step in range(args.steps + 1):
        t0 = time.time()
        bins_dir = os.path.join("data_pos", mir, f"s{step:02d}")
        if not os.path.exists(os.path.join(ROOT, bins_dir, "influence_phi.bin")):
            make_bins(layout_path, bins_dir)
        # (1) inner h-opt
        inner_out = os.path.join(args.out_root, mir, f"s{step:02d}_inner")
        init_file = None
        if step > 0:
            init_file = os.path.join(args.out_root, mir, f"s{step:02d}_init.txt")
            write_init(args.out_root, mir, h_best, os.path.join(ROOT, init_file))
        render(layout_path, bins_dir, inner_out, mir, args.iters, template,
               init_file=init_file)
        s95 = read_s95(inner_out, mir)
        h_best = read_best(inner_out, mir)
        print(f"[{mir} s{step}] inner best S95={s95:.3f}", flush=True)
        # acceptance: any regression > 0.1% rejects the move and halves the step
        if best_total is not None and s95 > best_total * 1.001:
            print(f"  REGRESS {s95:.3f} vs best {best_total:.3f}; halve step to "
                  f"{step_m*500:.1f}mm and re-propose", flush=True)
            step_m /= 2.0
            if step_m < 1e-3:
                print("  step below 1mm, stop")
                break
            layout_path = best_layout
            # recompute the move from the SAME state/gradient (no re-render):
            # fall through to a fresh proposal by re-entering the loop body —
            # simplest: rewind layout and re-do this iteration's dump+gradient
            # (dump dir cached -> cheap); inner rerun only after acceptance.
            continue
        if best_total is None or s95 < best_total:
            best_total = s95
            best_layout = layout_path
        history.append({"step": step, "s95": s95, "layout": os.path.basename(layout_path)})
        if step == args.steps:
            break
        # (2) dump run at the optimized state
        dump_dir = os.path.join(args.out_root, mir, f"s{step:02d}_dump")
        init_file = os.path.join(args.out_root, mir, f"s{step:02d}_dump_init.txt")
        write_init(args.out_root, mir, h_best, os.path.join(ROOT, init_file))
        render(layout_path, bins_dir, dump_dir, mir, 1, template,
               init_file=init_file, dump=True)
        # (3)+(4) gradient
        GLy, GLyu, GLyv = load_G_total(dump_dir, mir)
        lay = lu.load_layout(layout_path)
        bx, bz = lu.bolt_positions(lay)
        dL = tps.position_sensitivity(bx, bz, h_best, GLy, GLyu, GLyv)
        n = len(bx)
        gmax = np.abs(dL).max()
        print(f"  |dL/dpi| max={gmax:.3e}; top-3: "
              + ", ".join(f"{'x' if i < n else 'z'}:{i % n}={dL[i]:+.2e}"
                          for i in np.argsort(-np.abs(dL))[:3]), flush=True)
        # (5) normalized gradient step: only the steepest coordinate moves
        # step_m; others scale proportionally (A4-proven update rule).
        n = len(bx)
        gmax = np.abs(dL).max()
        if gmax <= 0:
            print("  zero gradient, stop")
            break
        span_ref = max_edge_span(bx, bz, peri_idx)
        while True:
            dpi = -step_m * dL / gmax
            nbx = bx + dpi[:n]
            nbz = bz + dpi[n:]
            nbx, nbz = project_constraints(nbx, nbz)
            span = max_edge_span(nbx, nbz, peri_idx)
            if span <= max(1.15 * span_ref, span_ref + 0.05):
                break
            step_m /= 2.0
            print(f"  edge span {span:.2f}m > ref {span_ref:.2f}m, halve step to "
                  f"{step_m*1000:.1f}mm and re-propose", flush=True)
            if step_m < 1e-3:
                print("  step below 1mm, stop")
                break
        if step_m < 1e-3:
            break
        # (6) new layout
        new_layout = os.path.join(ROOT, "configs/bolt_layouts/free",
                                  f"p6_{mir.lower()}_s{step+1:02d}.json")
        json.dump({"description": f"Phase6 {mir} step {step+1}",
                   "bolt_positions": [[float(x), float(z)] for x, z in zip(nbx, nbz)],
                   "plate_width_m": W, "plate_length_m": L, "plate_thickness_m": 0.004,
                   "youngs_modulus_pa": 70000000000.0, "poisson_ratio": 0.22,
                   "density_kg_m3": 2500, "gravity_m_s2": 9.81,
                   "mesh_ndiv_x": 64, "mesh_ndiv_z": 48},
                  open(new_layout, "w"), indent=2)
        layout_path = new_layout
        print(f"  step {step+1} layout written; max move "
              f"{np.abs(np.concatenate([nbx - bx, nbz - bz])).max()*1000:.1f}mm "
              f"[{time.time()-t0:.0f}s]", flush=True)

    out_csv = os.path.join(ROOT, "analysis", f"pos_joint_path_{mir.lower()}.csv")
    with open(out_csv, "w", newline="") as fh:
        wcsv = csv.DictWriter(fh, fieldnames=["step", "s95", "layout"])
        wcsv.writeheader(); wcsv.writerows(history)
    print(f"\n[{mir}] done. path -> {out_csv}")
    print(f"[{mir}] best layout: {best_layout}  best S95={best_total:.3f}")


if __name__ == "__main__":
    main()
