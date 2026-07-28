# 实验交接文档（笔记本 → 台式机迁移）

> 生成时间：2026-07-28 23:55（笔记本 RTX 4060 Laptop 8GB）。
> 用途：在台式机上 `git pull` 后，把本文档交给新会话的 Kimi，即可无缝继续实验。
> 生成时笔记本后台任务 `bash-0vw59byn` **仍在运行**（Phase 3 第 2/9 组收尾中），未被打断。

---

## 1. 给台式机 Kimi 的启动提示词（直接粘贴）

```
请阅读 docs/experiment_handoff.md 并按其"§5 剩余实验清单"继续 Phase 3/4 实验。
项目根即当前目录。先按 §5.1 检查 logs/_fw_*.log 各组完成度，切勿重复跑已有结果的组。
关键约束：只跑 300m NEWS 四镜（不跑 20 镜）；快速迭代用 36dir；终稿数字需 110dir 复核；
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

- 运行所需数据**已全部在仓库内**：`data_proxy/`（TPS 影响函数 + 20-bin 重力库，8.1MB）、`data/`（太阳方向、镜位、init 螺栓，含 `data/init_comp_36/` 锚定 init 与 anchor.bin）、`configs/`。无需重新生成。
- 台式机 GPU 只要是 Vulkan 兼容卡即可；显存 ≥8GB 稳妥（当前管线在 8GB 笔记本上运行）。

## 3. 项目一句话与文档地图

**在做什么**：定日镜螺栓行程（35 DOF）→ TPS 物理代理（含 FEA 重力库、法向耦合）→ 可微 MCRT → 年均 S95 的端到端优化；当前核心叙事是"重力地板的可补偿性认证"（导师问题：proxy 是否真起优化作用）。

| 文档 | 读它为了什么 |
|---|---|
| **本文档** | 交接总入口 |
| `docs/gravity_compensation_experiment.md` | 实验设计 + 假设 + **全部进度日志**（先读末尾三条 2026-07-28 日志） |
| `analysis/gravity_compensability_report.md` | Phase 0 诊断（形变三分解、子空间覆盖率 26–38%） |
| `analysis/real_gravity_penalty_table.md` | Phase 1 二十镜真实重力惩罚表（110dir 终版） |
| `docs/submission_strategy_and_outline.md` | 投稿方向（首选 AEI）+ 论文大纲 + 后续工作清单 |
| `docs/draft.md` | 论文中文初稿（摘要+引言+相关工作） |
| `CLAUDE.md` | 工程文档：编译/架构/参数/正则套件配置键 |

## 4. 实验现状快照（截至 2026-07-28 23:55）

### 4.1 已完成（数字定稿，36dir / 300m NEWS / S95 m²）

| 镜 | B_ideal (LSQ无重力) | B_naive (重力) | B_comp (闭式补偿init) | B\* (无重力优化下界) |
|---|---|---|---|---|
| North | 51.32 | 51.31 | 51.75 | **49.77** |
| East | 65.68 | 77.90 | 76.71 | **65.00** |
| South | 73.51 | 98.33 | 94.90 | **73.07** |
| West | 65.60 | 78.07 | 76.83 | **64.68** |

重力惩罚 = naive−ideal：N −0.01 / E +12.22 / S +24.82 / W +12.47。comp init 仅回收 10–14%。

### 4.2 Phase 3 已完成组（日志与结果已随仓库提交）

| 组 | 配置 | North | East | South | West | 结论 |
|---|---|---|---|---|---|---|
| `_fw_tanh_a0`（基线，150iter） | tanh 无正则 | 50.34 | 76.21 | 94.28 | 76.19 | **端到端仅回收 ~15%，iter~80 硬平台——重力地板是硬的** |
| `_fw_tanh_a1e3`（提交时 3/4） | +锚定 λ=1e3 | 50.42 | 76.26 | 94.33 | （跑批中） | 弱锚定≈基线（噪声内） |

North 侧 a0 端到端降到 50.34 < naive 51.31、< ideal 51.32（距 B\* 仅 0.57）——优化器正常，E/S/W 推不动是物理不是优化失败。

### 4.3 笔记本仍在跑

任务 `bash-0vw59byn` 按顺序执行剩余组（每组 4 镜 × 100 iter ≈ 3.3h@4060 Laptop）：
`a1e3(收尾) → a1e4 → a1e5 → nt_soft1e5 → nt_a1e3_soft1e5 → nt_a1e3_soft1e6 → tanh_a1e3_b1e2`。
**协调规则（避免撞车）**：二选一——
- **方案 A（笔记本跑完）**：等笔记本链条结束（约 07-29 20:00），在笔记本上 `git add -f logs results_fw_* && git commit && git push`，台式机只做第 9 组 + Phase 4；
- **方案 B（台式机接管，推荐若台式机已就绪）**：在笔记本当前组跑完边界时 `TaskStop bash-0vw59byn`，commit+push 已有结果，台式机从第一个无结果的组起跑（台式机 GPU 更快，剩余每组可能 <1.5h）。

## 5. 剩余实验清单（台式机接续协议）

### 5.1 检查完成度（每次开工先做）

```bash
for f in logs/_fw_*.log; do echo "$f: $(grep -c 'Done. Best S95' "$f" 2>/dev/null)/4"; done
```

### 5.2 顺序跑批（按需删去已完成组；日志落 logs/）

```bash
for c in _fw_tanh_a1e4 _fw_tanh_a1e5 _fw_nt_soft1e5 _fw_nt_a1e3_soft1e5 _fw_nt_a1e3_soft1e6 _fw_tanh_a1e3_b1e2 _fw_tanh_naiveinit; do
  echo "=== $c ==="; ./build/src/Release/bezier_opt.exe "configs/$c.json" > "logs/$c.log" 2>&1; echo "exit=$?"
done
```

配置均已就位（`configs/_fw_*.json`）：300m NEWS、36dir、coupling=1、comp init（`_fw_tanh_naiveinit` 除外，用 `data/init_lsq/`）、100 iter、lr=4e-4、stroke≤0.06。**第 9 组 `_fw_tanh_naiveinit` 务必跑**——检验地板是否 init 无关，是证据链闭环。

### 5.3 八组跑完后：汇总消融对照表

模板（回收率 = (naive−best)/(naive−ideal)，对 E/S/W 三镜分别算）：

| 组 | N | E | S | W | E/S/W 回收率 | 行程/弯曲能（从日志 Bolt stroke 行取） |
|---|---|---|---|---|---|---|

写入 `docs/gravity_compensation_experiment.md` 进度日志。

### 5.4 Phase 4 清单

1. **差距四层表终版**：36dir（已有）+ **110dir 复核**——⚠️ 36dir 对 E/W 镜训练过拟合 +1.7 m²（`sundir_sample/EXPERIMENT_REPORT_EAST_WEST.md`），论文终稿数字必须至少 110dir 训练、334dir 验证。110dir 每镜每 100 iter ≈ 3×36dir 耗时，按台式机算力排期。
2. **FEA 抽查**：`python scripts/post_fea_validation.py --stroke-file results_fw_tanh_a0/<mirror>_STROKE_bolts.txt --angles 29.5 58.5`（用法见 CLAUDE.md 末尾；需 ANSYS 许可证，无许可证可跳过并在论文误差预算中沿用已有 North 两角度数据）。
3. **CLAUDE.md 更新**：正则套件 5 个配置键已写；待补——重力耦合修复后的可比性声明、Phase 3 结论一段。
4. **论文回填**：`docs/draft.md` 中 `[TODO: P3]` 处填端到端回收率；叙事按"认证地板"定调（见 §4.2 结论）。

## 6. 关键工程细节与坑

1. **lr 语义**：tanh 与物理（tanh_bound=0）两种模式零点物理步长都等于 lr（`pipeline.cpp:996` lrComp 分支），两种模式均用 lr=4e-4。CLAUDE.md 旧建议"nt 模式 1.6e-5"已作废。
2. **patience 早停实际不触发**（相对变化阈值 1e-6 在 Adam 爬行下永不满足）——不要依赖它，用固定 iter 数（当前 100，平台证据充分）。
3. **计时口径**：日志 `time=82s` 是含验证的迭代；普通迭代 ~24s，均值 ~30s（4060 Laptop）。外推总时长用均值，别用 82s。
4. **编译防 LNK1104**：build 前确认无 `bezier_opt.exe` 在跑（`ps -W | grep bezier_opt`，有则 `taskkill //IM bezier_opt.exe //F`）。
5. **探针代码**：`pipeline.cpp/h` 内有 BEZIER_DEBUG_EVAL 调试分支与 `m_dbgEvalRound` 成员，默认关闭，勿删（Phase 4 后清理）。
6. **重力数据格式**：`data_proxy/gravity_angles.json` 为 v2 三平面格式（w, dw/du, dw/dv），C++ 按文件大小自动识别，勿用旧脚本重新生成覆盖。
7. **提交结果回仓库**：`results_*/` 在 .gitignore 中，提交需 `git add -f results_fw_xxx logs/xxx.log`（docs/ 已改为可跟踪）。

---

> 若交接文档与实际状态冲突（例如笔记本又跑完了更多组），以 `logs/_fw_*.log` 与 `docs/gravity_compensation_experiment.md` 末尾进度日志为准。
