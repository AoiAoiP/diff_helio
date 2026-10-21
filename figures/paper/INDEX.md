# 图表台账（figures/paper/INDEX.md）

> 图号与 `docs/paper/draft.md` 的图清单一一对应。每张图进入正文前，必须在本目录下建立同名映射文件
> `figN_<slug>.md`（模板见 §4），写明生成脚本、输入数据、最后生成时间。规程见 `AGENTS.md` §3.2、§8。
> 当前状态：**12 张图全部未生成**；下表是素材与脚本的到位情况。

---

## 1. 制图规范（摘自 draft.md，投稿前逐图核对）

- 图内文字一律英文；示意图用矢量（TikZ，PDF/EPS），数据图输出 PDF + 600 dpi PNG。
- 单栏宽 90 mm、1.5 栏 140 mm、双栏 190 mm；缩放后最小字号 ≥7 pt；线宽 0.8–1.2 pt。
- 色盲友好配色 Okabe-Ito：`#0072B2 #D55E00 #009E73 #CC79A7 #E69F00 #56B4E9`，禁止仅靠红/绿区分。
- matplotlib 设 `pdf.fonttype=42`，保证文字可编辑。

---

## 2. 图 1–12

| 图 | 章节 | 类型 | 数据 / 素材现状 | 生成脚本 | 状态 |
|---|---|---|---|---|---|
| 图 1 | §1 | 示意图 | 无数据依赖（塔、单镜剖面、光斑对比小图） | TikZ + matplotlib 插图 | 未生成 |
| 图 2 | §1、§3 章首 | 管线图（teaser） | 无数据依赖，按 §3 结构绘制 | TikZ | 未生成（**最高优先**） |
| 图 3 | §3.1 | 示意图 | 无数据依赖（板俯视 + 侧视 + 坐标轴） | TikZ | 未生成 |
| 图 4 | §3.5 | 示意图 | 无数据依赖；可并入图 2 面板 | TikZ | 未生成 |
| 图 5 | §4.1 | 数据图 | **部分**：本机只有零螺栓 FEA 点云（`data_proxy/ansys_csv/`）；带螺栓行程的 FEA 点云在台式机（A-01） | 改造 `scripts/run_fea_validation.py` | 未生成（数据待同步） |
| 图 6 | §4.2 | 数据图 | **部分**：`validation/flux_fea_vs_proxy/output/` 有 7 个角度的 FEA vs proxy 光斑对比（零螺栓）；RMCRT 侧无 | 改造 `scripts/run_flux_validation.py` | 未生成（E-02 待跑） |
| 图 7 | §4.3 | 数据图 | **无**：`--check-grad` 只有文档记录的 cos 0.966 / ratio 0.35，原始输出与步长扫描未见 | 新建 `figures/scripts/fig7_grad.py` | 未生成（E-05 待跑） |
| 图 8 | §4.4 | 数据图 | **无**：需在 `pipeline.cpp` 加 2–3 个计时点，另需离线 FEA 的 `elapsed_s` | 新建 `figures/scripts/fig8_perf.py` | 未生成（E-06） |
| 图 9 | §5.2 | 数据图 | **有**：`data_proxy/ansys_csv/` 21 个倾角点云 + 20 个三平面 bin；成分分解数字在 `docs/gravity_compensation_experiment.md` §1.1.1 | 新建 `figures/scripts/fig9_gravity.py` | 未生成（素材齐备） |
| 图 10 | §5.3 | 数据图 | **有**：B_ideal / B_naive / B_comp / B\* 在 `results_*_36/optimization_summary.csv`；九组消融在 `results_fw_*`；数字表在 `docs/gravity_compensation_experiment.md` §1.3–1.5 | 新建 `figures/scripts/fig10_bounds.py` | 未生成（**最高优先**，贡献 2 的证据） |
| 图 11 | §5.4 | 数据图 | **有**：margin 曲线与密度表在 `docs/phase5_report.md` §3.1.3、§3.2.2；形变场统计在 `analysis/margin_full_report.md`、`analysis/layout_scan_report.md`、`analysis/material_swap_report.md` | 新建 `figures/scripts/fig11_levers.py` | 未生成（素材齐备） |
| 图 12 | §5.5 | 数据图 | **有**：`data/lsq_vs_opt_334d.csv`（20 镜 334dir）+ `analysis/real_gravity_penalty_table.md`（110dir 惩罚比值） | 新建 `figures/scripts/fig12_field.py` | 未生成（素材齐备） |

**推进顺序建议**：图 2（决定第一印象，零数据依赖）→ 图 10（贡献 2 的唯一证据）→ 图 11 → 图 9 → 图 5/6（依赖台式机）→ 图 7/8（依赖补跑）→ 图 1、3、4、12。

---

## 3. 表 1–4

| 表 | 章节 | 状态 | 备注 |
|---|---|---|---|
| 表 1 | §5.1 | 已起草（`docs/paper/ch5_application_v1.md`） | “依据”列待补到小节号或文献号 |
| 表 2 | §4 末 | 仅轮廓 | 代理精度、光斑一致性、梯度一致性三组；RMCRT 行待 E-02 |
| 表 3 | §5.4 | **缺** | 结构杠杆对比（边距 / 密度 / 材料）尚未成表，现为正文文字 |
| 表 4 | §5.5 | 已起草 | 900/1200 m 行作废（能量溢出），待 E-03 重跑或删行；`lsq` 列口径待 E-04 |

---

## 4. 映射文件模板

```markdown
# fig10_bounds_decomposition

- 章节：§5.3
- 生成脚本：figures/scripts/fig10_bounds.py
- 输入数据：results_bound_300m_36/optimization_summary.csv、
            results_lsq_eval_c0_36/optimization_summary.csv、
            results_lsq_eval_c1_36/optimization_summary.csv
- 最后生成：YYYY-MM-DD HH:MM
- 状态：draft / final
- 备注：口径 36dir；功耗/能量侧无
```

## 5. 命名

- 图片本体：`figures/paper/figN_<slug>.pdf`（+ `.png` 供审阅）
- 映射文件：`figures/paper/figN_<slug>.md`，与图片同名
- 中间产物：`figures/generated/<script>_<param>/`，不得直接写 `figures/paper/`
- 绘图脚本：`figures/scripts/figN_<slug>.py`；TikZ 源：`figures/scripts/tikz/figN_<slug>.tex`
