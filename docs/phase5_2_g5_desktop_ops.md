# Phase 5.2 G5 台式机操作文档：ROM 重力场 + margin 端到端优化

> 面向台式机 kimi 的操作指令。前置：`docs/phase5_2_wos_layout_optimization.md` §6 Track B 与附录 C（B1/B2 全部技术细节与裁决记录）。
> 本批目标：用 von Kármán 板 ROM 作为重力场提供器，端到端跑出 **S95(margin) 曲线**（300m NEWS 四镜 @110dir），验证 Phase 5.1 预测的 "margin 0.08→0.04 带来 3–5% 改善"，并产出 ROM-bins vs ANSYS-bins 的光学对照（m08r sanity 组）。

## 1. 环境准备

```bash
git pull            # 拿到 scripts/rom_plate_fem.py、rom_field_provider.py、
                    # rom_margin_optimize.py、analysis/rom_b2_alpha_table.csv 等
python -c "import numpy, scipy; print('deps ok')"
```

无需 ANSYS（G5 主批不跑 FEA；§4 的 FEA 抽查才需要）。渲染器 exe：`build/src/Release/bezier_opt.exe`（若仓库无最新构建，用 MSBuild 重新构建 `build/bezier_opt.sln`，Release）。

## 2. 预检（10+15 min）

```bash
# (a) provider 自检：生成 margin=0.06 的 20 角度 ROM bins（约 10 min，CPU）
python scripts/rom_field_provider.py --margin 0.06 --out data_rom/m06
# 预期：20 行 [angle] 输出全部 mode=vk（无 linear-fallback）；
# gravity_10deg.bin 的 PV ≈ 7mm 量级（alpha 修正后），gravity_angles.json 生成。

# (b) 渲染器 3 迭代烟雾（验证 bins 被接受、loss 正常）
python scripts/rom_margin_optimize.py --margins 0.06 --iters 3 --reuse-bins --tag smoke
# 预期：results_rom/smoke_m06/run.log 中 20 个 gravity bin 全部 Loaded，
# Iter 0–2 的 S95 与 Loss 正常下降（量级：Loss ~3.8e4、S95 ~50–95 m^2 随镜面不同）。
```

## 3. G5 主批（预计 100 iter × 4 镜 × 6 组；按台式机 ~60–100s/iter 估 40–65 hr，建议拆晚班）

```bash
# 组1：m08 基线（ANSYS bins，直接复用 data_rom/m08——笔记本已放入仓库；
#      若缺失则 mkdir data_rom/m08 并复制 data_proxy 的 gravity_*.bin、influence_phi*.bin、gravity_angles.json）
python scripts/rom_margin_optimize.py --margins 0.08 --reuse-bins --tag base

# 组2：m08r sanity（margin 0.08 的 ROM bins——与组1 同 margin 对照，隔离 provider 误差）
python scripts/rom_margin_optimize.py --margins 0.08 --tag rom

# 组3–6：ROM margin 曲线（provider 每组约 10–15 min 自动先生成 bins）
python scripts/rom_margin_optimize.py --margins 0.06,0.05,0.04,0.03 --tag rom
```

- 驱动脚本逐 margin 串联：provider 生成 bins → 写 config（`bolt_margin` + `influence_data_path`）→ 渲染器 100 iter 优化（`--bolt-file` 热启动自前一 margin 的 North BEST）→ 解析 `optimization_summary.csv`。
- 产出：`analysis/rom_g5_margin_curve_{base,rom}.csv` + 各 `results_rom/*/` 目录。
- **判读**：(i) 组1 vs 组2 的 best_S95 差异 <2% ⇒ provider 端到端可信；(ii) rom 曲线在 margin 0.03–0.05 出现最小值且较 0.08 改善 3–5% ⇒ G5 通过，与 5.1 守恒律互证。
- 若时间紧张：先跑 0.08,0.04 两点（`--margins 0.08,0.04`）确认趋势再补全。

## 4. FEA 抽查批（G5 出 margin* 后执行，需 ANSYS）

对 G5 最优 margin m*（预测 0.03–0.05）：

```bash
# (a) m* 的 ANSYS 真值 bins（20 角度，约 5 min）
python scripts/ansys_gravity.py --bolt-layout <生成 m* 的 layout json，参照 configs/bolt_layouts/7x5_margin04.json 格式>
# (b) 用 ANSYS bins 复跑渲染器（确认 ROM 预测的光学改善在真值下成立）
python scripts/rom_margin_optimize.py --margins <m*> --reuse-bins --tag feacheck \
#   注意：--bins-root 需指向 ansys_gravity 输出目录；可直接把生成目录软链/复制为 data_rom/mXX
```

同时执行附录 C.6 两个独立批次（裁决差场量化假设 + 统一模型口径）：

```bash
# (c) 细网格 m04/m06（仅 10° 即可）：编辑 configs/bolt_layouts/7x5_margin04.json 加 "mesh_ndiv_x": 128, "mesh_ndiv_z": 96 后重跑 ansys_gravity.py（仅留 gravity_10deg）
# (d) 脚本重生成 m08 基线：python scripts/ansys_gravity.py --bolt-layout configs/bolt_layouts/7x5_default.json（输出到新目录 data_proxy_m08_script，勿覆盖 data_proxy）
```

## 5. 回收清单

- `analysis/rom_g5_margin_curve_*.csv`（主结果）
- `results_rom/*/optimization_summary.csv`、`results_rom/*/run.log`
- FEA 抽查目录（data_proxy_m08_script/、细网格 m04/m06 的 10° bin）
- 把结论追加到 `docs/phase5_2_wos_layout_optimization.md` 附录 C（新开 C.9 G5 记录）

## 6. 已知限制（判读时参照）

- ROM bins 与 ANSYS 真值的差异：10–30° cos≈0.94–0.96、幅值经 alpha 表修正后残余 ~15% 系统偏差；高角度（≥46°）靠负 alpha 翻号逼近，翻转角随布局可能漂移（m06 验证一致）。
- 差场（布局敏感度）ROM 幅值高估 ~2 倍 ⇒ margin 曲线形状可能偏陡，最优点位置比斜率更可信。
- m08 基线 bins（data_proxy）与脚本族模型不同（附录 C.3）：组1 与组2 的差异含模型系统差，判读 (i) 时预期 2–5% 而非完全一致；(d) 批次的脚本版 m08 才是最终公平基线。
