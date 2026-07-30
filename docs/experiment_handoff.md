# 实验交接文档（笔记本 → 台式机迁移）

> 生成时间：2026-07-28 23:55（笔记本 RTX 4060 Laptop 8GB）。
> **第 2 版：2026-07-29 12:15** —— a1e4/a1e5/nt_soft1e5 结果入库；超时事故记录；双机分工重排（笔记本收尾 3 组，台式机接 110dir 终稿数字）。
> 用途：在台式机上 `git pull`（或 clone bundle）后，把本文档交给新会话的 Kimi，即可无缝继续实验。

---

## 1. 给台式机 Kimi 的启动提示词（直接粘贴）

```
请阅读 docs/experiment_handoff.md 并按其"§5 剩余实验清单"继续实验。项目根即当前目录。
先按 §5.1 检查 logs/_fw_*.log 各组完成度：笔记本已完成的组一律不跑（当前分工见 §5.2）。
关键约束：只跑 300m NEWS 四镜（不跑 20 镜）；快速迭代用 36dir；终稿数字用 110dir（§5.2 任务 2/3）；
编译方法与坑见 §2 与 §6。每完成一个阶段，在 docs/gravity_compensation_experiment.md 追加进度日志。
```

## 2. 环境搭建（台式机首次）

```bash
# 1) 安装依赖：Vulkan SDK（版本以本机实际安装为准）、VS2022、CMake、Python(numpy/scipy/matplotlib)
# 2) 编译（首次 configure 会经 FetchContent 联网下载 fmt/glm/Slang）
export VULKAN_SDK="C:\\VulkanSDK\\<本机版本>"
"/c/Program Files/CMake/bin/cmake.exe" -S . -B build -G "Visual Studio 17 2022" -A x64
"/c/Program Files/CMake/bin/cmake.exe" --build build --config Release
# 3) 改了 .slang 后必须：rm -f build/shaders/*.spv 再重新 build
# 4) 运行
./build/src/Release/bezier_opt.exe configs/<name>.json
```

- 运行所需数据**已全部在仓库内**：`data_proxy/`（TPS 影响函数 + 20-bin 重力库，8.1MB）、`data/`（太阳方向、镜位、init 螺栓，含 `data/init_comp_36/`、`data/init_comp/`（110dir）锚定 init 与 anchor.bin）、`configs/`。无需重新生成。
- 台式机 GPU 只要是 Vulkan 兼容卡即可；显存 ≥8GB 稳妥。
- ~~离线迁移后备：bundle~~（已作废：两个 bundle 文件均已删除，且 2026-07-30 仓库历史重写后旧 bundle 与新历史不兼容；一律以 git clone 为准）。

## 3. 项目一句话与文档地图

**在做什么**：定日镜螺栓行程（35 DOF）→ TPS 物理代理（含 FEA 重力库、法向耦合）→ 可微 MCRT → 年均 S95 的端到端优化；当前核心叙事是"重力地板的可补偿性认证"（导师问题：proxy 是否真起优化作用）。

| 文档 | 读它为了什么 |
|---|---|
| **本文档** | 交接总入口 |
| `docs/gravity_compensation_experiment.md` | 实验设计 + 假设 + **全部进度日志**（先读末尾 2026-07-28/29 的日志） |
| `analysis/gravity_compensability_report.md` | Phase 0 诊断（形变三分解、子空间覆盖率 26–38%） |
| `analysis/real_gravity_penalty_table.md` | Phase 1 二十镜真实重力惩罚表（110dir 终版） |
| `docs/submission_strategy_and_outline.md` | 投稿方向（首选 AEI）+ 论文大纲 + 后续工作清单 |
| `docs/draft.md` | 论文中文初稿（摘要+引言+相关工作） |
| `CLAUDE.md` | 工程文档：编译/架构/参数/正则套件配置键 |

## 4. 实验现状快照（截至 2026-07-29 12:15）

### 4.1 基线与下界（定稿，36dir / 300m NEWS / S95 m²）

| 镜 | B_ideal (LSQ无重力) | B_naive (重力) | B_comp (闭式补偿init) | B\* (无重力优化下界) |
|---|---|---|---|---|
| North | 51.32 | 51.31 | 51.75 | **49.77** |
| East | 65.68 | 77.90 | 76.71 | **65.00** |
| South | 73.51 | 98.33 | 94.90 | **73.07** |
| West | 65.60 | 78.07 | 76.83 | **64.68** |

重力惩罚 = naive−ideal：N −0.01 / E +12.22 / S +24.82 / W +12.47。comp init 仅回收 10–14%。
110dir 对照（Phase 1，全 20 镜）：B_ideal = 51.57/66.74/72.43/66.92（与 36dir 偏差 <2.4%）。

### 4.2 Phase 3 已完成组（36dir，S95 m²；回收率 = (naive−best)/(naive−ideal)）

| 组 | 配置 | N | E | S | W | E/S/W 回收率 | 结论 |
|---|---|---|---|---|---|---|---|
| `_fw_tanh_a0`（基线） | tanh 无正则 | 50.34 | 76.21 | 94.28 | 76.19 | 13.8/16.3/15.1% | **端到端仅 ~15%，iter~80 硬平台——重力地板是硬的** |
| `_fw_tanh_a1e3` | +锚定 λ=1e3 | 50.42 | 76.26 | 94.33 | 76.18 | ≈基线 | 弱锚定无效果（噪声内） |
| `_fw_tanh_a1e4` | +锚定 λ=1e4 | 50.48 | 76.27 | 94.26 | 76.14 | ≈基线 | 同上 |
| `_fw_tanh_a1e5` | +锚定 λ=1e5 | 50.73 | 76.33 | 94.47 | 76.29 | 略差 | **强锚定开始压制仅存增益——锚定冗余假设成立** |
| `_fw_nt_soft1e5` | 解除 tanh+软墙 | 50.37 | 76.21 | 94.29 | 76.12 | ≈基线 | **tanh 硬界完全无影响（East 四位小数相同）——硬界不是地板成因** |

North 侧 a0 端到端降到 50.34 < naive 51.31、< ideal 51.32（距 B\* 仅 0.57）——优化器正常，E/S/W 推不动是物理不是优化失败。五个独立角度（子空间投影、端到端平台、锚定扫描、无界化、North 对照）已同指"**结构性硬地板**"。

### 4.3 笔记本仍在跑（勿重复）

任务 `bash-xatj04c5`（无超时）顺序执行最后 3 组，预计 **2026-07-29 ~21:30** 收工：
`_fw_nt_a1e3_soft1e5`（12:05 时 1/4）→ `_fw_nt_a1e3_soft1e6` → `_fw_tanh_a1e3_b1e2`。
收工后笔记本自动：汇总消融表入 `docs/gravity_compensation_experiment.md` → 本地 commit → 睡眠。
> 事故记录：原链条 `bash-0vw59byn` 于 07-29 09:15 撞 20h 超时被杀（死在 nt_a1e3_soft1e5 开头，无成果损失），剩余组以 `bash-xatj04c5` 重启。

## 5. 剩余实验清单（双机分工）

### 5.1 检查完成度（每次开工先做）

```bash
for f in logs/_fw_*.log; do echo "$f: $(grep -c 'Done. Best S95' "$f" 2>/dev/null)/4"; done
```

### 5.2 分工

**笔记本（已在跑，台式机不要碰）**：`_fw_nt_a1e3_soft1e5`、`_fw_nt_a1e3_soft1e6`、`_fw_tanh_a1e3_b1e2`（36dir，100iter，每组 ~3.4h@4060 Laptop）。

**台式机（按序执行）**：

```bash
# 任务 1：第 9 组（36dir，~1–1.5h）——LSQ init 端到端，检验地板是否 init 无关
./build/src/Release/bezier_opt.exe configs/_fw_tanh_naiveinit.json > logs/_fw_tanh_naiveinit.log 2>&1

# 任务 2：B*@110dir 终稿下界（~6–10h；配置为 200iter，可改 150——平台证据在 iter~100）
./build/src/Release/bezier_opt.exe configs/_bound_nograv_300m.json > logs/_bound_nograv_300m.log 2>&1

# 任务 3：a0@110dir 终稿回收率（100iter，~3–5h）——配置需新建（见下）
./build/src/Release/bezier_opt.exe configs/_fw_tanh_a0_110.json > logs/_fw_tanh_a0_110.log 2>&1
```

**任务 3 配置创建法**：复制 `configs/_fw_tanh_a0.json` 为 `configs/_fw_tanh_a0_110.json`，改四处——`sun_train_file` 与 `sun_validation_file` → `data/110_sundir_paper.txt`、`bolt_init_dir` → `data/init_comp/`、`output_dir` → `results_fw_tanh_a0_110`。

### 5.3 结果汇合（关键！）

笔记本 push 受限（github.com git 端点被重置），**a1e4/a1e5/nt_soft1e5 及今晚 3 组的结果在笔记本本地提交里**。汇合方式择一：
1. 网络恢复后笔记本 `git push`（或用户手动推）；
2. 笔记本今晚跑完后再生成新 bundle（`git bundle create diff_helio_handoff2.bundle master`），用户带至台式机 `git pull ../diff_helio_handoff2.bundle master`。

汇合后由任一方出**九组消融全表**（模板：`docs/gravity_compensation_experiment.md` 进度日志（五）或按 §4.2 扩展），写入进度日志。

### 5.4 Phase 4 清单（汇合后）

1. **差距四层表终版**：36dir（已有，§4.1/§4.2）+ 110dir（台式机任务 2/3 完成后填入）。⚠️ 36dir 对 E/W 镜训练过拟合 +1.7 m²（`sundir_sample/EXPERIMENT_REPORT_EAST_WEST.md`），论文终稿数字以 110dir 为准、334dir 前向验证收尾。
2. **FEA 抽查**：`python scripts/post_fea_validation.py --stroke-file results_fw_tanh_a0/<mirror>_STROKE_bolts.txt --angles 29.5 58.5`（用法见 CLAUDE.md 末尾；需 ANSYS 许可证，无许可证可跳过并在误差预算中沿用已有 North 两角度数据）。
3. **CLAUDE.md 更新**：补 Phase 3 结论一段（"结构性硬地板 + 五重证据"）。
4. **论文回填**：`docs/draft.md` 中 `[TODO: P3]` 处填端到端回收率（36dir ~15%，以 110dir 为准）；叙事按"认证地板"定调。

## 6. 关键工程细节与坑

1. **lr 语义**：tanh 与物理（tanh_bound=0）两种模式零点物理步长都等于 lr（`pipeline.cpp:996` lrComp 分支），两种模式均用 lr=4e-4。CLAUDE.md 旧建议"nt 模式 1.6e-5"已作废。
2. **patience 早停实际不触发**（相对变化阈值 1e-6 在 Adam 爬行下永不满足）——不要依赖它，用固定 iter 数（当前 100，平台证据充分）。
3. **计时口径**：日志 `time=82s` 是含验证的迭代；普通迭代 ~24s，均值 ~30s（4060 Laptop，36dir）。110dir 约为 3 倍。外推总时长用均值，别用 82s。
4. **后台任务超时**：Bash(run_in_background) 默认 600s、显式上限 24h；长链条务必 `disable_timeout=true`（`bash-0vw59byn` 撞 20h 超时被杀的教训，§4.3）。
5. **编译防 LNK1104**：build 前确认无 `bezier_opt.exe` 在跑（`ps -W | grep bezier_opt`，有则 `taskkill //IM bezier_opt.exe //F`）。
6. **探针代码**：`pipeline.cpp/h` 内有 BEZIER_DEBUG_EVAL 调试分支与 `m_dbgEvalRound` 成员，默认关闭，勿删（Phase 4 后清理）。
7. **重力数据格式**：`data_proxy/gravity_angles.json` 为 v2 三平面格式（w, dw/du, dw/dv），C++ 按文件大小自动识别，勿用旧脚本重新生成覆盖。
8. **提交结果回仓库**：`results_*/` 在 .gitignore 中，提交需 `git add -f results_fw_xxx logs/xxx.log`（docs/ 已改为可跟踪）。

---

> 若交接文档与实际状态冲突（例如任一方又跑完了更多组），以 `logs/_fw_*.log` 与 `docs/gravity_compensation_experiment.md` 末尾进度日志为准。
