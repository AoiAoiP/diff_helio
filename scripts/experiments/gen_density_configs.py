#!/usr/bin/env python3
"""Batch generate bezier_opt configs for density scan experiment."""
import json, os, shutil
from pathlib import Path

ROOT = Path("L:/Code/bezier_opt_desktop/.claude/worktrees/add_prior_art_citations")

LAYOUTS = {
    "5x3_m05": {"nx": 5, "nz": 3, "nb": 15, "data": "data_proxy_density/5x3_margin05_fine",
                "init_dir": "data/init_comp_5x3/"},
    "7x5_m05": {"nx": 7, "nz": 5, "nb": 35, "data": "data_proxy_density/7x5_margin05_fine",
                "init_dir": "data/init_comp_7x5/"},
    "9x7_m05": {"nx": 9, "nz": 7, "nb": 63, "data": "data_proxy_density/9x7_margin05_fine",
                "init_dir": "data/init_comp_9x7/"},
    "11x9_m05": {"nx": 11, "nz": 9, "nb": 99, "data": "data_proxy_density/11x9_margin05_fine",
                 "init_dir": "data/init_comp_11x9/"},
}

MIRRORS = ["North_300m", "East_300m", "South_300m", "West_300m"]

TEMPLATE = {
    "sun_train_file": "data/110_sundir_paper.txt",
    "sun_validation_file": "data/110_sundir_paper.txt",
    "ellipse_file": "data/ellipse_news_300m.txt",
    "receiver_radius": 10.0, "receiver_height": 20.0,
    "pixel_width": 157, "pixel_height": 50,
    "heliostat_width": 12.84, "heliostat_length": 9.45,
    "grid_size": 32, "glass_depth": 0.004,
    "refractive_index": 1.523, "slope_error": 0.001,
    "reflectivity": 0.88, "sun_type": "buie",
    "dni": 1000.0, "csr": 0.01,
    "sun_sigma": 0.00251, "sun_theta_max": 0.00465,
    "iterations": 100, "learning_rate": 0.0004,
    "min_learning_rate": 0.0004,
    "beta1": 0.9, "beta2": 0.999, "adam_epsilon": 1e-08,
    "patience": 20, "energy_target": 1.0,
    "use_bolt": 1, "use_bspline": 0,
    "bolt_init_file": "auto",
    "samplePoolPow": 26,
    "gravity_normal_coupling": 1,
    "max_bolt_stroke": 0.06,
    "lambda_energy": 0.5,
    "stroke_regularization": 0.001,
}

os.chdir(ROOT)
os.makedirs("configs/density_scan", exist_ok=True)

for layout_key, lo in LAYOUTS.items():
    cfg = dict(TEMPLATE)
    cfg["num_bolts"] = lo["nb"]
    cfg["num_bolts_x"] = lo["nx"]
    cfg["num_bolts_z"] = lo["nz"]
    cfg["bolt_margin"] = 0.05
    cfg["influence_data_path"] = lo["data"]
    cfg["bolt_init_dir"] = lo["init_dir"]
    cfg["output_dir"] = f"results_density/{layout_key}"

    fname = f"configs/density_scan/{layout_key}.json"
    with open(fname, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"  {fname} (nb={lo['nb']}, init={lo['init_dir']})")

print(f"\nGenerated {len(LAYOUTS)} configs (4 mirrors each).")
