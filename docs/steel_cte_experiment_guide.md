# 钢材热膨胀系数（CTE）影响实验行动指南

> 状态：设计稿（2026-08-10）。执行者：后续实验执行者（人或 AI agent）。
> 本文是材料测试线的补充实验指南，覆盖从文献核查到端到端评估的全部阶段（T0–T4）。
> 所有项目内机制均标注真实文件路径/函数名；外部物理常数若未核实一律标注「需文献核实」，禁止直接引用。

---

## 1. 科学问题与动机

材料线目前只考察了弹性参数（E/ν/ρ/t）对重力形变的影响，结论是「材料/厚度 = 逐角度纯缩放轴」（见 `analysis/material_swap_report.md` 与 `docs/phase5_structural_optimization.md` §2.3/§3.2）。但真实定日镜不是单一材料板：它是**玻璃反射层 + 钢背板 + 胶层的层合结构**。当环境温度或日照导致板体升温时，两种材料的热膨胀系数（CTE）失配会在层合板内产生**热弯曲（thermal bow）**——这是与重力正交、且材料线从未覆盖的形变源。

物理量级（全部**需文献核实**，下列数值仅供数量级参考、来源存疑）：

- 普通钠钙玻璃 CTE ≈ 8–9.5e-6 /K；低碳钢 CTE ≈ 11–13e-6 /K。失配量级 Δα ≈ 2–4e-6 /K。
- 注意：任务背景中「1.2e-5 vs 2.3e-5 /K」一对数值存疑——2.3e-5 /K 是**铝**的典型值而非钠钙玻璃；钢-玻璃层合板的真实失配比这对数字小约一个量级。T0 阶段必须查清本项目镜像面所用的玻璃牌号与钢牌号的实际 CTE 并给出出处。
- 经典双金属片公式：曲率 κ ≈ 6·Δα·ΔT·(1+m)² / [h·(3(1+m)² + (1+mn)(m² + 1/(mn)))]（Timoshenko 1925, J. Opt. Soc. Am.，公式引用**需文献核实**）。粗略量级：12.84 m 宽镜板、Δα=3e-6/K、ΔT=20 K 时，自由热弯曲矢高可达 mm 量级——与 10° 重力 PV（11.09 mm，`phase5_structural_optimization.md` §2.3）同量级，不可忽略。

与论文叙事的关系：本实验是**补充性实验**，回答「纯缩放轴结论在真实层合板+温度场下是否仍成立」。若热弯曲显著，则材料线结论需要限定适用范围；若可忽略或仍是纯缩放，则论文稳健性增强。两种结果都有叙事价值。

---

## 2. 现状盘点与缺口

已做（全部只涉及弹性参数替换，无任何温度自由度）：

- **M0 解析**：w ∝ (1−ν²)ρa⁴/(Et²)，钢 vs 玻璃等厚比值 1.014（§2.3）。
- **M1 探针**：钢 t3/t4/t6 × 5 角度（{10, 42, 46, 50, 80}），`scripts/material_swap_analysis.py` 出 cos_sim/α_w/mean_w，判定 t4/t6 纯缩放 Go、t3 近似缩放（§3.2，`analysis/material_swap_report.md`）。
- **钢 t5 端到端**：9×7 @margin 0.05 布局（`configs/bolt_layouts/9x7_steel_t5mm_m05.json`），North 300m S95 51.75 vs 玻璃 4mm 54.73（−5.5%），见 §3.2.1；结果在 `results_steel_9x7_t5/`、bins 在 `data_proxy_steel/9x7_steel_t5_m05_fine/`。

缺口：

- 全库（scripts/、docs/、analysis/、shaders/、src/）无「热膨胀 / thermal expansion / CTE」任何记录；温度自由度从未进入 FEA 模型与代理管线。
- 现有 APDL 模板（`scripts/generate_proxy_model.py` 的 `generate_gravity_apdl()`）是单层 SHELL181 + 单一材料（MP,EX/NUXY/DENS），无 MP,ALPX、无温度载荷、无分层截面（SECDATA）。
- FEA 数据通路（重力 bins，20 角度 × 3 平面）本身是通用的——热形变一旦算出即可同格式接入（见 §4）。

---

## 3. 实验总体设计（T0 → T4）

每阶段给出目标、步骤、产出、Go/No-Go 门。**门不过则停修，不进下一阶段**（沿用 Phase 5 门体系惯例，§2.5）。

### T0 文献与数量级估计（0.5–1 天，无 FEA）

- 目标：锁定真实 CTE 数值与温度场景量级，给出热弯曲是否值得做 FEA 的先验判断。
- 步骤：
  1. 查本项目镜像面（KeshengV3 参考机，`analysis/kesheng_v3_parameters.md`）的背板钢材牌号与玻璃牌号；查手册/标准取 CTE、导热系数、发射率。全部记录出处；查不到就标「需文献核实」并取区间。
  2. 查定日镜实测/仿真文献中镜面温升量级（DNI≈1000 W/m² 下玻璃面相对环境温升、前后面温差），标「需文献核实」。
  3. 用 Timoshenko 双金属公式（或等效层合板 CLT 手算）估计自由热弯曲矢高/斜率 RMS，与 10° 重力斜率 RMS（6.59 mrad，§2.3）对比。
- 产出：`analysis/thermal_magnitude_estimate.md`（数值 + 出处 + 存疑标注）。报告模板至少包含：两种材料 CTE（含出处/存疑标注）、ΔT 场景表（环境温度摆幅、日照温升、前后面温差）、Timoshenko 公式代入计算、与 10° 重力斜率 RMS 的比值、Go/No-Go 建议。
- 门：若最不利场景（最大 Δα × 最大 ΔT）下热弯曲斜率 RMS < 0.1 mrad（≈ 重力最坏工况的 1.5%），整个实验线 No-Go，直接写否定结论进论文补充材料；否则 Go T1。

### T1 均匀温升基准（半天，FEA 冒烟）

- 目标：验证 (a) 均匀温升下均质板无热弯曲、热形变对光学面型无影响（w≈0），(b) ANSYS 热-结构 APDL 改动正确，(c) 螺栓约束下的热屈曲是否被意外触发。
- 物理预期：均质板 + 均匀 ΔT，若螺栓仅约束平动（现模板 `D,ALL,UX/UY/UZ,0`），热膨胀被螺栓 patch 约束产生面内压应力；薄板在 NLGEOM,ON 下可能**热屈曲**跳出面外——这本身是物理现象，但若在 T1 出现大 w，说明真实螺栓约束建模对热问题敏感，必须在报告中区分「物理屈曲」与「数值伪影」（用细子步 + 网格加密裁决，见 §6）。
- 步骤：
  1. 复制 `generate_gravity_apdl()` 为 `scripts/thermal_proxy_model.py`（新文件，勿改原脚本），改动点：材料段加 `MP,ALPX,1,<cte>` 与 `MP,REFT,1,293`（参考温度 20°C）；求解段加 `TREF,293` 与 `BF,ALL,TEMP,313`（ΔT=+20 K）；其余（SHELL181、KEYOPT(3)=2、网格、螺栓 BC、7 列 CSV 输出）保持不动。
  2. 布局用 `configs/bolt_layouts/9x7_steel_t5mm_m05.json`（钢 t5），角度只跑探针集 {10, 46, 80}（沿用 M1 探针角度口径，§2.3）。
  3. NLGEOM,ON，细子步 `NSUBST,50,500,50`（防坑教训②，勿用模板的 1,10,1）。
  4. 输出 CSV 到 `data_proxy_thermal/t1_uniform/ansys_csv/`，用 `python scripts/generate_proxy_model.py gravity --source-dir <csv目录> --output-dir data_proxy_thermal/t1_uniform --angles 10 46 80` 打包成 bins（复用 `precompute_gravity_bins()`，无需新代码）。
- 产出：`data_proxy_thermal/t1_uniform/gravity_{10,46,80}deg.bin`（每 bin 12288 B）+ `gravity_angles.json`。
- 门：|w| PV < 0.5 mm 且斜率 RMS < 0.05 mrad（纯面内伸缩，无面外分量）→ Go T2。若 PV ≥ 0.5 mm → 先按 §6 排查热屈曲真伪，再决定是否为热屈曲单独建档。

### T2 日照稳态温度场 + 层合板热-力耦合 FEA（1–2 天）

- 目标：得到钢背板+玻璃面层层合板在日照稳态温度场下的热弯曲形变 w_thermal(x, z; θ)。
- 温度场建模（从简到繁，先做最小模型）：
  - 最小模型（推荐起点）：假设均匀整体温升 ΔT_bulk（如 +20 K）叠加前后面线性温差 ΔT_fb（如 5 K 与 10 K 两档），共 2–3 个工况。温度场直接以壳单元层温度施加（SHELL181 分层壳支持逐层温度，TBTOP/TBBOT 或 BF 逐层，具体命令**执行时在 ANSYS 文档核实**）。这避免了完整对流/辐射边界条件的参数不确定性，用工况 bracket 覆盖。
  - 完整模型（仅当最小模型结果显著且论文需要时）：稳态热分析（SHELL131/132 或 SOLID70 映射），边界 = 正面吸收 (1−ρ)·DNI（ρ=0.88，见配置文件 reflectivity）+ 双面自然/强迫对流 + 长波辐射；导热由两层材料导热系数（**需文献核实**）决定。热-结构顺序耦合。
- 结构模型：分层 SHELL181（SEC TYPE,SHELL + SECDATA 逐层厚度/材料/角度），材料 1=玻璃面层（E=70 GPa, ν=0.22, ρ=2500, ALPX=玻璃 CTE）、材料 2=钢背板（E=206 GPa, ν=0.30, ρ=7800, ALPX=钢 CTE，沿用 `9x7_steel_t5mm_m05.json` 的弹性口径）。层厚分配：总厚 5 mm 中玻璃/钢的实际比例**需文献核实**（典型镜面玻璃 3–4 mm + 钢背板 1–2 mm，执行时定）。**关键决策点**：若走「等效单层壳 + CLT 等效 ABD 矩阵」路线可省分层建模，但需自行推导等效 ALPX 与弯扭耦合项，错误风险高——**推荐直接分层壳**，ANSYS 内部处理层合本构。
- 同时保留重力：热-力耦合应开 ACEL（重力 9.81）+ 温度载荷，输出 w_total；w_thermal = w_total − w_gravity（w_gravity 已有：`data_proxy_steel/9x7_steel_t5_m05_fine` 的 bins 或同口径重跑）。**必须同网格同子步口径**做无温对照 run 才能干净相减。
- 角度：先探针 {10, 46, 80}；若热形变显著且随 θ 变化（cos_sim(10°场, 80°场) < 0.99），补全 20 bin（DEFAULT_ANGLES_20BIN，`generate_proxy_model.py:52`）。
- 步骤：扩展 T1 的 `scripts/thermal_proxy_model.py`；APDL 干跑（`--dry-run`）人审后再上真 FEA；CSV → bins 同 T1 第 4 步，输出 `data_proxy_thermal/t2_laminate/`。
- 产出：`data_proxy_thermal/t2_laminate/gravity_*deg.bin`（w_thermal，3 平面，12288 B/bin）+ `analysis/thermal_bow_report.md`（仿 `material_swap_report.md` 格式：PV/斜率 RMS/三频带分解，可用 `scripts/layout_scan_analysis.py` 的 `stats_table()` 复用）。
- 门：w_thermal 斜率 RMS < 0.1 mrad（所有工况）→ 热弯曲可忽略，写否定结论，实验线收尾；≥ 0.1 mrad → Go T3。同时检查形状不变性：w_thermal 与 w_gravity 的 cos_sim——若 ≥0.99，热弯曲可被现有螺栓补偿轴部分吸收，T4 叙事大不同。

### T3 热形变 bins 接入可微管线（0.5–1 天）

两条路线，**推荐 A 先行**（零代码改动），B 仅在需要独立开关热项时做。

- **路线 A（离线叠加，零代码改动）**：w_total(x,z,θ) = w_gravity + w_thermal 在线性叠加意义下直接相加，离线生成新 bins 目录：
  - 写一个小脚本（可放 `scripts/thermal_proxy_model.py` 的 `merge` 子命令）：逐 bin 读 `data_proxy_steel/9x7_steel_t5_m05_fine/gravity_{ang}deg.bin` 与 `data_proxy_thermal/t2_laminate/gravity_{ang}deg.bin`（各 3×1024 float32），逐元素相加，写 `data_proxy_thermal/t4_combined/gravity_{ang}deg.bin`；拷贝 `influence_phi*.bin`、`gravity_angles.json`、`gravity_y.bin`。
  - 若 T2 结论是热形变不随 θ 变化：把单个热形变 bin 复制/叠加到全部 20 个角度 bin 上即可（20-bin 通路天然支持，无需改角度表）。
  - 渲染器只要把配置的 `influence_data_path` 指向 `data_proxy_thermal/t4_combined` 即可跑（`src/pipeline.cpp:486-550` 按文件大小自动识别 3-plane 格式）。
- **路线 B（独立 buffer，可微/可开关）**：新增 binding 31 `thermalMerged`（结构与 binding 30 `gravityMerged` 完全相同），改动点：
  - `shaders/bolt_common.slang`：binding 31 声明 + 在 `boltSurfaceAtGrid()`（bolt_common.slang:112）中把热场采样加到 y/yu/yv（复用 `sampleGravityField()` 的模式，热场可共享 gravityLo/Hi/T 插值下标）。
  - `src/pipeline.cpp`：buffer 创建/上传（pipeline.cpp:484-550 段落）、descriptor 写入（pipeline.cpp:660-725 段落）、配置键 `thermal_data_path`（`src/config.cpp` 的 extractFloat/extractString 模式，`lambda_energy` 见 config.cpp:138）。
  - push constant 加 `enableThermal` 开关（参考现有 `disableGravity`/`gravityNormalCoupling` 的传法，pipeline.cpp:785-786）。
  - 改完必须重编译 Slang shader 并更新 .spv（项目构建流程见 CMake/FindSlang.cmake）。
- 接入自检（幻影重力教训①）：跑渲染器后检查日志必须出现 20 行 `Loaded gravity_{ang}deg.bin (3-plane, wPV=...)`（pipeline.cpp:523），且每个 bin 恰好 12288 B；出现 `legacy 1-plane` 或 WARNING 即停。
- 门：路线 A 下渲染器 3 迭代烟雾（仿 §2.6 手册 (c) 步）Loss 正常、面型统计与「纯重力」+「纯热」之和一致（抽查一个网格点的 w 数值吻合到 float32 精度）→ Go T4。

### T4 端到端评估（0.5–1 天 GPU）

- 目标：在钢 t5 @margin 0.05 布局（9×7=63 栓，`configs/bolt_layouts/9x7_steel_t5mm_m05.json`）上比较「有/无热形变」的年均 S95。
- 步骤：
  1. 复制 `configs/archive/_steel_9x7_t5_eval334.json` 为 `configs/_cte_t4_eval334_thermal.json`（一次性配置，下划线前缀），把 `influence_data_path` 改为 `data_proxy_thermal/t4_combined`，`output_dir` 改为 `results_cte_t4_eval334_thermal`。评估口径不动（334 方向平衡集 `data/334_sundir_balanced.txt`，iterations=1，lr=0）。
  2. 对照组直接用既有结果（同一 eval 配置、`influence_data_path=data_proxy_steel/9x7_steel_t5_m05_fine` 的输出，`results_steel_9x7_t5_eval334/`）；若存档不全则重跑一遍对照，保证同二进制同太阳文件。
  3. 运行：`./build/src/Release/bezier_opt.exe --config configs/_cte_t4_eval334_thermal.json`（exe 路径见 `scripts/run_flux_validation.py:66`）。
  4. 若评估组差异显著，再跑优化组（仿 `_steel_9x7_t5_200i.json`：110dir 训练集、200 iter、comp init `data/init_comp/`），检验螺栓能否重新补偿热弯曲。
  5. 优化必须带 `lambda_energy` 约束（教训③；`src/config.cpp:138`，缺省 0.0 = 关闭，需显式设置，取值沿用对应材料线既有配置）。
- 产出：`results_cte_t4_eval334_thermal/` + `analysis/cte_endtoend_report.md`（有/无热形变 S95 对照表 + 结论）。
- 门（判读标准）：年均 S95 相对变化 < 1% → 热效应在代理口径下可忽略，论文加一句稳健性说明；1–5% → 论文补充材料报道；> 5% → 需要讨论层合板建模进主线，升级为本线正式章节。

---

## 4. 管线改造点清单

| 项 | 位置 | 改不改 |
|---|---|---|
| bins 生成 | `scripts/thermal_proxy_model.py`（新建，模板取自 `generate_proxy_model.py` 的 `generate_gravity_apdl()`） | 新增 APDL 热/分层段 |
| CSV→bin | `precompute_gravity_bins()`（generate_proxy_model.py:226） | 不改，直接复用（w = uy·cosθ + uz·sinθ 与 z/cosθ 解压对热形变同样成立） |
| C++ 加载 | `src/pipeline.cpp:486-550` | 路线 A 不改；路线 B 加 binding 31 buffer |
| shader | `shaders/bolt_common.slang`（binding 30 `gravityMerged`、`sampleGravityField()`、`boltSurfaceAtGrid()`） | 路线 A 不改；路线 B 加热场采样 |
| 角度插值 | C++ `gravityAnglesDeg[20]`（pipeline.cpp:761）与 shader `kGravityAngles`（bolt_common.slang:59） | 不改；热形变单 bin 时靠复制填满 20 bin |
| 配置 | `influence_data_path`（config.cpp） | 指向新目录即可 |
| 光学渲染 | 法线耦合 `gravityNormalCoupling`（bolt_common.slang:90-102） | 不改；热形变斜率经 bins 的 dw/du、dw/dv 平面自动进法线 |

---

## 5. ANSYS 建模要点

- 可执行文件：`L:/Program Files/ANSYS Inc/v252/ansys/bin/winx64/ANSYS252.exe`（generate_proxy_model.py:56）；批跑参数 `-b -np 4 -j <job> -i <dat> -o <out>`（`run_ansys()`，:534）。
- 坐标约定：板法向 (0, cosθ, +sinθ)（GUI 约定）；w = uy·cosθ + uz·sinθ；z 坐标解压 z_flat = z_tilt/cosθ（generate_proxy_model.py:284-300）。热形变提取沿用同一公式，**禁止改约定**。
- 螺栓 BC：NSEL ±0.3 m 窗口 patch 内 UX/UY/UZ=0（:474-484）。热问题下面内约束是热应力来源，属物理；但 patch 大小影响结果，敏感性抽查时勿动窗口尺寸。
- 单元与网格：SHELL181，KEYOPT(3)=2，映射网格 mesh_ndiv_x/z = 64/48（布局 JSON 控制）。分层用 SECDATA；层温度施加方式**执行时查 ANSYS SHELL181 文档核实**。
- 子步：NLGEOM,ON 时**必须细子步**（`NSUBST,50,500,50` 口径，教训②）。现模板 `NSUBST,1,10,1`（:491）对热-屈曲类问题不可接受。
- 温度参考：`TREF`/`MP,REFT` 必须显式设置并在报告中记录；ΔT 一律以相对 20°C 标注。
- 输出：7 列 CSV（x,y,z,ux,uy,uz,usum），节点循环 *VWRITE（:501-523），勿改格式。

T1 相对现模板的 APDL 最小改动示例（示意，行号对应 `generate_gravity_apdl()` 生成的 .dat）：

```apdl
! ── 材料段追加（现模板 :450-453 之后）──
MP,ALPX,1,1.2e-5        ! 钢 CTE，数值以 T0 文献结果为准（此处为占位）
MP,REFT,1,293           ! 参考温度 20°C

! ── 求解段替换（现模板 :487-498）──
/SOLU
ANTYPE,STATIC
NLGEOM,ON
AUTOTS,ON
NSUBST,50,500,50        ! 细子步（教训②；勿用模板默认 1,10,1）
PRED,ON
TREF,293
BF,ALL,TEMP,313         ! 均匀温升 ΔT = +20 K
ACEL,0,9.81,0           ! T1 可选：先关重力做纯热冒烟，再开重力对照
SOLVE
```

T2 分层壳改动示例（取代现模板单层 `R,1,thick`，:456）：

```apdl
! ── 分层截面：玻璃面层 + 钢背板（总厚 5mm，层厚比以 T0 结果为准）──
SECTYPE,1,SHELL
SECDATA,0.003,2         ! 层1：玻璃 3mm，材料号2
SECDATA,0.002,1         ! 层2：钢 2mm，材料号1
! 材料 2 = 玻璃：MP,EX,2,7.0e10 / MP,NUXY,2,0.22 / MP,DENS,2,2500 / MP,ALPX,2,<玻璃CTE>
```

---

## 6. 验证与防坑清单

历史教训（必须逐条落实）：

1. **幻影重力**：任何 bins 数据交接（含跨机器拷贝）后，验收 = ①每个 `gravity_*deg.bin` 恰好 12288 B（3 plane × 1024 × float32），②渲染器日志 20 行全为 `Loaded gravity_* (3-plane, ...)` 且无 legacy 警告（pipeline.cpp:523/532/544）。git 提交前 `git status` 确认 bins 已纳入（大文件策略按仓库现状执行）。
2. **粗子步跳支**：所有 NLGEOM run 用 `NSUBST,50,500,50`；报告中出现分支翻转/变号点移动时，第一动作是子步加密重跑裁决，不许直接采信（§3.8 教训）。
3. **能量溢出作弊**：T4 优化组必须设 `lambda_energy`（config.cpp:138；缺省 0 即关闭）；检查 history 中能量项无异常放大。

FEA 抽查规程：

- 每个阶段至少抽 1 个角度做网格加密对照（mesh_ndiv 128/96），w PV 变化 > 2% 则全批加密重跑。
- 每个新 APDL 模板先 `--dry-run`（gravity-ansys 子命令支持）人审 .dat，再跑真 FEA。
- 手算锚点：T1 的面内自由膨胀量 α·ΔT·L 与 ANSYS 面内位移场对比（量级不符即停）；T2 与 T0 的双金属公式估计对比（同量级即可，差 3 倍以上需解释）。
- T2 相减法（w_thermal = w_total − w_gravity）的对照 run 必须同网格、同子步、同 BC，仅温度载荷不同。
- bins 打包后必查 `gravity_angles.json` 的 `pv_mm`/`slope_rms_mrad` 元数据是否落在物理合理区间（`precompute_gravity_bins()` 自动输出，generate_proxy_model.py:337-348）；`nan_filled > 0` 需在报告中说明原因。

数据交接验收清单（每次跨机器/跨阶段交接 bins 时逐条打勾）：

- [ ] 每个 `gravity_*deg.bin` 文件大小恰为 12288 B（或 legacy 4096 B，但本实验禁止 legacy）。
- [ ] bin 数量与角度表一致（探针 3 个或全量 20 个），`gravity_angles.json` 在场。
- [ ] 渲染器日志 20/探针数行 `Loaded gravity_* (3-plane, ...)`，无 legacy 警告。
- [ ] `git status` 确认新 bins 已提交或被接收方实际收到（幻影重力教训①）。
- [ ] 交接记录写明：布局 JSON、材料参数、温度工况、NSUBST、网格、ANSYS 版本。

---

## 7. 数据与配置目录约定（2026-08-10 清理约定）

- 新实验数据：`data_proxy_thermal/`（子目录 `t1_uniform/`、`t2_laminate/`、`t4_combined/`，各含 `ansys_csv/` 中间产物）。
- 若需重建钢基线：`data_proxy_steel/` 下新建子目录，勿覆盖既有 `9x7_steel_t5_m05_fine/`。
- 布局配置：放 `configs/bolt_layouts/`（本实验复用 `9x7_steel_t5mm_m05.json`，一般无需新建）。
- 临时/一次性配置：放 `configs/` 根目录、下划线前缀（如 `configs/_cte_t4_eval334_thermal.json`），视为一次性，用后归档 `configs/archive/`。
- 分析报告：放 `analysis/`（`thermal_magnitude_estimate.md`、`thermal_bow_report.md`、`cte_endtoend_report.md`）。
- 结果：放仓库根 `results_cte_*/`。

---

## 8. 时间与资源估计

| 阶段 | 内容 | 估计 | 资源 |
|---|---|---|---|
| T0 | 文献 + 手算 | 0.5–1 天 | 无 |
| T1 | 3 角度均匀温升 FEA + 打包 | 半天（FEA 每角度数分钟级，参考 gravity-ansys 单次 < 600 s 超时，generate_proxy_model.py:534） | ANSYS 机 |
| T2 | 层合板热-力 FEA（2–3 工况 × 3–20 角度） | 1–2 天（主要耗在建模调试） | ANSYS 机 |
| T3 | bins 接入 + 烟雾 | 0.5 天（路线 A）；+0.5–1 天（路线 B 编译调试） | 台式机 |
| T4 | 端到端评估 ×2 + 可选优化 | 0.5–1 天 | 台式机 GPU |
| 合计 | | 约 3–5 个工作日 | |

硬依赖：ANSYS 许可证（T1/T2）、台式机 GPU 环境（T3/T4）。T0 不依赖任何机器，先行。

---

## 附录 A：命令速查

```bash
# T1/T2：打包 CSV → bins（复用重力通路，source-dir 指向本实验 CSV 目录）
python scripts/generate_proxy_model.py gravity \
    --source-dir data_proxy_thermal/t1_uniform/ansys_csv \
    --output-dir data_proxy_thermal/t1_uniform \
    --angles 10 46 80

# bins 质检：字节数（应输出 12288）
stat -c %s data_proxy_thermal/t1_uniform/gravity_10deg.bin

# 形场对比（cos_sim / α_w 探针分析，仿 M1 口径）
python scripts/material_swap_analysis.py \
    --baseline data_proxy_steel/9x7_steel_t5_m05_fine \
    --scan thermal=data_proxy_thermal/t2_laminate \
    --output analysis/thermal_bow_report.md

# T4：端到端评估（334 方向平衡集，iterations=1）
./build/src/Release/bezier_opt.exe --config configs/_cte_t4_eval334_thermal.json

# T4：优化组（110dir 训练集，200 iter；先确认 lambda_energy 已设置）
./build/src/Release/bezier_opt.exe --config configs/_cte_t4_200i_thermal.json
```

## 附录 B：关键文件索引

| 文件 | 作用 |
|---|---|
| `scripts/generate_proxy_model.py` | 重力 bins 全流程；`generate_gravity_apdl()` 为 APDL 模板母本；`precompute_gravity_bins()` 为 CSV→3-plane bin 打包器 |
| `scripts/thermal_proxy_model.py` | **本实验新建**：热/层合 APDL 生成 + bins merge 子命令 |
| `scripts/material_swap_analysis.py` | cos_sim/α_w 探针分析（M1 口径，直接复用于热形变场对比） |
| `scripts/layout_scan_analysis.py` | `stats_table()`：PV/斜率 RMS/三频带统计 |
| `shaders/bolt_common.slang` | binding 30 `gravityMerged`、`sampleGravityField()`、`boltSurfaceAtGrid()` |
| `src/pipeline.cpp:486-550` | bins 加载与 3-plane 格式自动识别；:761 角度插值 |
| `src/config.cpp:138` | `lambda_energy` 解析（缺省 0 = 关闭） |
| `configs/bolt_layouts/9x7_steel_t5mm_m05.json` | 钢 t5 @m05 布局（63 栓） |
| `configs/archive/_steel_9x7_t5_eval334.json` | 评估配置母本（334dir，iterations=1） |
| `configs/archive/_steel_9x7_t5_200i.json` | 优化配置母本（110dir，200 iter） |
| `data_proxy_steel/9x7_steel_t5_m05_fine/` | 钢 t5 纯重力 bins（对照组） |
| `docs/phase5_structural_optimization.md` §2.3/§3.2/§3.8 | 材料线结论与粗子步教训原始记录 |
