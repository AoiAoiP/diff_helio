#!/usr/bin/env python3
"""Analyze 300-iteration optimization results.

Steps:
  1. Loss/S95 curve (dual-axis plot)
  2. Bolt height distribution heatmap
  3. Deformation validation (2 comparisons: no-grav vs TPS, 0deg-grav vs TPS+gravity)
  4. Sun direction & mirror tilt angle for zenith sun
"""

import sys, os, json, struct
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from scipy.interpolate import griddata

# ---- Paths ----
RESULT_DIR = "results_vsm_mnvn_300iter"
DATA_DIR = "data_vsm_mnvn_tik32"

# ---- Constants (matching validation_utils.py) ----
W, L = 12.84, 9.45
GS, NB = 32, 35
BX_list = np.array([(u - 0.5) * W for u in [0.08, 0.22, 0.36, 0.50, 0.64, 0.78, 0.92]])
BZ_list = np.array([(v - 0.5) * L for v in [0.08, 0.29, 0.50, 0.71, 0.92]])
X_GRID = np.linspace(-W/2, W/2, GS)
Z_GRID = np.linspace(-L/2, L/2, GS)
Xg, Zg = np.meshgrid(X_GRID, Z_GRID)

# ============================================================================
# STEP 1: Loss / S95 curve
# ============================================================================
def plot_loss_curve():
    history = np.loadtxt(f"{RESULT_DIR}/North_300m_history.csv", delimiter=",", skiprows=1)
    iters = history[:, 0].astype(int)
    loss = history[:, 1]
    s95 = history[:, 2]

    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax2 = ax1.twinx()

    ax1.plot(iters, loss, "steelblue", linewidth=1.2, alpha=0.8, label="Loss")
    ax1.set_xlabel("Iteration", fontsize=12)
    ax1.set_ylabel("Loss", color="steelblue", fontsize=12)
    ax1.tick_params(axis="y", labelcolor="steelblue")

    # S95: only plot validation points (every 10 iters)
    val_mask = np.zeros(len(iters), dtype=bool)
    prev = -1
    for i, (it, s) in enumerate(zip(iters, s95)):
        if it % 10 == 0 and s != prev:
            val_mask[i] = True
            prev = s
    val_iters = iters[val_mask]
    val_s95 = s95[val_mask]

    ax2.plot(val_iters, val_s95, "darkorange", marker="o", ms=4, linewidth=1.5, label="S95 (m²)")
    ax2.set_ylabel("S95 Area (m²)", color="darkorange", fontsize=12)
    ax2.tick_params(axis="y", labelcolor="darkorange")

    # Annotations
    ax2.axhline(52.68, color="green", linestyle="--", alpha=0.5, label="Best S95=52.68")
    ax2.axhline(43, color="red", linestyle=":", alpha=0.4, label="Ideal ellipse ~43 m²")
    ax2.annotate(f"Init S95={s95[0]:.1f}", xy=(0, s95[0]), fontsize=9, color="darkorange",
                 xytext=(10, s95[0]+8), arrowprops=dict(arrowstyle="->", color="gray", lw=0.8))
    ax2.annotate(f"Best S95={val_s95[-1]:.2f}", xy=(val_iters[-1], val_s95[-1]),
                 fontsize=10, color="green", fontweight="bold",
                 xytext=(val_iters[-1]-80, val_s95[-1]+5),
                 arrowprops=dict(arrowstyle="->", color="green", lw=0.8))

    # LR decay annotation
    ax1.annotate("LR decay zone\n(lr: 2e-4 → 1e-8)", xy=(150, loss[150]),
                 fontsize=9, color="gray",
                 xytext=(80, loss[0]*0.75),
                 arrowprops=dict(arrowstyle="->", color="gray", lw=0.8))

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=9)

    ax1.set_xlim(0, 300)
    ax1.set_title("North 300m — 300-Iter Optimization (Linear LR Decay)", fontsize=13, fontweight="bold")
    ax1.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(f"{RESULT_DIR}/loss_curve.png", dpi=150)
    plt.close(fig)
    print("[1] Loss curve saved to loss_curve.png")

# ============================================================================
# STEP 2: Bolt height distribution
# ============================================================================
def plot_bolt_distribution():
    strokes = np.loadtxt(f"{RESULT_DIR}/North_300m_STROKE_bolts.txt")
    strokes = strokes.reshape(5, 7)  # 5 rows (Z) × 7 cols (X), row-major

    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.imshow(strokes * 1000, cmap="RdYlBu_r", origin="lower",
                   extent=[BX_list[0]-0.92, BX_list[-1]+0.92, BZ_list[0]-1.0, BZ_list[-1]+1.0],
                   aspect="auto")
    cbar = fig.colorbar(im, ax=ax, label="Stroke (mm)")

    # Annotate each bolt
    for zi in range(5):
        for xi in range(7):
            val = strokes[zi, xi] * 1000
            ax.annotate(f"{val:.1f}", (BX_list[xi], BZ_list[zi]),
                        ha="center", va="center", fontsize=7,
                        color="white" if val > 35 else "black")

    ax.set_xlabel("Plate X (m)", fontsize=11)
    ax.set_ylabel("Plate Z (m)", fontsize=11)
    ax.set_title(f"Bolt Stroke Distribution (max={strokes.max()*1000:.1f} mm, min={strokes.min()*1000:.1f} mm)",
                 fontsize=12, fontweight="bold")
    ax.set_aspect("equal")

    # Mark center bolt (idx 17, zi=2, xi=3)
    ax.plot(BX_list[3], BZ_list[2], "ko", markersize=10, markerfacecolor="none", markeredgewidth=2)
    ax.annotate("min stroke\n(center)", (BX_list[3], BZ_list[2]),
                fontsize=8, ha="center", va="bottom", xytext=(0, -15), textcoords="offset points",
                color="black")

    fig.tight_layout()
    fig.savefig(f"{RESULT_DIR}/bolt_distribution.png", dpi=150)
    plt.close(fig)
    print(f"[2] Bolt distribution saved. max={strokes.max()*1000:.1f}mm, min={strokes.min()*1000:.1f}mm")

# ============================================================================
# STEP 3: Deformation validation
# ============================================================================
def load_influence_phi():
    """Load influence_phi.bin → (35, 25, 25)."""
    data = np.fromfile(f"{DATA_DIR}/influence_phi.bin", dtype=np.float32)
    return data.reshape(NB, GS, GS)

def load_gravity_0deg():
    """Load gravity_0deg.bin → (25, 25)."""
    return np.fromfile(f"{DATA_DIR}/gravity_0deg.bin", dtype=np.float32).reshape(GS, GS)

def load_fea_horizontal(path):
    """Load FEA node dump for HORIZONTAL plate (0 deg tilt).

    Plate is in XZ plane, plate normal = global Y.
    u_local = UY directly, no projection needed.
    Z_SCALE = 1.0 (no scaling).
    """
    data = np.loadtxt(path, delimiter=",", skiprows=1)
    x_plate = data[:, 0]  # NX → plate X
    z_plate = data[:, 2]  # NZ → plate Z
    u_local = data[:, 4]  # UY → plate-normal displacement

    # Interpolate to 25x25 grid
    u_grid = griddata((x_plate, z_plate), u_local, (Xg, Zg), method="linear")
    nan_mask = np.isnan(u_grid)
    if nan_mask.any():
        u_nn = griddata((x_plate, z_plate), u_local, (Xg, Zg), method="nearest")
        u_grid[nan_mask] = u_nn[nan_mask]

    return x_plate, z_plate, u_local, u_grid

def compute_proxy_surface(phi, bolt_strokes):
    """w(x,z) = sum_b h_b * phi_b(x,z)."""
    w = np.zeros((GS, GS))
    for b in range(NB):
        w += bolt_strokes[b] * phi[b]
    return w

def compare_with_fea(w_proxy, u_grid_fea, method_name, out_dir):
    """Compare proxy with FEA, return metrics. De-mean both fields first."""
    w_dm = w_proxy - np.mean(w_proxy)
    fea_dm = u_grid_fea - np.mean(u_grid_fea)
    residual = w_dm - fea_dm

    rms = np.sqrt(np.mean(residual**2)) * 1000
    max_err = np.max(np.abs(residual)) * 1000
    ss_res = np.sum(residual**2)
    ss_tot = np.sum((fea_dm - np.mean(fea_dm))**2)
    r2 = 1.0 - ss_res / max(ss_tot, 1e-20)
    pv_proxy = np.max(w_proxy) - np.min(w_proxy)
    pv_fea = np.max(u_grid_fea) - np.min(u_grid_fea)
    pv_ratio = pv_proxy / max(pv_fea, 1e-20)
    shape_corr = np.corrcoef(w_dm.ravel(), fea_dm.ravel())[0, 1]

    return {
        "method": method_name,
        "rms_mm": float(f"{rms:.3f}"),
        "max_err_mm": float(f"{max_err:.3f}"),
        "r2": float(f"{r2:.4f}"),
        "pv_ratio": float(f"{pv_ratio:.3f}"),
        "shape_corr": float(f"{shape_corr:.4f}"),
        "pv_proxy_mm": float(f"{pv_proxy*1000:.3f}"),
        "pv_fea_mm": float(f"{pv_fea*1000:.3f}"),
        "mean_proxy_mm": float(f"{np.mean(w_proxy)*1000:.3f}"),
        "mean_fea_mm": float(f"{np.mean(u_grid_fea)*1000:.3f}"),
    }


def plot_deformation_validation(metrics_list, w_proxy_ng, w_fea_ng, w_proxy_g, w_fea_g):
    """2-row x 3-col comparison figure."""
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))

    for row_idx, (w_proxy, w_fea, m) in enumerate([
        (w_proxy_ng, w_fea_ng, metrics_list[0]),
        (w_proxy_g, w_fea_g, metrics_list[1]),
    ]):
        w_proxy_dm = w_proxy - np.mean(w_proxy)
        w_fea_dm = w_fea - np.mean(w_fea)
        residual = w_proxy_dm - w_fea_dm
        vmax = max(np.max(np.abs(w_proxy_dm)), np.max(np.abs(w_fea_dm)))
        vmax_res = np.max(np.abs(residual))

        im0 = axes[row_idx, 0].imshow(w_proxy_dm * 1000, cmap="RdBu_r", origin="lower",
                                       extent=[-W/2, W/2, -L/2, L/2],
                                       vmin=-vmax*1000, vmax=vmax*1000, aspect="auto")
        axes[row_idx, 0].set_title(f"TPS Proxy\nPV={m['pv_proxy_mm']:.1f}mm", fontsize=10, fontweight="bold")
        axes[row_idx, 0].set_ylabel("Z (m)", fontsize=9)
        plt.colorbar(im0, ax=axes[row_idx, 0], label="mm")

        im1 = axes[row_idx, 1].imshow(w_fea_dm * 1000, cmap="RdBu_r", origin="lower",
                                       extent=[-W/2, W/2, -L/2, L/2],
                                       vmin=-vmax*1000, vmax=vmax*1000, aspect="auto")
        axes[row_idx, 1].set_title(f"FEA\nPV={m['pv_fea_mm']:.1f}mm", fontsize=10, fontweight="bold")
        plt.colorbar(im1, ax=axes[row_idx, 1], label="mm")

        im2 = axes[row_idx, 2].imshow(residual * 1000, cmap="RdBu_r", origin="lower",
                                       extent=[-W/2, W/2, -L/2, L/2],
                                       vmin=-vmax_res*1000, vmax=vmax_res*1000, aspect="auto")
        label = f"TPS Proxy (no gravity) vs FEA (no gravity)" if row_idx == 0 else \
                f"TPS Proxy + 0deg gravity vs FEA (0deg gravity)"
        axes[row_idx, 2].set_title(f"Residual\nRMS={m['rms_mm']:.2f}mm, R²={m['r2']:.3f}",
                                   fontsize=10, fontweight="bold")
        plt.colorbar(im2, ax=axes[row_idx, 2], label="mm")

        for ax in axes[row_idx]:
            ax.set_xlabel("X (m)", fontsize=9)

    fig.suptitle(f"Deformation Validation — North 300m (300-iter optimized bolts)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(f"{RESULT_DIR}/deformation_validation.png", dpi=150)
    plt.close(fig)
    print("[3] Deformation validation saved.")


def run_deformation_validation():
    phi = load_influence_phi()
    strokes = np.loadtxt(f"{RESULT_DIR}/North_300m_STROKE_bolts.txt")
    gravity_0 = load_gravity_0deg()

    # 3a: No-gravity comparison
    w_proxy_ng = compute_proxy_surface(phi, strokes)
    _, _, _, u_grid_nograv = load_fea_horizontal(f"{RESULT_DIR}/node_dump_nograv.csv")
    m1 = compare_with_fea(w_proxy_ng, u_grid_nograv, "TPS_nograv", RESULT_DIR)

    # 3b: 0deg gravity comparison
    w_proxy_g = gravity_0 + compute_proxy_surface(phi, strokes)
    _, _, _, u_grid_grav = load_fea_horizontal(f"{RESULT_DIR}/node_dump_0deg_grav.csv")
    m2 = compare_with_fea(w_proxy_g, u_grid_grav, "TPS_0deg_grav", RESULT_DIR)

    metrics = [m1, m2]
    with open(f"{RESULT_DIR}/deformation_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    for m in metrics:
        print(f"  {m['method']}: RMS={m['rms_mm']}mm, R2={m['r2']}, "
              f"PV_ratio={m['pv_ratio']}, shape_corr={m['shape_corr']}")

    plot_deformation_validation(metrics, w_proxy_ng, u_grid_nograv, w_proxy_g, u_grid_grav)
    return metrics


# ============================================================================
# STEP 4: Sun direction & mirror tilt angle
# ============================================================================
def compute_mirror_tilt():
    """Compute mirror tilt angle for zenith sun at North 300m."""
    sd = np.array([0.0, 1.0, 0.0])  # zenith (sun overhead)
    hp = np.array([0.0, 0.0, 300.0])  # North 300m
    ap = np.array([0.0, 180.0, 0.0])  # receiver

    r = ap - hp
    r_norm = r / np.linalg.norm(r)
    macro_normal = sd + r_norm
    macro_normal /= np.linalg.norm(macro_normal)
    cos_theta = abs(macro_normal[1])
    tilt_deg = np.degrees(np.arccos(cos_theta))

    print("\n" + "=" * 60)
    print("STEP 4: Sun Direction & Mirror Tilt")
    print("=" * 60)
    print(f"  Heliostat:    North 300m  [{hp[0]}, {hp[1]}, {hp[2]}]")
    print(f"  Receiver:     [{ap[0]}, {ap[1]}, {ap[2]}]")
    print(f"  Sun direction (zenith): [{sd[0]}, {sd[1]}, {sd[2]}]")
    print(f"  Reflection dir:        [{r_norm[0]:.4f}, {r_norm[1]:.4f}, {r_norm[2]:.4f}]")
    print(f"  Macro-normal:          [{macro_normal[0]:.4f}, {macro_normal[1]:.4f}, {macro_normal[2]:.4f}]")
    print(f"  cos(theta) = {cos_theta:.4f}")
    print(f"  Mirror tilt angle: {tilt_deg:.1f} deg from vertical")
    print(f"  (mirror elevation: {90-tilt_deg:.1f} deg from horizontal)")
    print()
    print("  → Use ANSYS with mirror tilted at {:.1f} deg from vertical".format(tilt_deg))
    print("    and the bolt strokes from North_300m_STROKE_bolts.txt")
    print("    to get the gravity-affected FEA point cloud for flux validation.")
    print("=" * 60)


# ============================================================================
if __name__ == "__main__":
    os.makedirs(RESULT_DIR, exist_ok=True)

    plot_loss_curve()
    plot_bolt_distribution()
    run_deformation_validation()
    compute_mirror_tilt()
    print("\nDone.")
