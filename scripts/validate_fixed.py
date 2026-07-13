#!/usr/bin/env python3
"""Full validation: deformation (4 conditions) + flux (29.5 deg zenith sun)."""
import sys, os, json, struct, glob, re, subprocess
import numpy as np
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, 'proxy')

DATA_DIR = 'data_vsm_mnvn_tik32'
RESULT_DIR = 'results_vsm_mnvn_300iter'
OUT_DIR = 'validation_fixed'
EXE = os.path.join(ROOT, 'build/src/Release/bezier_opt.exe')
os.makedirs(OUT_DIR, exist_ok=True)

W, L = 12.84, 9.45
GS, NB = 32, 35
X_GRID = np.linspace(-W/2, W/2, GS)
Z_GRID = np.linspace(-L/2, L/2, GS)
Xg, Zg = np.meshgrid(X_GRID, Z_GRID)

# Load influence and strokes
phi = np.fromfile(f'{DATA_DIR}/influence_phi.bin', dtype=np.float32).reshape(NB, GS, GS)
strokes = np.loadtxt(f'{RESULT_DIR}/North_300m_STROKE_bolts.txt')
print(f'Bolt strokes: max={strokes.max()*1000:.1f}mm, PV={strokes.max()*1000-strokes.min()*1000:.1f}mm')

# Load gravity bins
g0  = np.fromfile(f'{DATA_DIR}/gravity_0deg.bin',  dtype=np.float32).reshape(GS, GS)
g30 = np.fromfile(f'{DATA_DIR}/gravity_30deg.bin', dtype=np.float32).reshape(GS, GS)
g45 = np.fromfile(f'{DATA_DIR}/gravity_45deg.bin', dtype=np.float32).reshape(GS, GS)
g60 = np.fromfile(f'{DATA_DIR}/gravity_60deg.bin', dtype=np.float32).reshape(GS, GS)

def compute_gravity(tilt_deg):
    angles = np.array([0, 30, 45, 60, 75])
    bins = [g0, g30, g45, g60, None]  # 75 not loaded
    if tilt_deg <= 0: return g0
    if tilt_deg >= 60: return bins[3]
    for i in range(len(angles)-1):
        if angles[i] <= tilt_deg <= angles[i+1]:
            t = (tilt_deg - angles[i]) / (angles[i+1] - angles[i])
            return (1-t)*bins[i] + t*bins[i+1]
    return g0

def compute_proxy(phi, strokes, gravity=None):
    w = np.zeros((GS, GS))
    for b in range(NB): w += strokes[b] * phi[b]
    if gravity is not None: w += gravity
    return w

def load_fea_horizontal(path):
    data = np.loadtxt(path, delimiter=',', skiprows=1)
    x_p, z_p = data[:,0], data[:,2]
    u_local = data[:,4]  # UY = plate-normal for horizontal plate
    u_grid = griddata((x_p, z_p), u_local, (Xg, Zg), method='linear')
    n = np.isnan(u_grid)
    if n.any(): u_grid[n] = griddata((x_p, z_p), u_local, (Xg, Zg), method='nearest')[n]
    return u_grid

def load_fea_tilted(path, tilt_deg):
    theta = np.radians(tilt_deg); ct, st = np.cos(theta), np.sin(theta)
    data = np.loadtxt(path, delimiter=',', skiprows=1)
    x_g, z_g = data[:,0], data[:,2]
    uy, uz = data[:,4], data[:,5]
    u_local = uy*ct + uz*st
    z_ext = z_g.max()-z_g.min(); zs = L/z_ext if z_ext>0 else 1.0
    u_grid = griddata((x_g, z_g*zs), u_local, (Xg, Zg), method='linear')
    n = np.isnan(u_grid)
    if n.any(): u_grid[n] = griddata((x_g, z_g*zs), u_local, (Xg, Zg), method='nearest')[n]
    return u_grid

def compare(wp, wf, label):
    wp_dm, wf_dm = wp-np.mean(wp), wf-np.mean(wf)
    res = wp_dm-wf_dm
    rms = np.sqrt(np.mean(res**2))*1000
    ss_r=np.sum(res**2); ss_t=np.sum((wf_dm-np.mean(wf_dm))**2)
    r2 = 1-ss_r/max(ss_t,1e-20)
    pv_p=(np.max(wp)-np.min(wp))*1000; pv_f=(np.max(wf)-np.min(wf))*1000
    return {'rms_mm':round(rms,2),'r2':round(r2,4),'pv_ratio':round(pv_p/pv_f,4),
            'shape_corr':round(np.corrcoef(wp_dm.ravel(),wf_dm.ravel())[0,1],4),
            'pv_proxy_mm':round(pv_p,1),'pv_fea_mm':round(pv_f,1)}, res

# =====================================================================
# PART A: Deformation Validation (4 conditions)
# =====================================================================
print('\n=== Deformation Validation ===')
pairs = [
    ('0deg_nograv',   compute_proxy(phi, strokes), load_fea_horizontal(f'{RESULT_DIR}/node_dump_0deg_nograv.csv')),
    ('0deg_grav',     compute_proxy(phi, strokes, compute_gravity(0)), load_fea_horizontal(f'{RESULT_DIR}/node_dump_0deg_grav.csv')),
    ('29.5deg_grav',  compute_proxy(phi, strokes, compute_gravity(29.5)), load_fea_tilted(f'{RESULT_DIR}/node_dump_295deg_gtav.csv', 29.5)),
    ('58.5deg_grav',  compute_proxy(phi, strokes, compute_gravity(58.5)), load_fea_tilted(f'{RESULT_DIR}/node_dump_585deg_grav.csv', 58.5)),
]

fig, axes = plt.subplots(4, 3, figsize=(16, 20))
metrics = []
for row, (label, wp, wf) in enumerate(pairs):
    m, res = compare(wp, wf, label); m['label']=label; metrics.append(m)
    print(f"  {label}: RMS={m['rms_mm']:.2f}mm R2={m['r2']:.4f} PV_ratio={m['pv_ratio']:.4f} shape_corr={m['shape_corr']:.4f}")
    wp_dm, wf_dm = wp-np.mean(wp), wf-np.mean(wf)
    vmax = max(np.max(np.abs(wp_dm)), np.max(np.abs(wf_dm)))
    rmax = np.max(np.abs(res))
    for col, (data, title, vmi, vma) in enumerate([
        (wp_dm*1000, f"TPS Proxy\nPV={m['pv_proxy_mm']:.0f}mm", -vmax*1000, vmax*1000),
        (wf_dm*1000, f"FEA\nPV={m['pv_fea_mm']:.0f}mm", -vmax*1000, vmax*1000),
        (res*1000, f"Residual\nRMS={m['rms_mm']:.1f}mm R2={m['r2']:.3f}", -rmax*1000, rmax*1000)]):
        im = axes[row,col].imshow(data, cmap='RdBu_r', origin='lower',
            extent=[-W/2,W/2,-L/2,L/2], vmin=vmi, vmax=vma, aspect='auto')
        plt.colorbar(im, ax=axes[row,col], label='mm')
        axes[row,col].set_title(title, fontsize=9, fontweight='bold')
        if col==0: axes[row,col].set_ylabel(f'{label}\nZ (m)', fontsize=8)
        if row==3: axes[row,col].set_xlabel('X (m)', fontsize=8)

fig.suptitle('Deformation Validation — TPS Proxy (Fixed Kernel) vs FEA', fontsize=14, fontweight='bold')
fig.tight_layout()
fig.savefig(f'{OUT_DIR}/deformation.png', dpi=150)
plt.close(fig)
with open(f'{OUT_DIR}/deformation_metrics.json','w') as f: json.dump(metrics, f, indent=2)

# Loss curve
history = np.loadtxt(f'{RESULT_DIR}/North_300m_history.csv', delimiter=',', skiprows=1)
iters, loss, s95 = history[:,0].astype(int), history[:,1], history[:,2]
val_mask = np.array([i%10==0 and (i==0 or s95[i]!=s95[max(0,i-1)]) for i in range(len(iters))])
fig, ax1 = plt.subplots(figsize=(12,5)); ax2 = ax1.twinx()
ax1.plot(iters, loss, 'steelblue', lw=1, alpha=0.8, label='Loss')
ax2.plot(iters[val_mask], s95[val_mask], 'darkorange', marker='o', ms=4, lw=1.5, label='S95 (m²)')
ax1.set_xlabel('Iteration'); ax1.set_ylabel('Loss', color='steelblue')
ax2.set_ylabel('S95 (m²)', color='darkorange')
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1+lines2, labels1+labels2, loc='upper right')
ax1.set_title(f'North 300m — {len(iters)} Iter (Fixed Kernel, LR Decay) | Best S95={s95.min():.2f} m²', fontweight='bold')
ax1.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(f'{OUT_DIR}/loss_curve.png', dpi=150); plt.close(fig)

# Bolt distribution
BX_arr = np.array([(u-0.5)*W for v in [0.08,0.29,0.50,0.71,0.92] for u in [0.08,0.22,0.36,0.50,0.64,0.78,0.92]])
BZ_arr = np.array([(v-0.5)*L for v in [0.08,0.29,0.50,0.71,0.92] for u in [0.08,0.22,0.36,0.50,0.64,0.78,0.92]])
st = strokes.reshape(5,7)
bx_u = np.array([(u-0.5)*W for u in [0.08,0.22,0.36,0.50,0.64,0.78,0.92]])
bz_v = np.array([(v-0.5)*L for v in [0.08,0.29,0.50,0.71,0.92]])
fig, ax = plt.subplots(figsize=(9,6))
im = ax.imshow(st*1000, cmap='RdYlBu_r', origin='lower',
    extent=[bx_u[0]-0.92, bx_u[-1]+0.92, bz_v[0]-1.0, bz_v[-1]+1.0], aspect='auto')
cbar = plt.colorbar(im, ax=ax, label='mm')
for zi in range(5):
    for xi in range(7):
        ax.annotate(f'{st[zi,xi]*1000:.1f}', (bx_u[xi], bz_v[zi]),
            ha='center', va='center', fontsize=7, color='white' if st[zi,xi]*1000>18 else 'black')
ax.set_xlabel('X (m)'); ax.set_ylabel('Z (m)')
ax.set_title(f'Bolt Stroke (max={strokes.max()*1000:.1f}mm)', fontweight='bold')
fig.tight_layout(); fig.savefig(f'{OUT_DIR}/bolt_distribution.png', dpi=150); plt.close(fig)

# =====================================================================
# PART B: Flux Validation (29.5 deg, zenith sun)
# =====================================================================
print('\n=== Flux Validation (29.5 deg, zenith sun) ===')

# Proxy surface at 29.5 deg
w_proxy_295 = compute_proxy(phi, strokes, compute_gravity(29.5))
fea_295 = load_fea_tilted(f'{RESULT_DIR}/node_dump_295deg_gtav.csv', 29.5)

# Export surfaces
for label, w in [('proxy', w_proxy_295), ('fea', fea_295)]:
    path = f'{OUT_DIR}/surface_{label}_295deg.txt'
    with open(path, 'w') as f:
        for zi in range(GS):
            for xi in range(GS):
                f.write(f'{Xg[zi,xi]:.6f} {Zg[zi,xi]:.6f} {w[zi,xi]:.12f}\n')
    print(f'  Exported: {path}')

# Create sun file and config
with open(f'{OUT_DIR}/sun_zenith.txt', 'w') as f: f.write('0.0 1.0 0.0\n')
cfg = {
    "sun_train_file": f"{OUT_DIR}/sun_zenith.txt", "sun_validation_file": f"{OUT_DIR}/sun_zenith.txt",
    "ellipse_file": "data/ellipse_north.txt", "output_dir": f"{OUT_DIR}/flux",
    "receiver_radius":10,"receiver_height":20,"pixel_width":157,"pixel_height":50,
    "heliostat_width":12.84,"heliostat_length":9.45,"grid_size":25,
    "glass_depth":0.003,"refractive_index":1.523,"slope_error":0.001,"reflectivity":0.88,
    "sun_type":"buie","dni":1000,"csr":0.01,"sun_sigma":0.00251,"sun_theta_max":0.00465,
    "iterations":1,"patience":1,"learning_rate":0.0002,"beta1":0.9,"beta2":0.999,"adam_epsilon":1e-08,
    "use_bolt":1,"num_bolts":35,"num_bolts_x":7,"num_bolts_z":5,
    "influence_data_path":"data_vsm_mnvn_tik32","bolt_init_file":"","disable_gravity":1,
    "enable_mse_loss":0,"geometry_sample_grid":20
}
os.makedirs(f'{OUT_DIR}/flux', exist_ok=True)

# Run GPU flux dumps
for label, surf in [('proxy', f'{OUT_DIR}/surface_proxy_295deg.txt'),
                     ('fea', f'{OUT_DIR}/surface_fea_295deg.txt')]:
    cfg['output_dir'] = f'{OUT_DIR}/flux_{label}'
    os.makedirs(cfg['output_dir'], exist_ok=True)
    cfg_path = f'{OUT_DIR}/flux_config_{label}.json'
    with open(cfg_path,'w') as f: json.dump(cfg, f, indent=2)
    cmd = [EXE, '--dump-flux', '--surface-file', surf, '--config', cfg_path]
    print(f'  Running GPU flux: {label}...')
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    for line in r.stdout.split('\n'):
        if 'PV=' in line or 'surface' in line.lower() or 'Saved' in line:
            print(f'    {line.strip()}')

# Load and compare flux
def load_npy(path):
    with open(path, 'rb') as f:
        magic = f.read(6); major, minor = struct.unpack('<BB', f.read(2))
        hl = struct.unpack('<H' if major==1 else '<I', f.read(2 if major==1 else 4))[0]
        hdr = f.read(hl).decode()
        sm = re.search(r"'shape':\s*\(([^)]+)\)", hdr)
        shape = tuple(int(x.strip()) for x in sm.group(1).split(',') if x.strip()) if sm else (50,157)
        return np.frombuffer(f.read(), dtype=np.float32).reshape(shape)

def compute_s95_level(flux):
    sf = np.sort(flux.ravel())[::-1]
    return sf[max(0, min(np.searchsorted(np.cumsum(sf), 0.95*flux.sum()), len(sf)-1))]

proxy_npy = glob.glob(f'{OUT_DIR}/flux_proxy/*_sun0_flux.npy')
fea_npy = glob.glob(f'{OUT_DIR}/flux_fea/*_sun0_flux.npy')

if proxy_npy and fea_npy:
    fp_raw = load_npy(proxy_npy[0])
    ff_raw = load_npy(fea_npy[0])

    # Rotate 180
    fp_raw = np.rot90(fp_raw, 2)
    ff_raw = np.rot90(ff_raw, 2)

    fp_s = gaussian_filter(fp_raw, sigma=1.5)
    ff_s = gaussian_filter(ff_raw, sigma=1.5)
    diff = fp_s - ff_s

    s95_p = compute_s95_level(fp_s); s95_f = compute_s95_level(ff_s)

    flux_cmap = LinearSegmentedColormap.from_list('flux', [
        (0,(0,0,0.6)),(0.2,(0.3,0.5,1)),(0.4,(0.7,0.85,1)),
        (0.5,(1,1,1)),(0.6,(1,0.85,0.7)),(0.8,(1,0.4,0)),(1,(0.6,0,0))])

    ext = [-180, 180, 0, 20]

    for label, data, s95_val, fname in [
        ('proxy', fp_s, s95_p, 'flux_proxy_295deg.png'),
        ('fea', ff_s, s95_f, 'flux_fea_295deg.png')]:
        fig, ax = plt.subplots(figsize=(10,6))
        im = ax.imshow(data, cmap=flux_cmap, aspect='auto', vmin=0, extent=ext)
        plt.colorbar(im, ax=ax, label='W/m²', shrink=0.85)
        ax.contour(data, levels=[s95_val], colors='lime', linewidths=2.5, extent=ext)
        ax.set_title(f'{"TPS Proxy" if label=="proxy" else "FEA"} (29.5 deg, zenith sun)\n'
                     f'peak={data.max():.0f} W/m²  S95={np.sum(data>=s95_val)} px',
                     fontsize=12, fontweight='bold')
        ax.set_xlabel('Azimuth (deg)'); ax.set_ylabel('Height (m)')
        for x in [-90,0,90]: ax.axvline(x, color='gray', ls=':', alpha=0.3, lw=0.5)
        fig.tight_layout(); fig.savefig(f'{OUT_DIR}/{fname}', dpi=150); plt.close(fig)
        print(f'  {fname}: peak={data.max():.0f}, S95={np.sum(data>=s95_val)} px')

    rms = float(np.sqrt(np.mean((fp_s-ff_s)**2)))
    print(f'  Flux RMS diff: {rms:.2f} W/m²')

print(f'\nAll results saved to {OUT_DIR}/')
