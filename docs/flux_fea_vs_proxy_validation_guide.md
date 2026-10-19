# 光斑验证实验工作流：FEA vs TPS Proxy（同位置 × 多倾角，S95 + 总能量）

> 目的：对**同一面镜子（同一位置）**在不同倾角下，分别用 **FEA 真值点云**与 **TPS Proxy 曲面**跑 Vulkan 光追，
> 对比所得光斑的 **S95 尺寸（m²）**与**总能量（W）**。
>
> 日期：2026-08-11。依赖脚本：`scripts/run_fea_validation.py`（FEA 生成 + 形变对比）、
> `scripts/run_flux_validation.py`（光斑对比，已修复两个 bug，见 §4）。

---

## 1. 指标口径（与 C++ 主程序一致）

| 指标 | 定义 |
|------|------|
| **S95 (m²)** | 与 `main.cpp` dump-flux 内联算法一致：20 轮二分求阈值 `level`，统计 `f ≥ level` 的像素数 × 像素面积 |
| **像素面积** | `2πRH / (Wpx·Hpx) = 2π·10·20 / (157·50) ≈ 0.16008 m²/px`（圆柱接收器展开） |
| **总能量 (W)** | flux 为接收器像素辐照度（W/m²），总功率 = `Σflux × 像素面积`。**在归一化之前**取原始 flux 求和（旧版脚本先归一化再报告，导致 `total_proxy ≡ total_fea`，已修复） |
| NRMSE / corr | 先把 Proxy 光斑总能量归一化到 FEA 总能量后比较——**只测光斑形状**，不含截获能量差异 |

S95 与总能量是本次实验的两个主指标；NRMSE/corr 为辅助解释指标。

---

## 2. 场景 A（推荐，桌面机）：带优化螺栓行程的完整验证

前置条件：ANSYS MAPDL v252 + license（`run_fea_validation.py` 中 `ANSYS_EXE` 默认
`L:/Program Files/ANSYS Inc/v252/ansys/bin/winx64/ANSYS252.exe`，可用 `--ansys-exe` 覆盖）、
Vulkan SDK 已构建的 `bezier_opt.exe`、`data_proxy/`（v2 三平面重力 bins + TPS 影响函数）。

### 2.1 Phase 1 — FEA：对所选倾角跑 ANSYS 螺栓行程仿真

```bash
# RES = 含 *_STROKE_bolts.txt 的优化结果目录（如 results_north_300iter/）
python scripts/run_fea_validation.py \
    --result-dir <RES> \
    --heliostat-prefix North_300m \
    --angles 10 26 42 58 60 73 80
```

- 每个角度一次静力仿真（NLGEOM-ON、重力 + 35 螺栓沿板法向的给定位移、SHELL181 64×48 网格）；
- 输出 `<RES>/fea_validation/`：`node_dump_<ang>deg.csv`（7 列 x,y,z,ux,uy,uz,usum）、
  `fea_deformed_<ang>deg.txt`、`fea_pointcloud_<ang>deg.txt`、`fea_metadata.json`、APDL 副本；
- 不确定时先 `--dry-run` 只生成 APDL 输入文件检查。
- **60° 说明**：60° 不在 20-bin 重力角集合里（相邻 bin 为 58°/62°），是**唯一的非 bin 角度**——
  Proxy 侧靠角度插值，FEA 侧是 ANSYS 新解，因此 60° 单独反映**重力角度插值误差**的光学影响。
  本机 `data_proxy/ansys_csv/node_dump_60deg.csv` 是旧口径数据（3072 节点、位移形状与相邻角度不一致），
  不可作真值使用；桌面机 Phase 1 重新生成后即可用。

### 2.2 Phase 1b（可选但建议）— 形变层面对比，提前止损

```bash
python scripts/run_fea_validation.py \
    --result-dir <RES> \
    --compare-csv <RES>/fea_validation/node_dump_26deg.csv \
    --compare-csv <RES>/fea_validation/node_dump_58deg.csv \
    --compare-csv <RES>/fea_validation/node_dump_60deg.csv
```

预期（历史口径）：RMS ~2.0–3.3 mm、shape_corr 0.95–0.96、PV_ratio ~0.9–1.0。
**若 shape_corr ≈ −1，说明螺栓行程符号约定反了**，先查 STROKE 文件与 APDL 的符号，再进 Phase 2。

### 2.3 Phase 2 — 光斑对比（每角度 2 次 GPU 光追 dump）

```bash
python scripts/run_flux_validation.py \
    --result-dir <RES> \
    --heliostat-prefix North_300m \
    --fea-dir <RES>/fea_validation \
    --angles 10 26 42 58 60 73 80 \
    --config configs/bolt_optimize_north_200iter.json \
    --sun-file data/36_sundir_fast.txt \
    --exe <ABS_PATH>/build/src/Release/bezier_opt.exe
```

- 每个角度：Proxy 面 = 重力 bins（角度插值）+ Σh·φ（STROKE 行程）；FEA 面 = `node_dump_*.csv`
  提取板法向位移 `w = uy·cosθ + uz·sinθ` → 插值到 32×32 网格；分别写 `x z w` 曲面文件 → `--dump-flux`；
- 太阳方向：从 `--sun-file` 中找倾角匹配 ±1° 的方向，找不到则合成恰好产生目标倾角的方向；
- 光学设定沿用 `bolt_optimize_north_200iter.json`：Buie(CSR=0.01)、1 mrad 斜率误差、n=1.523/4mm 双面折射玻璃、
  接收器 157×50、网格 32×32、位置 North 300m（`data/ellipse_north.txt`）；
- 输出 `<RES>/fea_validation/flux_validation/`：
  - `flux_comparison_summary.csv` / `.json` —— **汇总表（S95 m²、总能量 W、差值、NRMSE、corr）**
  - `flux_metrics_<ang>deg.json`、`flux_comparison_<ang>deg.png`（光斑 side-by-side + S95 等值线）
  - `flux_{proxy,fea}_<ang>deg.npy` —— 原始光斑，可自行复算
- 终端最后会直接打印每个角度的 S95/总能量对比表。

### 2.4 结果解读

- **ΔE（能量差）**：面型差异引起的截获/溢出差异，越接近 0 说明 Proxy 在光学能量意义上越等效；
- **ΔS95（尺寸差）**：面型差异引起的光斑聚光尺寸差；
- ΔE≈0 而 ΔS95 明显 → 面型差主要改变能量分布而非截获（近场再分布）；
- **60°** 单独看插值误差；其余角度看"影响函数 + 重力 + 网格"的整体光学保真度。

---

## 3. 场景 B（无 ANSYS 机器）：零螺栓（纯重力）快速自检

用已有纯重力 FEA 点云（20 bin 角度，NLGEOM-ON），验证「重力 bins → 曲面文件 → 光追」管线可用性。

```bash
# 1) 零行程文件（35 行 0.0）
mkdir -p validation/flux_fea_vs_proxy/zero_bolts
python - <<'EOF'
with open('validation/flux_fea_vs_proxy/zero_bolts/North_300m_STROKE_bolts.txt','w') as f:
    f.write('# zero bolt strokes (pure gravity check)\n')
    for _ in range(35):
        f.write('0.0\n')
EOF

# 2) 光斑对比（注意：排除 60°，本机 60° CSV 为旧口径）
python scripts/run_flux_validation.py \
    --result-dir validation/flux_fea_vs_proxy/zero_bolts \
    --heliostat-prefix North_300m \
    --fea-dir data_proxy/ansys_csv \
    --angles 10 26 42 58 62 73 80 \
    --config configs/bolt_optimize_north_200iter.json \
    --sun-file data/36_sundir_fast.txt
```

- bin 角度下 Proxy 重力 bins 就来自该角度同一 FEA CSV → 两者差值仅反映网格插值 + 有限差分导数，
  属于**管线一致性自检**（预期 S95/能量几乎一致），不是代理精度检验；
- 代理精度检验必须走场景 A（带螺栓行程、新 FEA）。

---

## 4. 本次对 `scripts/run_flux_validation.py` 的修复（2026-08-11）

1. **v2 三平面重力加载 bug**：旧代码只接受单平面 bin（1024 floats），而当前 `data_proxy` 是 v2 三平面
   （`gravity_angles.json: "format": "w_du_dv_v2"`，每 bin 12288 B = 3×1024）→ 旧代码会把重力静默置零，
   Proxy 面只有螺栓项，结果完全错误。已按 `run_fea_validation.py` 的写法补 `raw[:n_grid]` 分支。
2. **总能量被归一化掩盖**：旧 `compute_flux_metrics` 先把 Proxy 归一化到 FEA 总能量再报告
   `total_proxy/total_fea` → 两者恒等，能量对比无意义。已改为在归一化前保存原始 `Σflux`，
   新增 `total_proxy_w/total_fea_w`（W）与 `energy_diff_w/energy_diff_pct`。
3. **新增 S95(m²) 指标**：新增 `s95_proxy_m2/s95_fea_m2/s95_diff_m2/s95_diff_m2_pct`
   （main.cpp 同款 20 轮二分语义），汇总表与 CSV 同步升级。
4. **整型角度文件名 bug**：旧查找逻辑 `str(angle).replace('.','')` 对整型角度失效
   （10.0 → "100"），且只匹配 `run_fea_validation.py` 的旧命名 → 整型角度找不到 FEA CSV 而全部跳过。
   新增 `find_fea_csv()` 同时兼容 `node_dump_10deg.csv` / `node_dump_10.0deg.csv` /
   `node_dump_295deg.csv`（29.5°）/ `node_dump_29.5deg.csv` 四种命名。
5. **子进程输出改为文件重定向**：`run_flux_dump` 原用 `subprocess(capture_output=True)`（命名管道），
   在禁用 named pipe 的环境（沙箱/CI）会 EPERM；改为 stdout/stderr 重定向到日志文件后读取，
   正常桌面与受限环境通用。

---

## 5. 常见坑

- **桌面交接前校验 data_proxy**：20 个 `gravity_*.bin` 必须都是 **12288 B**（v2 三平面），
  否则用 `python scripts/generate_proxy_model.py gravity --source-dir data_proxy/ansys_csv --output-dir data_proxy` 重生成；
- **exe 与 shaders**：`--dump-flux` 以 exe 所在目录为 cwd 加载 `shaders/*.spv`（cmake 构建后自动复制）；从 worktree 运行请显式 `--exe`；
- **STROKE 与 FEA 必须同源**：Phase 1 与 Phase 2 的 `--result-dir` 必须指向同一结果目录，否则 FEA 点云与 Proxy 的螺栓行程不对应；
- **沙箱/CI 环境**：`run_flux_dump` 已改为日志文件重定向（见 §4.5），无 named pipe 依赖。

---

## 6. 本机已验证状态（2026-08-11 冒烟测试）

在工作机（无 ANSYS）上完成了 **场景 B 零螺栓 7 角度（10/26/42/58/62/73/80）端到端冒烟测试**：
Release 构建 + 14 次 GPU 光追全部成功。结果符合预期——bin 角度下 FEA 与 Proxy 光斑几乎逐位一致：

| 角度 | S95 (m²) | ΔS95 | E FEA (W) | E Proxy (W) | ΔE% | NRMSE |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 10.0° | 229.6 | +0.0 | 51402 | 51402 | 0.00 | 0.0000 |
| 26.0° | 239.5 | +0.0 | 65868 | 65868 | 0.00 | 0.0000 |
| 42.0° | 218.0 | +0.0 | 66623 | 66596 | −0.04 | 0.0016 |
| 58.0° | 209.1 | +0.0 | 66296 | 66283 | −0.02 | 0.0014 |
| 62.0° | 232.8 | +0.0 | 75729 | 75764 | +0.05 | 0.0014 |
| 73.0° | 236.1 | +0.0 | 75119 | 75119 | 0.00 | 0.0000 |
| 80.0° | 233.1 | +0.0 | 72221 | 72221 | 0.00 | 0.0000 |

（零螺栓、纯重力口径：bin 角度下 Proxy 重力 bins 即来自同一 FEA CSV，差异仅来自网格插值/有限差分，
故几乎一致——这证明管线自洽。**带螺栓行程的代理精度对比请在桌面机按场景 A 执行**。）
