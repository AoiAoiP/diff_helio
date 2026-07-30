# G1 validation: WoS influence functions vs ANSYS unit-probe influence (layout 7x5 m08).
# WoS output: 35 x 256x192 (raw + FD slopes). ANSYS production: 35 x 32x32.
# Metric: per-bolt cos_sim after block-averaging WoS to 32x32, plus PV ratio.
import numpy as np, sys

WOS_DIR = sys.argv[1] if len(sys.argv) > 1 else "data_wos_g1"
ANSYS_DIR = sys.argv[2] if len(sys.argv) > 2 else "data_proxy"
NB, TW, TH, G = 35, 256, 192, 32

wos = np.fromfile(f"{WOS_DIR}/influence_phi.bin", dtype=np.float32).reshape(NB, TH, TW)
ans = np.fromfile(f"{ANSYS_DIR}/influence_phi.bin", dtype=np.float32).reshape(NB, G, G)
assert wos.shape == (NB, TH, TW) and ans.shape == (NB, G, G)

# block-average WoS 256x192 -> 32x32 (8x6 blocks)
wos_ds = wos.reshape(NB, G, TH // G, G, TW // G).mean(axis=(2, 4))

def cs(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na > 0 and nb > 0 else 0.0

print(f"WoS: {WOS_DIR}  ({TW}x{TH}), ANSYS: {ANSYS_DIR} ({G}x{G})")
print(f"WoS value range: [{wos.min():.4f}, {wos.max():.4f}]   ANSYS: [{ans.min():.4f}, {ans.max():.4f}]")
print(f"\n{'bolt':>4} | {'cos_sim':>8} | {'wosPV':>8} {'ansPV':>8} {'PVratio':>8}")
css, pvr = [], []
for b in range(NB):
    a, w = ans[b].ravel(), wos_ds[b].ravel()
    c = cs(a, w)
    pv_w = float(w.max() - w.min()); pv_a = float(a.max() - a.min())
    r = pv_w / pv_a if pv_a > 0 else float('nan')
    css.append(c); pvr.append(r)
    print(f"{b:>4} | {c:>8.4f} | {pv_w:>8.4f} {pv_a:>8.4f} {r:>8.3f}")

css, pvr = np.array(css), np.array(pvr)
print(f"\ncos_sim: mean={css.mean():.4f} min={css.min():.4f} (bolt {css.argmin()}) max={css.max():.4f}")
print(f"PV ratio (wos/ansys): mean={np.nanmean(pvr):.3f} std={np.nanstd(pvr):.3f}")

# center bolt vs corner bolt vs edge bolt diagnostics
# layout 7 cols (x) x 5 rows (z), idx = row*7+col; center = (2,3)->17, corners 0/6/28/34
print("\nkey bolts: center=17, corners=0,6,28,34, edge-mid=3,31,17? ")
for b in [17, 0, 6, 28, 34, 3, 10, 24]:
    print(f"  bolt {b:>2}: cos={css[b]:.4f} PVratio={pvr[b]:.3f}")
