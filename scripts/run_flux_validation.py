#!/usr/bin/env python3
"""
Flux validation: compare optical flux distributions between TPS proxy and FEA surfaces.

For each FEA tilt angle (29.5°, 58.5°), finds the closest sun direction, generates
surface files (x z w) for both proxy and FEA, runs bezier_opt.exe --dump-flux,
and creates side-by-side comparison plots.

Usage:
  python scripts/run_flux_validation.py \
    --result-dir results_4mirror_200iter \
    --heliostat-prefix North \
    --fea-dir results_4mirror_200iter/fea_validation \
    --angles 29.5 58.5
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

ROOT = Path(__file__).resolve().parent.parent

# Resolve the real git repo root (works from worktrees too).
# In a worktree, .git is a file pointing to the main repo's gitdir.
def _git_root():
    # Try git command first
    try:
        r = subprocess.run(['git', 'rev-parse', '--git-common-dir'],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=10)
        if r.returncode == 0:
            # git-common-dir is the main .git dir; repo root is one level up
            git_dir = Path(r.stdout.strip())
            return git_dir.parent
    except Exception:
        pass
    # Fallback: look for .git file (worktree indicator)
    git_file = ROOT / '.git'
    if git_file.is_file():
        content = git_file.read_text()
        if content.startswith('gitdir:'):
            # gitdir: path/.git/worktrees/name -> repo root = dirname(dirname(path/.git))
            gitdir_path = content.split(':', 1)[1].strip()
            # gitdir_path points to ...\repo\.git\worktrees\name
            # repo root = parent of parent of parent
            p = Path(gitdir_path)
            return p.parent.parent  # .git/worktrees/name -> up 2 to .git's parent
    # Last resort: assume worktree is under .claude/worktrees/
    if '.claude' in str(ROOT) and 'worktrees' in str(ROOT):
        return ROOT.parent.parent.parent  # up from worktree/name -> .claude -> repo
    return ROOT

REPO_ROOT = _git_root()

# ── Paths ──
BEZIER_EXE = REPO_ROOT / "build/src/Release/bezier_opt.exe"
DEFAULT_CONFIG = REPO_ROOT / "configs/bolt_optimize_north_200iter.json"


# ══════════════════════════════════════════════════════════════════════════════
# Data loading (shared with run_fea_validation.py logic)
# ══════════════════════════════════════════════════════════════════════════════

def parse_stroke_file(path):
    """Parse STROKE_bolts.txt — one stroke value per line, zero-based, meters."""
    strokes = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                strokes.append(float(line))
            except ValueError:
                pass
    return strokes


def load_influence_functions(data_dir, grid_size=32):
    """Load TPS influence functions from data_proxy/*.bin files."""
    def _load(name):
        p = os.path.join(data_dir, name)
        if not os.path.exists(p):
            raise FileNotFoundError(f"Missing: {p}. Run generate_proxy_model.py tps first.")
        return np.fromfile(p, dtype=np.float32)

    phi_raw   = _load('influence_phi.bin')
    phi_u_raw = _load('influence_phi_u.bin')
    phi_v_raw = _load('influence_phi_v.bin')

    n_grid = grid_size * grid_size
    NB = len(phi_raw) // n_grid
    if NB * n_grid != len(phi_raw):
        raise ValueError(f"influence_phi.bin size {len(phi_raw)} not divisible by {n_grid}")

    phi   = phi_raw.reshape(NB, n_grid)
    phi_u = phi_u_raw.reshape(NB, n_grid)
    phi_v = phi_v_raw.reshape(NB, n_grid)
    return phi, phi_u, phi_v, NB


def load_gravity_bins(data_dir):
    """Load 20-bin gravity data and angle list."""
    meta_path = os.path.join(data_dir, 'gravity_angles.json')
    with open(meta_path) as f:
        meta = json.load(f)
    angles = sorted([float(k) for k in meta['angles'].keys()])
    GS = meta['grid_size']
    n_grid = GS * GS

    bins = np.zeros((len(angles), n_grid), dtype=np.float32)
    for i, ang in enumerate(angles):
        ang_int = int(ang) if ang == int(ang) else ang
        path = os.path.join(data_dir, f'gravity_{ang_int}deg.bin')
        if os.path.exists(path):
            raw = np.fromfile(path, dtype=np.float32)
            if len(raw) == n_grid:
                bins[i] = raw
    return bins, np.array(angles), GS


def interpolate_gravity(angle_deg, gravity_bins, gravity_angles):
    """Bilinear interpolation of gravity at target angle."""
    n_bins = len(gravity_angles)
    lo, hi = 0, n_bins - 1
    for i in range(n_bins - 1):
        if gravity_angles[i] <= angle_deg <= gravity_angles[i + 1]:
            lo, hi = i, i + 1
            break
    if angle_deg <= gravity_angles[0]:
        lo, hi = 0, 0
    if angle_deg >= gravity_angles[-1]:
        lo, hi = n_bins - 1, n_bins - 1
    if lo == hi:
        return gravity_bins[lo].copy()
    t = (angle_deg - gravity_angles[lo]) / (gravity_angles[hi] - gravity_angles[lo] + 1e-30)
    return (1.0 - t) * gravity_bins[lo] + t * gravity_bins[hi]


def compute_proxy_surface(bolt_strokes, phi, gravity):
    """Compute TPS proxy surface: w = gravity + Σ h_b·φ_b."""
    w = gravity.astype(np.float64).copy()
    for b in range(len(bolt_strokes)):
        if abs(bolt_strokes[b]) > 1e-12:
            w += bolt_strokes[b] * phi[b].astype(np.float64)
    return w


def fea_csv_to_plate_local(csv_path, angle_deg):
    """Load FEA 7-col CSV and transform to plate-local coordinates."""
    data = np.loadtxt(csv_path, delimiter=',', skiprows=1)
    theta = np.radians(angle_deg)
    cos_t, sin_t = np.cos(theta), np.sin(theta)

    x_local = data[:, 0]
    z_local = data[:, 2] / max(cos_t, 1e-6)
    uy, uz = data[:, 4], data[:, 5]
    w_fea = uy * cos_t + uz * sin_t

    return x_local, z_local, w_fea


def interpolate_fea_to_grid(x_local, z_local, w_fea, grid_size=32):
    """Interpolate scattered FEA displacement to pixel-centered render grid."""
    from scipy.interpolate import griddata as gd

    W, L = 12.84, 9.45
    u = (np.arange(grid_size) + 0.5) / grid_size
    x_grid = (u - 0.5) * W
    z_grid = (u - 0.5) * L
    Xg, Zg = np.meshgrid(x_grid, z_grid)

    w_grid = gd((x_local, z_local), w_fea, (Xg, Zg), method='linear')
    nan_mask = np.isnan(w_grid)
    if nan_mask.any():
        w_nn = gd((x_local, z_local), w_fea, (Xg, Zg), method='nearest')
        w_grid[nan_mask] = w_nn[nan_mask]
        print(f"    Interpolation: {nan_mask.sum()}/{grid_size*grid_size} NaN points filled")

    return w_grid, Xg, Zg


# ══════════════════════════════════════════════════════════════════════════════
# Sun direction → tilt angle mapping
# ══════════════════════════════════════════════════════════════════════════════

def load_sun_directions(path):
    """Load sun direction file (one direction per line: sx sy sz)."""
    dirs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 3:
                dirs.append(np.array([float(parts[0]), float(parts[1]), float(parts[2])]))
    return dirs


def mirror_tilt_angle(sun_dir, helio_pos, receiver_pos):
    """Compute mirror tilt angle from horizontal (degrees) for given sun direction.

    Mirror normal bisects sun direction and direction to receiver.
    Tilt angle = acos(n_y), where n is the mirror normal (plate faces upward).
    """
    r_vec = np.array(receiver_pos) - np.array(helio_pos)
    r_dir = r_vec / np.linalg.norm(r_vec)
    s_dir = np.array(sun_dir) / np.linalg.norm(sun_dir)
    normal = s_dir + r_dir
    normal = normal / np.linalg.norm(normal)
    cos_tilt = abs(normal[1])
    tilt_rad = np.arccos(np.clip(cos_tilt, 0.0, 1.0))
    return np.degrees(tilt_rad)


def find_closest_sun_direction(target_angle, sun_dirs, helio_pos, receiver_pos):
    """Find sun direction whose mirror tilt is closest to target_angle.

    Returns (index, sun_dir, actual_tilt_angle).
    """
    best_idx, best_dir, best_tilt, best_diff = 0, sun_dirs[0], 0.0, 1e9
    for i, sd in enumerate(sun_dirs):
        tilt = mirror_tilt_angle(sd, helio_pos, receiver_pos)
        diff = abs(tilt - target_angle)
        if diff < best_diff:
            best_idx, best_dir, best_tilt, best_diff = i, sd, tilt, diff
    return best_idx, best_dir, best_tilt


def synthetic_sun_for_tilt(target_tilt_deg, helio_pos, receiver_pos):
    """Compute a synthetic sun direction that produces exactly the target mirror tilt.

    For a north-south aligned system (heliostat at (0,0,-d), receiver at (0,H,0)),
    the mirror azimuth is purely south-facing. We solve for the sun direction s
    such that the mirror normal n = normalize(s + r) has the target tilt.

    Returns a unit vector (sx, sy, sz) representing the sun direction.
    """
    r_vec = np.array(receiver_pos) - np.array(helio_pos)
    r_dir = r_vec / np.linalg.norm(r_vec)

    theta = np.radians(target_tilt_deg)
    n_y = np.cos(theta)

    # For a north heliostat with south-facing mirror:
    # n_x = 0 (no E-W component), n_z = sqrt(1 - n_y²) (south-facing)
    n_z = np.sqrt(max(1.0 - n_y * n_y, 0.0))
    normal = np.array([0.0, n_y, n_z])

    # Reflect: s = 2(n·r)n - r
    n_dot_r = np.dot(normal, r_dir)
    s_dir = 2.0 * n_dot_r * normal - r_dir

    # Normalize (should be nearly unit already)
    s_dir = s_dir / np.linalg.norm(s_dir)

    return s_dir


def get_sun_for_tilt(target_angle, sun_dirs, helio_pos, receiver_pos, max_diff_deg=1.0):
    """Get a sun direction for a target tilt angle.

    If a sun direction from the file matches within max_diff_deg, use it.
    Otherwise, synthesize one that produces the exact tilt.

    Returns (sun_idx_or_neg, sun_dir, actual_tilt).
      sun_idx_or_neg: index in sun_dirs if from file, -1 if synthetic.
    """
    idx, sd, tilt = find_closest_sun_direction(target_angle, sun_dirs, helio_pos, receiver_pos)
    diff = abs(tilt - target_angle)

    if diff <= max_diff_deg:
        return idx, sd, tilt
    else:
        syn_dir = synthetic_sun_for_tilt(target_angle, helio_pos, receiver_pos)
        syn_tilt = mirror_tilt_angle(syn_dir, helio_pos, receiver_pos)
        return -1, syn_dir, syn_tilt


# ══════════════════════════════════════════════════════════════════════════════
# Surface file generation (format: x z uy, grid_size² points)
# ══════════════════════════════════════════════════════════════════════════════

def write_surface_file(path, w_grid, grid_size=32):
    """Write surface file in format expected by bezier_opt.exe --surface-file.

    Format: x z uy (one point per line, grid_size² points, row-major over z then x).
    """
    W, L = 12.84, 9.45
    u = (np.arange(grid_size) + 0.5) / grid_size
    x_vals = (u - 0.5) * W
    z_vals = (u - 0.5) * L

    w_2d = w_grid.reshape(grid_size, grid_size)
    with open(path, 'w') as f:
        f.write(f"# Surface file: {grid_size}x{grid_size} points, x z uy(m)\n")
        for iz in range(grid_size):
            for ix in range(grid_size):
                f.write(f"{x_vals[ix]:.6f} {z_vals[iz]:.6f} {w_2d[iz, ix]:.9f}\n")


# ══════════════════════════════════════════════════════════════════════════════
# Flux dump runner
# ══════════════════════════════════════════════════════════════════════════════

def run_flux_dump(surface_file, sun_file, config_path, output_dir, exe):
    """Run bezier_opt.exe --dump-flux --surface-file <f> and return flux file paths.

    Runs from the exe's directory (where shaders/ lives).
    Returns dict mapping sun_index → flux file path.
    """
    exe_dir = str(Path(exe).parent)  # build/src/Release/ — has shaders/
    cmd = [
        str(exe),
        "--dump-flux",
        "--config", str(Path(config_path).absolute()),
        "--surface-file", str(Path(surface_file).absolute()),
    ]
    env = os.environ.copy()
    env['BEZIER_S95_GPU'] = '1'

    print(f"    Running: bezier_opt.exe --dump-flux --config ... --surface-file ...")
    result = subprocess.run(cmd, cwd=exe_dir, capture_output=True, text=True,
                           encoding='utf-8', errors='replace',
                           timeout=300, env=env)

    if result.returncode != 0:
        print(f"    STDOUT (last 500 chars): {result.stdout[-500:]}")
        print(f"    STDERR (last 500 chars): {result.stderr[-500:]}")
        raise RuntimeError(f"bezier_opt.exe failed with code {result.returncode}")

    # Parse output to find saved flux files
    flux_files = {}
    for line in result.stdout.splitlines():
        if "Saved flux:" in line:
            path = line.split("Saved flux:")[1].strip().split()[0]
            m = re.search(r'sun(\d+)_flux', os.path.basename(path))
            if m:
                flux_files[int(m.group(1))] = path

    if not flux_files:
        print(f"    STDOUT: {result.stdout[-1000:]}")
        raise RuntimeError("No flux files found in output")

    print(f"    Flux files: {[os.path.basename(p) for p in flux_files.values()]}")
    return flux_files


def load_flux_npy(path):
    """Load a flux NPY file."""
    with open(path, 'rb') as f:
        magic = f.read(6)
        if magic != b'\x93NUMPY':
            raise ValueError(f"Not a NPY file: {path}")
        f.read(2)  # version
        header_len = int.from_bytes(f.read(2), 'little')
        header = f.read(header_len).decode('utf-8')
        shape_match = re.search(r"'shape':\s*\(([^)]+)\)", header)
        shape = tuple(int(x.strip()) for x in shape_match.group(1).split(',') if x.strip())
        data = np.frombuffer(f.read(), dtype=np.float32)
        return data.reshape(shape)


# ══════════════════════════════════════════════════════════════════════════════
# Metrics
# ══════════════════════════════════════════════════════════════════════════════

def compute_s95_area(flux):
    """Compute S95 area (number of brightest pixels containing 95% energy)."""
    f = flux.ravel()
    total = f.sum()
    if total <= 0:
        return 0.0
    sorted_f = np.sort(f)[::-1]
    cumsum = np.cumsum(sorted_f)
    idx = np.searchsorted(cumsum, 0.95 * total)
    return float(idx + 1)


def compute_flux_metrics(flux_proxy, flux_fea):
    """Compute comparison metrics between two flux distributions."""
    fp = flux_proxy.ravel().astype(np.float64)
    ff = flux_fea.ravel().astype(np.float64)

    # Normalize to same total energy for fair comparison
    fp = fp / fp.sum() * ff.sum()

    diff = fp - ff
    rms = np.sqrt(np.mean(diff ** 2))
    max_flux = max(fp.max(), ff.max())
    nrmse = rms / max(max_flux, 1e-10)

    fp_dm = fp - np.mean(fp)
    ff_dm = ff - np.mean(ff)
    num = np.sum(fp_dm * ff_dm)
    den = np.sqrt(np.sum(fp_dm ** 2) * np.sum(ff_dm ** 2))
    corr = float(num / max(den, 1e-30))

    s95_p = compute_s95_area(fp)
    s95_f = compute_s95_area(ff)

    return {
        'nrmse': float(nrmse),
        'rms_flux': float(rms),
        'corr': corr,
        's95_proxy': s95_p,
        's95_fea': s95_f,
        's95_diff_pct': float((s95_p - s95_f) / max(s95_f, 1) * 100),
        'max_flux': float(max_flux),
        'total_proxy': float(fp.sum()),
        'total_fea': float(ff.sum()),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Plotting
# ══════════════════════════════════════════════════════════════════════════════

def _s95_threshold(flux):
    """Return the flux value that defines the S95 contour (95% energy containment)."""
    f = flux.ravel()
    total = f.sum()
    if total <= 0:
        return 0.0
    sorted_f = np.sort(f)[::-1]
    cumsum = np.cumsum(sorted_f)
    idx = np.searchsorted(cumsum, 0.95 * total)
    idx = min(idx, len(sorted_f) - 1)
    return float(sorted_f[idx])


def plot_flux_comparison(flux_proxy, flux_fea, angle_deg, sun_idx, metrics, out_dir):
    """Create side-by-side flux comparison figure with S95 contours and denoising."""
    from scipy.ndimage import gaussian_filter

    fp = flux_proxy.astype(np.float64).copy()
    ff = flux_fea.astype(np.float64).copy()

    # Normalize to same total
    fp = fp / fp.sum() * ff.sum()

    # Denoise with mild Gaussian filter
    fp_smooth = gaussian_filter(fp, sigma=0.8)
    ff_smooth = gaussian_filter(ff, sigma=0.8)

    # Compute S95 thresholds on smoothed data
    s95_thresh_p = _s95_threshold(fp_smooth)
    s95_thresh_f = _s95_threshold(ff_smooth)

    diff = fp_smooth - ff_smooth
    vm = max(fp_smooth.max(), ff_smooth.max()) * 0.95
    vm_diff = max(abs(diff).max(), 1e-6)

    fig = plt.figure(figsize=(18, 8))
    gs = GridSpec(2, 3, figure=fig, hspace=0.4, wspace=0.35,
                  width_ratios=[1, 1, 1], height_ratios=[1, 0.5])

    titles = [
        f'TPS Proxy Flux\nS95={metrics["s95_proxy"]:.0f} px',
        f'FEA Flux ({angle_deg:.1f}°)\nS95={metrics["s95_fea"]:.0f} px',
        f'Difference (Proxy − FEA)\nNRMSE={metrics["nrmse"]:.4f}  corr={metrics["corr"]:.4f}'
    ]
    data_list = [fp_smooth, ff_smooth, diff]
    # Coolwarm = red-white-blue for flux; RdBu_r for difference
    cmaps = ['coolwarm', 'coolwarm', 'RdBu_r']
    vmins = [(0, vm), (0, vm), (-vm_diff, vm_diff)]

    ny, nx = fp.shape
    for col in range(3):
        ax = fig.add_subplot(gs[0, col])
        im = ax.imshow(data_list[col], cmap=cmaps[col], aspect='auto',
                       vmin=vmins[col][0], vmax=vmins[col][1],
                       extent=[0, nx, 0, ny], origin='lower')
        ax.set_title(titles[col], fontsize=10, fontweight='bold')
        ax.set_xlabel('Azimuth pixel'); ax.set_ylabel('Height pixel')
        plt.colorbar(im, ax=ax, label='W/m²' if col < 2 else 'Δ W/m²')

        # S95 contour line on flux plots
        if col == 0:
            ax.contour(fp_smooth, levels=[s95_thresh_p], colors='black',
                      linewidths=1.5, linestyles='--', extent=[0, nx, 0, ny], origin='lower')
        elif col == 1:
            ax.contour(ff_smooth, levels=[s95_thresh_f], colors='black',
                      linewidths=1.5, linestyles='--', extent=[0, nx, 0, ny], origin='lower')

    # Row 2 left: horizontal profile (mid-height) with S95 markers
    ax_h = fig.add_subplot(gs[1, 0])
    mid_row = ny // 2
    ax_h.plot(fp_smooth[mid_row, :], 'b-', lw=1.5, label='TPS Proxy')
    ax_h.plot(ff_smooth[mid_row, :], 'r--', lw=1.5, label='FEA')
    ax_h.axhline(y=s95_thresh_p, color='blue', ls=':', alpha=0.5, label=f'S95 proxy')
    ax_h.axhline(y=s95_thresh_f, color='red', ls=':', alpha=0.5, label=f'S95 FEA')
    ax_h.set_xlabel('Azimuth pixel'); ax_h.set_ylabel('Flux (W/m²)')
    ax_h.set_title(f'Horizontal profile (mid-height)', fontsize=9, fontweight='bold')
    ax_h.legend(fontsize=6); ax_h.grid(True, alpha=0.3)

    # Row 2 middle: vertical profile (mid-azimuth) with S95 markers
    ax_v = fig.add_subplot(gs[1, 1])
    mid_col = nx // 2
    ax_v.plot(fp_smooth[:, mid_col], 'b-', lw=1.5, label='TPS Proxy')
    ax_v.plot(ff_smooth[:, mid_col], 'r--', lw=1.5, label='FEA')
    ax_v.axhline(y=s95_thresh_p, color='blue', ls=':', alpha=0.5)
    ax_v.axhline(y=s95_thresh_f, color='red', ls=':', alpha=0.5)
    ax_v.set_xlabel('Height pixel'); ax_v.set_ylabel('Flux (W/m²)')
    ax_v.set_title(f'Vertical profile (mid-azimuth)', fontsize=9, fontweight='bold')
    ax_v.legend(fontsize=7); ax_v.grid(True, alpha=0.3)

    # Row 2 right: metrics table
    ax_tbl = fig.add_subplot(gs[1, 2])
    ax_tbl.axis('off')
    tbl = (
        f"Flux Comparison — {angle_deg:.1f}°\n"
        f"{'='*42}\n"
        f"  NRMSE:           {metrics['nrmse']:.6f}\n"
        f"  RMS flux:        {metrics['rms_flux']:.3f} W/m²\n"
        f"  Correlation:     {metrics['corr']:.6f}\n"
        f"  S95 proxy:       {metrics['s95_proxy']:.0f} px\n"
        f"  S95 FEA:         {metrics['s95_fea']:.0f} px\n"
        f"  S95 diff:        {metrics['s95_diff_pct']:+.1f}%\n"
        f"  Max flux:        {metrics['max_flux']:.1f} W/m²\n"
        f"  Total proxy:     {metrics['total_proxy']:.0f} W\n"
        f"  Total FEA:       {metrics['total_fea']:.0f} W\n"
        f"{'='*42}\n"
    )
    ax_tbl.text(0.05, 0.95, tbl, transform=ax_tbl.transAxes,
                fontsize=8.5, fontfamily='monospace', va='top',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

    fig.suptitle(f'Flux Comparison: TPS Proxy vs FEA — {angle_deg:.1f}° tilt (sun #{sun_idx})',
                 fontsize=12, fontweight='bold', y=0.98)

    png_path = os.path.join(out_dir, f'flux_comparison_{angle_deg:.1f}deg.png')
    plt.savefig(png_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"    Plot saved: {png_path}")
    return png_path


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Flux validation: compare optical flux between TPS proxy and FEA surfaces")
    parser.add_argument('--result-dir', required=True,
                        help='Result directory containing *_STROKE_bolts.txt')
    parser.add_argument('--heliostat-prefix', default='North',
                        help='Prefix to filter stroke files')
    parser.add_argument('--fea-dir', required=True,
                        help='Directory containing FEA node_dump_*deg.csv files')
    parser.add_argument('--angles', type=float, nargs='+', default=[29.5, 58.5],
                        help='Tilt angles for FEA validation')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG),
                        help='Base config file for optical simulation')
    parser.add_argument('--output-dir', default=None,
                        help='Output directory (default: <fea_dir>/flux_validation/)')
    parser.add_argument('--influence-dir', default='data_proxy',
                        help='Path to influence/gravity data')
    parser.add_argument('--sun-file', default='data/36_sundir_fast.txt',
                        help='Sun directions file')
    parser.add_argument('--exe', default=str(BEZIER_EXE),
                        help='Path to bezier_opt.exe')
    args = parser.parse_args()

    # ── Resolve paths ──
    def resolve(p, root=REPO_ROOT):
        return str(root / p) if not os.path.isabs(p) else p

    result_dir = resolve(args.result_dir)
    fea_dir = resolve(args.fea_dir)
    influence_dir = resolve(args.influence_dir, REPO_ROOT)
    sun_file = resolve(args.sun_file, REPO_ROOT)
    config_path = resolve(args.config, REPO_ROOT)
    exe_path = resolve(args.exe, REPO_ROOT)

    out_dir = args.output_dir if args.output_dir else os.path.join(fea_dir, 'flux_validation')
    os.makedirs(out_dir, exist_ok=True)

    # ── Find stroke file ──
    stroke_candidates = []
    for f in os.listdir(result_dir):
        if f.endswith('_STROKE_bolts.txt') and args.heliostat_prefix in f:
            stroke_candidates.append(os.path.join(result_dir, f))
    if not stroke_candidates:
        print(f"ERROR: No *_STROKE_bolts.txt with prefix '{args.heliostat_prefix}' in {result_dir}")
        sys.exit(1)
    stroke_path = stroke_candidates[0]
    helio_name = os.path.basename(stroke_path).replace('_STROKE_bolts.txt', '')
    print(f"=== Flux Validation: {helio_name} ===")
    print(f"  Stroke file: {stroke_path}")
    print(f"  FEA dir:     {fea_dir}")
    print(f"  Output:      {out_dir}/")

    # ── Load data ──
    strokes = np.array(parse_stroke_file(stroke_path), dtype=np.float64)
    print(f"  Bolts: {len(strokes)}, stroke range [{strokes.min()*1000:.1f}, {strokes.max()*1000:.1f}] mm")

    phi, phi_u, phi_v, NB = load_influence_functions(influence_dir)
    if len(strokes) != NB:
        print(f"  WARN: {len(strokes)} strokes vs {NB} bolts")
        NB = min(len(strokes), NB)
    gravity_bins, gravity_angles, GS = load_gravity_bins(influence_dir)

    sun_dirs = load_sun_directions(sun_file)
    print(f"  Sun dirs: {len(sun_dirs)} directions loaded")

    # Fixed geometry: North heliostat at (0,0,-300), receiver at (0,180,0)
    helio_pos = (0.0, 0.0, -300.0)
    receiver_pos = (0.0, 180.0, 0.0)

    # ── Process each angle ──
    all_results = []
    temp_dir = os.path.join(out_dir, '_tmp')
    os.makedirs(temp_dir, exist_ok=True)

    for angle in args.angles:
        print(f"\n{'─'*60}")
        print(f"  Processing {angle:.1f}°")
        print(f"{'─'*60}")

        # 1. Get matching sun direction (from file or synthetic)
        sun_idx, sun_dir, actual_tilt = get_sun_for_tilt(
            angle, sun_dirs, helio_pos, receiver_pos, max_diff_deg=1.0)
        tag = f"#{sun_idx}" if sun_idx >= 0 else "synthetic"
        print(f"  Sun dir: {tag} tilt={actual_tilt:.3f}° (target {angle:.1f}°)")
        print(f"  Sun direction: ({sun_dir[0]:.4f}, {sun_dir[1]:.4f}, {sun_dir[2]:.4f})")

        # 2. Generate proxy surface
        gravity = interpolate_gravity(actual_tilt, gravity_bins, gravity_angles)
        w_proxy = compute_proxy_surface(strokes[:NB], phi[:NB], gravity)
        proxy_surface_file = os.path.join(temp_dir, f"proxy_surface_{angle:.1f}deg.txt")
        write_surface_file(proxy_surface_file, w_proxy, GS)
        print(f"  Proxy surface: PV={np.ptp(w_proxy)*1000:.2f}mm")

        # 3. Generate FEA surface
        fea_csv = os.path.join(fea_dir, f"node_dump_{str(angle).replace('.', '')}deg.csv")
        if not os.path.exists(fea_csv):
            alt = os.path.join(fea_dir, f"node_dump_{angle:.1f}deg.csv")
            if os.path.exists(alt):
                fea_csv = alt
        if not os.path.exists(fea_csv):
            print(f"  ERROR: FEA CSV not found: {fea_csv}")
            continue

        x_local, z_local, w_fea_scatter = fea_csv_to_plate_local(fea_csv, angle)
        w_fea_grid, Xg, Zg = interpolate_fea_to_grid(x_local, z_local, w_fea_scatter, GS)
        fea_surface_file = os.path.join(temp_dir, f"fea_surface_{angle:.1f}deg.txt")
        write_surface_file(fea_surface_file, w_fea_grid, GS)
        print(f"  FEA surface: PV={np.ptp(w_fea_grid)*1000:.2f}mm")

        # 4. Create temp sun file with single direction
        temp_sun_file = os.path.join(temp_dir, f"sun_{angle:.1f}deg.txt")
        with open(temp_sun_file, 'w') as f:
            f.write(f"{sun_dir[0]:.6f} {sun_dir[1]:.6f} {sun_dir[2]:.6f}\n")

        # 5. Create temp config (use absolute paths since cwd will be exe dir)
        with open(config_path) as f:
            cfg = json.load(f)
        cfg['sun_train_file'] = os.path.abspath(temp_sun_file)
        cfg['sun_validation_file'] = os.path.abspath(temp_sun_file)
        # Resolve any relative paths in config to absolute (based on repo root)
        for key in ['ellipse_file', 'influence_data_path']:
            if key in cfg and not os.path.isabs(cfg[key]):
                cfg[key] = str(REPO_ROOT / cfg[key])
        flux_out_subdir = os.path.join(temp_dir, f"flux_out_{angle:.1f}deg")
        os.makedirs(flux_out_subdir, exist_ok=True)
        cfg['output_dir'] = os.path.abspath(flux_out_subdir)
        temp_config = os.path.join(temp_dir, f"config_{angle:.1f}deg.json")
        with open(temp_config, 'w') as f:
            json.dump(cfg, f, indent=2)

        # 6. Run flux dump for proxy
        print(f"  Running flux dump (proxy)...")
        cfg_proxy = dict(cfg)
        flux_out_proxy = os.path.join(temp_dir, f"flux_out_{angle:.1f}deg_proxy")
        os.makedirs(flux_out_proxy, exist_ok=True)
        cfg_proxy['output_dir'] = os.path.abspath(flux_out_proxy)
        temp_config_proxy = os.path.join(temp_dir, f"config_{angle:.1f}deg_proxy.json")
        with open(temp_config_proxy, 'w') as f:
            json.dump(cfg_proxy, f, indent=2)
        try:
            proxy_flux_files = run_flux_dump(proxy_surface_file, temp_sun_file,
                                            temp_config_proxy, flux_out_proxy, exe_path)
        except Exception as e:
            print(f"  ERROR running proxy flux: {e}")
            continue

        # 7. Run flux dump for FEA
        print(f"  Running flux dump (FEA)...")
        cfg_fea = dict(cfg)
        flux_out_fea = os.path.join(temp_dir, f"flux_out_{angle:.1f}deg_fea")
        os.makedirs(flux_out_fea, exist_ok=True)
        cfg_fea['output_dir'] = os.path.abspath(flux_out_fea)
        temp_config_fea = os.path.join(temp_dir, f"config_{angle:.1f}deg_fea.json")
        with open(temp_config_fea, 'w') as f:
            json.dump(cfg_fea, f, indent=2)
        try:
            fea_flux_files = run_flux_dump(fea_surface_file, temp_sun_file,
                                          temp_config_fea, flux_out_fea, exe_path)
        except Exception as e:
            print(f"  ERROR running FEA flux: {e}")
            continue

        # 8. Compare
        sun_key = 0
        if sun_key not in proxy_flux_files or sun_key not in fea_flux_files:
            print(f"  ERROR: Missing flux output files")
            continue

        flux_proxy = load_flux_npy(proxy_flux_files[sun_key])
        flux_fea = load_flux_npy(fea_flux_files[sun_key])

        print(f"  Flux proxy: shape={flux_proxy.shape}, sum={flux_proxy.sum():.1f}, max={flux_proxy.max():.1f}")
        print(f"  Flux FEA:   shape={flux_fea.shape}, sum={flux_fea.sum():.1f}, max={flux_fea.max():.1f}")

        metrics = compute_flux_metrics(flux_proxy, flux_fea)
        metrics['angle_deg'] = angle
        metrics['actual_tilt'] = float(actual_tilt)
        metrics['sun_idx'] = int(sun_idx)
        metrics['sun_synthetic'] = (sun_idx < 0)

        print(f"  Results: NRMSE={metrics['nrmse']:.4f}, corr={metrics['corr']:.4f}, "
              f"S95 proxy={metrics['s95_proxy']:.0f}, S95 FEA={metrics['s95_fea']:.0f} "
              f"({metrics['s95_diff_pct']:+.1f}%)")

        # 9. Plot
        plot_flux_comparison(flux_proxy, flux_fea, angle, sun_idx, metrics, out_dir)

        # 10. Save metrics + NPY
        metrics_path = os.path.join(out_dir, f'flux_metrics_{angle:.1f}deg.json')
        with open(metrics_path, 'w') as f:
            json.dump(metrics, f, indent=2)

        for label, flux_path in [('proxy', proxy_flux_files[sun_key]), ('fea', fea_flux_files[sun_key])]:
            dest = os.path.join(out_dir, f'flux_{label}_{angle:.1f}deg.npy')
            shutil.copy(flux_path, dest)

        all_results.append(metrics)

    # ── Summary ──
    if all_results:
        summary_path = os.path.join(out_dir, 'flux_comparison_summary.json')
        with open(summary_path, 'w') as f:
            json.dump(all_results, f, indent=2)

        print(f"\n{'='*75}")
        print(f"  Flux Comparison Summary")
        print(f"{'='*75}")
        print(f"  {'Angle':<8s} {'Tilt':<8s} {'NRMSE':>8s} {'Corr':>8s} {'S95_proxy':>10s} {'S95_FEA':>10s} {'ΔS95%':>8s}")
        print(f"  {'-'*65}")
        for m in all_results:
            print(f"  {m['angle_deg']:<8.1f} {m['actual_tilt']:<8.2f} "
                  f"{m['nrmse']:8.4f} {m['corr']:8.4f} "
                  f"{m['s95_proxy']:10.0f} {m['s95_fea']:10.0f} {m['s95_diff_pct']:7.1f}%")
        print(f"  {'='*65}")

    print(f"\n=== Done. Output: {out_dir}/ ===")
    for f in sorted(os.listdir(out_dir)):
        fpath = os.path.join(out_dir, f)
        if os.path.isfile(fpath):
            size_kb = os.path.getsize(fpath) / 1024
            print(f"  {f}  ({size_kb:.1f} KB)")

    # Cleanup temp
    shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
