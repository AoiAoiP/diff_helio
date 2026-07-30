# Phase 4 FEA 抽查结果汇总（South_300m + North_300m）

> 执行日期：2026-07-30（台式机）
> 依据文档：`docs/phase4_fea_desktop_handoff.md`（对应主报告 `docs/gravity_compensation_experiment.md` §2.3 Phase 4 第 2 步）
> 仓库状态：2026-07-30 历史重写后全新 clone（HEAD `db64f6e`），旧本地副本已删除。

## 任务目的

用 ANSYS FEA 复算 Phase 3 优化终态螺栓（`results_fw_tanh_a0/`，a0 基线组，35 螺栓）
下的重力畸变，与 TPS proxy 对比，判定"重力地板是真实物理还是 proxy 伪影"。

## 1. 环境自检（§1，通过）

- `data_proxy/gravity_10deg.bin` = **12288 字节**（v2 格式，非 4096 幻影数据）✓
- `results_fw_tanh_a0/South_300m_STROKE_bolts.txt` 在位（35 值，0–37.8 mm）✓
- `results_fw_tanh_a0/North_300m_STROKE_bolts.txt` 在位（35 值，0–37.2 mm）✓
- ANSYS 默认路径在位：`L:/Program Files/ANSYS Inc/v252/ansys/bin/winx64/ANSYS252.exe`，未使用 `--ansys-exe`
- 备注：新 clone 不含 `build/` 目录，脚本临时目录需要，已手动 `mkdir -p build`

## 2. Dry-run（§2，通过）

```
python scripts/run_fea_validation.py --result-dir results_fw_tanh_a0 \
    --heliostat-prefix South_300m --angles 29.5 --dry-run
```

生成 `apdl_bolt_stroke_29.5deg.dat (14.0 KB)`，无 ERROR，与文档预期一致。

## 3. 正式运行结果（§3）

运行命令：

```bash
python scripts/run_fea_validation.py --result-dir results_fw_tanh_a0 \
    --heliostat-prefix South_300m --compare 2>&1 | tee logs/_phase4_fea_south300m.log
python scripts/run_fea_validation.py --result-dir results_fw_tanh_a0 \
    --heliostat-prefix North_300m --compare 2>&1 | tee logs/_phase4_fea_north300m.log
```

两镜均为 `=== FEA Validation done: 3/3 angles ===`。

### South_300m（主抽查）— 对比表原样

```
  [0.0deg]   UY_PV=40.6mm, USUM_PV=37.8mm, nodes=3185, 7s
  [29.5deg]  UY_PV=35.0mm, USUM_PV=37.8mm, nodes=3185, 3s
  [58.5deg]  UY_PV=20.0mm, USUM_PV=37.8mm, nodes=3185, 11s

  Comparing: South_300m, 0.0deg, NLGEOM-ON
    Results: RMS=3.907mm, R2=0.8293, shape_corr=0.9310, PV_ratio=1.1436
  Comparing: South_300m, 29.5deg, NLGEOM-ON
    Results: RMS=3.750mm, R2=0.8423, shape_corr=0.9371, PV_ratio=1.1526
  Comparing: South_300m, 58.5deg, NLGEOM-ON
    Results: RMS=2.900mm, R2=0.9078, shape_corr=0.9644, PV_ratio=1.2087
```

### North_300m（阴性对照）— 对比表原样

```
  [0.0deg]   UY_PV=40.2mm, USUM_PV=37.2mm, nodes=3185, 4s
  [29.5deg]  UY_PV=34.7mm, USUM_PV=37.2mm, nodes=3185, 3s
  [58.5deg]  UY_PV=19.8mm, USUM_PV=37.2mm, nodes=3185, 4s

  Comparing: North_300m, 0.0deg, NLGEOM-ON
    Results: RMS=3.842mm, R2=0.8308, shape_corr=0.9313, PV_ratio=1.1233
  Comparing: North_300m, 29.5deg, NLGEOM-ON
    Results: RMS=3.667mm, R2=0.8454, shape_corr=0.9380, PV_ratio=1.1323
  Comparing: North_300m, 58.5deg, NLGEOM-ON
    Results: RMS=2.777mm, R2=0.9134, shape_corr=0.9666, PV_ratio=1.1906
```

### 指标速查表

| 镜子 | 角度 | RMS (mm) | R² | shape_corr | PV ratio |
|---|---|---|---|---|---|
| South_300m | 0.0° | 3.907 | 0.8293 | 0.9310 | 1.1436 |
| South_300m | 29.5° | 3.750 | 0.8423 | 0.9371 | 1.1526 |
| South_300m | 58.5° | 2.900 | 0.9078 | 0.9644 | 1.2087 |
| North_300m | 0.0° | 3.842 | 0.8308 | 0.9313 | 1.1233 |
| North_300m | 29.5° | 3.667 | 0.8454 | 0.9380 | 1.1323 |
| North_300m | 58.5° | 2.777 | 0.9134 | 0.9666 | 1.1906 |

## 4. 判定（§5）

对照 §5 判定表：

- 失败行①「RMS ≥2× 历史水平（历史 2.8–3.3 mm）」——**未触发**，全部角度 RMS ∈ [2.777, 3.907] mm；
- 失败行②「shape_corr <0.9」——**未触发**，全部角度 shape_corr ∈ [0.9310, 0.9666]；
- 失败行③「PV ratio 远离 1」——1.12–1.21，未达显著远离量级。

**判定结论：落在第一行——地板为真实物理，Phase 3 结论通过独立验证。**
后续动作：结果写入主报告 §3.7，Phase 4 收口。

## 5. 日志中的异常输出（原样记录，不作解读）

- 每条对比均打印 `WARN: gravity_XXdeg.bin has 3072 floats, expected 1024`
  （12288 字节 = 3072 float32，即 §1 要求的 v2 格式；脚本 WARN 后继续完成对比）；
- 每条对比均打印 `Gravity PV: 0.00 mm`。

## 6. 产物清单（均已保留，未删除）

- `logs/_phase4_fea_south300m.log`、`logs/_phase4_fea_north300m.log` —— 完整运行日志；
- `results_fw_tanh_a0/fea_validation/comparison/` —— 两镜逐角度对比 PNG（6 张）、
  逐角度 `metrics_*.json`（6 个，数值与日志一致）；
- `results_fw_tanh_a0/fea_validation/` 顶层 —— APDL 输入、node_dump CSV、
  fea_deformed / fea_pointcloud、`fea_metadata.json`。

注意：两次运行共用同一输出目录，顶层不带镜子前缀的文件（APDL/node_dump/fea_deformed）
已被第二次（North）运行覆盖；`comparison/comparison_summary.json` 亦只含 North。
South 的逐角度数值完整保存在 `logs/_phase4_fea_south300m.log` 与
`comparison/metrics_South_300m_*.json` 中，不受影响。

---

## ⚠️ 笔记本侧复核（2026-07-30）：§4 判定暂缓——对比中 proxy 重力被置零，需重跑

**§5 记录的两条异常是致命的**：`run_fea_validation.py` 的 `load_gravity_bins` 只接受
1024-float 旧格式，v2 三平面 bin（3072 floats）触发 WARN 后该 bin **保持为零**——
`Gravity PV: 0.00 mm` 系字面意义。本次对比实际是 FEA(螺栓+重力) vs proxy(仅螺栓)，
RMS 随角度递减（3.9→2.9mm）正是重力场量级递减的镜像——测出的主要是"被减去的重力本身"，
**对 proxy 重力保真度没有说出任何东西**（幻影重力 bug 第三次转世：C++ 管线、台式机旧 bins、
本次 Python 验证脚本）。§4 判定依据的"与历史 2.8–3.3mm 同水平"比较对象不一致，结论暂缓。

**修复**（笔记本已提交）：`load_gravity_bins` 增加 v2 分支（取 w 平面），本地验证
wPV=11.09/10.31/9.30/8.12/6.79mm 与 C++ 加载器逐位一致；`post_fea_validation.py`
共享同一函数，一并修复。

**重跑指令**（台式机，pull 后，每镜 ~1 分钟）：

```bash
git pull
python scripts/run_fea_validation.py --result-dir results_fw_tanh_a0 \
    --heliostat-prefix South_300m --compare 2>&1 | tee logs/_phase4_fea_south300m_v2.log
python scripts/run_fea_validation.py --result-dir results_fw_tanh_a0 \
    --heliostat-prefix North_300m --compare 2>&1 | tee logs/_phase4_fea_north300m_v2.log
```

通过标准：日志中 `Gravity PV` 应 ≈ 该角度重力 bin 插值 PV（0° ≈11mm、29.5° ≈5mm、
58.5° ≈2mm 量级，非 0.00）；此后 RMS/shape_corr 才是"proxy(螺栓+重力) vs FEA"的有效对比。
预期：若 proxy 重力保真，RMS 应回落至螺栓差异水平（~2–3mm）、shape_corr 回升至 ~0.95+；
若 RMS 不降反升 → proxy 重力存在真实误差，需重估地板量级。

---

## ✅ 终判（2026-07-30，v2 重跑后）：通过——重力地板为真实物理

重跑（proxy 重力正确加载，Gravity PV=11.09/5.54/2.83mm 与 bin 值逐位一致）后：
两镜 RMS 2.129–3.346mm、shape_corr 0.954–0.978、R² 0.877–0.948，与 2026-07-17/21
历史验证同水平。① 大重力角度加入 proxy 重力后 RMS 大降（0° −42~45%）→ 重力场形状吻合；
② South≈North（惩罚差 25 倍而偏差几乎相同）→ 重力侧无系统性失真。
保留项：58.5° PV_ratio ~1.25–1.27（46° NLGEOM 变号区小分母效应，方向为 proxy 高估形变，
结论方向安全）。详见主报告 §3.7。
