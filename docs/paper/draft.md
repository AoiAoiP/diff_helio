# 论文草稿 — 使用物理耦合可微渲染方法的定日镜面型优化

> **目标期刊**：Computational Visual Media (CVM，CCF-B) 或 Advanced Engineering Informatics(AEI，CCF-B)
> **叙事主线**：
旧问题：纯几何优化无物理可达性→ 
新框架：可微渲染嵌入物理代理→ 
新分析：分析有多少空间是优化器可达的→ 
新知识：重力惩罚机理与结构性界限→ 
新设计：螺栓排布结构重设计

> **状态说明（非正文）**：
2026.8.10 ：设计大纲，框架初稿
2026.8.11 ：全文章节AI初稿完成，**不可用**。
2026.8.14 ：按 RPW 流程重写 §2 相关工作（重构为四小节：可微渲染 / 物理信息仿真 / 能流仿真 / 面型优化；新增占位引用）。
2026.8.14 ：按 RPW 流程改写 §3 系统模型与问题形式化（新增章节总览段；纬度统一为 37.36°N；45°/46° 统一为 46°；倾角表改编号为表 2，后续表顺延为表 3–6；46° 变号点标注占位）。
2026.8.14 ：参考文献在`ref/`目录下；占位编号 [n] 须逐一核对 bibliographic details。
2026.9.1 ：重构文章框架并确认。
2026.9.2 ：写完摘要+引言+相关工作正文 *插图仍需绘制。*
2026.9.3 ：§1–§2 并入正文；参考文献重排至 [1]–[32]，TBC 已核 18 条。
2026.9.4 ：§3 并入正文；参考文献扩至 [1]–[35]。


> **文章框架**
写作语言规范：段落之间靠论点自然衔接，段首句直接承载内容；禁止"本段/本章/本小节说明…"等元话语，禁止以"总之/综上/概括而言/由此可见/简言之"作段尾模板式收束；无破折号；无"不是…而是…/而非"结构；无"正是/恰"；正文不设"与相关工作的定位对比表"类表格（工作差异并入行文）。
```
0  文章定位与投递期刊
    核心贡献：
    - 贡献 1：物理耦合可微渲染框架。 
        本文提出将 FEA 衍生的薄板样条代理与多倾角重力解嵌入 GPU 可微蒙特卡洛光线追踪渲染器的端到端管线，以显式表面场为渲染管线的一等输入，使"结构形变→表面法向→光路→光斑"的完整因果链对机械设计变量端到端可微。
    - 贡献 2：梯度优化方法的界限分析。 
        基于框架的梯度子空间分解，本文将面型优化差距区分为优化器可达分量与支撑几何可达分量，回答"给定支撑布局下，面型调节的物理上限在哪里"。对重力惩罚显著的镜位，分析表明 84%–87% 的优化差距位于梯度不可达的支撑几何子空间，且不可达分量集中于螺栓支撑点间的悬挑区域。
    - 贡献 3：界限驱动的结构层重设计。 
        依据界限分析将不可达分量归因于悬挑弯曲，本文以螺栓边距、网格密度与镜面材料为杠杆压低结构性界限，使优化结构的光斑面积与理想几何结构的差距收窄至 4%–10%，且红利集中于分析预先判定的悬挑主导镜位，验证了界限分析的预测能力。
    
    投递期刊：Advanced Engineering Informatic（AEI），CCF-B，IF≈11.5

1  引言（Introduction）
    介绍塔式光热太阳能；
    介绍镜面面型优化的必要性，以及镜面实际在物理环境遇到的问题；
    介绍利用可微优化方法设计镜面的现状；
    指出存在的问题：1）现有镜面微观表达仅使用斜率误差进行法向随机扰动，没有将全镜面几何按物理规则进行仿真，进一步无从进行最优优化；2）现有面型优化，要么是纯几何的可微优化，没有实际物理意义；要么使用FEA工具进行传统优化，与光追框架脱节。
    
    本文提出新框架——物理耦合可微渲染：
    框架简述：将物理规律嵌入可微优化框架中，寻求最优形变，以及探究镜面形变成因，并基于成因设计新的最优方案。
    框架应用：利用新工具探究形变成因
    面型优化方案：根据成因设计新最优面型，并逼近理想面型。
2  相关工作（Related Work）
    2.1 定日镜能流仿真：说明定日镜能流仿真（可微光追系 vs 离线结构-光学耦合系），以及重要性
    2.2 定日镜面型优化：说明定日镜面型与结构优化，以及必要性
    2.3 物理信息仿真：说明物理信息机器学习方法在工程设计的应用
    2.4 可微渲染：说明图形学中的可微渲染方法
3  框架介绍（Method：Physics-Coupled Differentiable Rendering）
    3.1 问题陈述 & 符号规定 （Problem Statement & Notation）
        说明优化变量、坐标系规定。并加入符号表
    3.2 GPU 可微 MCRT 渲染器
        (参考Yuan论文)简述框架光学端部分，说明可微光线追踪算法
    3.3 FEA衍生的TPS物理代理模型
        3.3.1 表面参数化：说明表面模型表达式 w(u, v) = w_{grav}(u, v; θ) + Σ h_b · Φ_b(u, v)
        3.3.2 重力部分说明：20-bin、三平面查找表
        3.3.3 TPS部分说明：TPS核说明、Tikhonov 正则设定
    3.4 正则化与约束：L = L_{S95} + λ_E · L_{energy}，其它约束不要了，不影响结果，且避免消融实验抢占篇幅。
    3.5 框架梯度链说明：说明框架全景与梯度链，螺栓 → 面型  → 能流 → S95
    
4  框架验证实验（Framework Validation）
    4.1 代理精度验证
    - 实验目的：验证提出的物理代理与FEA结果差距较小，以证明框架物理端流程可行
    - 实验方法：使用物理代理正向计算同一螺栓排布、不同倾角下的表面形变场，并于Ansys Mechical结果进行对比
    - 实验结果：R2>0.98, RMS<0.2mm, 法向误差<0.99
    4.2 光斑仿真验证
    - 实验目的：验证移植后的光学模块与已发表 RMCRT 前向模型一致，并给出代理面型误差的光斑级误差预算
    - 实验方法：绘制不同镜面倾角下，本框架正向渲染出的光斑与现有成熟光追框架渲染出的光斑
    - 实验结果：面型匹配度>0.998，光斑总能量差距<1%
    4.3 梯度正确性验证
        解析梯度 vs 有限差分。
    4.4 端到端性能分析
    - 评估框架自身时空开销
    - 与传统离线串行优化范式的对比
5 框架应用实验（Application: Gravity-Limited Heliostat Surface Design）
    5.1 实验设置
    说明镜面参数、镜场设置、螺栓排布、太阳方向采样策略
    5.2 重力形变影响分析
        说明重力影响镜面的机理——局部高阶凹陷
    5.3 可补偿性界限分析
        说明优化空间中有哪些部分是由于螺栓排布造成的结构性地板。并指明结构重构的必要性
    5.4 结构层重设计
        包含螺栓排布/螺栓密度/镜面材料三个方向，最终使得优化结果光斑逼近纯几何结果光斑。
    5.5 全镜场泛化实验
        推广到全镜场进行实验。并进行讨论。
6  讨论与结论（Discussion & Conclusion）
    6.1 设计规则与方法论意义
    6.2 局限与未来工作
```

>**文章贡献**

- 贡献 1：物理耦合可微渲染框架。 
本文提出将 FEA 衍生的薄板样条代理与多倾角重力解嵌入 GPU 可微蒙特卡洛光线追踪渲染器的端到端管线，以显式表面场为渲染管线的一等输入，使"结构形变→表面法向→光路→光斑"的完整因果链对机械设计变量端到端可微。

- 贡献 2：梯度优化方法的界限分析。 
基于框架的梯度子空间分解，本文将面型优化差距区分为优化器可达分量与支撑几何可达分量，回答"给定支撑布局下，面型调节的物理上限在哪里"。
对重力惩罚显著的镜位，分析表明 84%–87% 的优化差距位于梯度不可达的支撑几何子空间，且不可达分量集中于螺栓支撑点间的悬挑区域。

- 贡献 3：界限驱动的结构层重设计。 
依据界限分析将不可达分量归因于悬挑弯曲，本文以螺栓边距、网格密度与镜面材料为杠杆压低结构性界限，
使优化结构的光斑面积与理想几何结构的差距收窄至 4%–10%，且红利集中于分析预先判定的悬挑主导镜位，验证了界限分析的预测能力。

> **文章图清单**

**制图规范**：图内文字一律英文（投 AEI）；示意图用矢量（PDF/EPS），数据图输出 PDF + 600 dpi PNG 供审阅；组合图 500 dpi；单栏宽 90 mm、1.5 栏 140 mm、双栏 190 mm；缩放后最小字号 ≥7 pt；线宽 0.8–1.2 pt；色盲友好配色（Okabe-Ito：`#0072B2 #D55E00 #009E73 #CC79A7 #E69F00 #56B4E9`），禁止仅靠红/绿区分；matplotlib 设 `pdf.fonttype=42` 保证文字可编辑。

| 编号 | 位置 | 类型 | 内容要点 | 数据/素材来源 | 工具 | 优先级 |
|---|---|---|---|---|---|---|
| 图 1 | §1 第二段 | 示意图 | (a) 塔式电站侧视（塔/接收器/镜场/入射光/倾角 θ）；(b) 单镜剖面：玻璃板 + 7×5 螺栓支撑 + 重力与风载箭头 + 形变后凹陷 vs 理想面；(c) 形变前后光斑对比小图 | TikZ 主体 + matplotlib 光斑插图 | TikZ | 高 |
| **图 2** | §1 第六段、§3 章首 | **管线图（teaser）** | 力学域（35 螺栓 h → TPS Φ_b + 20-bin 三平面重力表 → 表面场 w/∇w → 法向）+ 光学域（Buie → 双层折射 → 接收器 157×50 → flux → S95 二分 → sigmoid 损失）+ 反向梯度链（dL/dh 三通道 → 投影 → Adam），标注"单次 submit 端到端可微" | 代码结构（§3） | **TikZ** | **最高** |
| 图 3 | §3.1 | 示意图 | 板面俯视（以 $W, L, N_b$ 符号标注，不写取值）+ 侧视（u/v/y 轴、法向 n、倾角 θ 与塔方位） | §3.1 符号表 | TikZ | 高 |
| 图 4 | §3.5 | 示意图 | 跨域梯度链：三通道贡献项、力学域与光学域在表面法线处衔接 | §3.5 公式 (7) | TikZ | 中（可并入图 2 面板 b） |
| 图 5 | §4.1 | 数据图 | Proxy｜FEA｜残差 三面板 + 中心剖面 + 逐行 RMS | `run_fea_validation.py` 已产出同款 | matplotlib（改造现有脚本） | 高 |
| 图 6 | §4.2 | 数据图 | 本框架 vs RMCRT 光斑并排 + S95 等值线 + 水平/垂直剖面 + 蒙特卡洛噪声地板 | `run_flux_validation.py` 已产出同款 | matplotlib（改造现有脚本） | 高 |
| 图 7 | §4.3 | 数据图 | 解析梯度 vs 有限差分（散点 + cos 相似度/比值条） | `--check-grad` 输出 | matplotlib | 中 |
| 图 8 | §4.4 | 数据图 | 阶段耗时堆叠条 + 随太阳方向数/网格的扩展曲线 + 与传统串行（2N+1 次评估）对数坐标对比 | 需在 `pipeline.cpp` 补计时点 | matplotlib | 中 |
| 图 9 | §5.2 | 数据图 | 多倾角形变场 pcolormesh + PV–倾角曲线 + 悬挑处剖面 | `data_proxy/ansys_csv` + bins | matplotlib | 高 |
| 图 10 | §5.3 | 数据图 | 三档 S95 柱状（理想/实际/优化）+ 梯度可达 vs 不可达分量场图（标注悬挑区域） | Phase 0–3 结果 | matplotlib | **最高**（贡献 2 的证据） |
| 图 11 | §5.4 | 数据图 | margin（U 形曲线，标出最优带）｜密度｜材料 三面板 | Phase 5 结果 | matplotlib | 高 |
| 图 12 | §5.5 | 数据图 | 20 镜位布置 + 回收率/结构性残余的空间着色 | 全镜场结果 | matplotlib | 中 |

**表清单**：表 1 §5.1 镜面/镜场参数与太阳方向采样策略；表 2 §4 验证指标汇总（代理精度、光斑一致性、梯度一致性）；表 3 §5.4 结构杠杆对比（边距/密度/材料）。

**绘图工具链（本机已核查）**：TikZ（TeXLive 2025，`latexmk -pdf`，示意图首选，矢量且与正文同字体）；matplotlib 3.10.9（数据图，共享 `.mplstyle`）；ImageMagick 7.1.1（DPI/格式转换、拼版）；可选 PyVista（3D 面型/光路，需 `pip install pyvista`）。本机无 Inkscape，如需手绘矢量建议安装或用在线 draw.io 导出 PDF。

**建议目录结构**：输出 `docs/paper/figs/`；TikZ 源与样式 `docs/paper/figs/src/`；数据图脚本 `scripts/paper_figures/figNN_*.py`（每图一脚本，数据目录参数化）；`docs/paper/figs/README.md` 记录"图号 → 脚本 → 数据源"映射。

**素材缺口（决定绘图排期）**：图 5 需带螺栓行程的 FEA 点云（本机无 ANSYS，需台式机）；图 6 需 RMCRT 对比结果；图 9–12 需从台式机同步 `results_*` 与 Phase 5 数据；图 8 需在 `pipeline.cpp` 补 2–3 个计时点。

**推进顺序**：图 2（不依赖实验数据，决定第一印象）→ 图 1、图 3 → 改造图 5/图 6 脚本 → 数据齐备后做图 9–12。


---

# 正文

**题目**

使用物理耦合可微渲染方法的定日镜面型优化
Physics-Coupled Differentiable Rendering for Heliostat Surface Optimization

**摘要**

可微渲染方法假设交互面为纯几何，梯度止于表面参数；当表面本身是结构载荷的函数时，梯度必须穿越力学与光学域的边界。本文提出了物理耦合可微渲染框架：以薄板样条函数代理将螺栓行程映射为连续表面场，并将多倾角有限元重力解嵌入自研GPU可微蒙特卡洛光线追踪渲染器，将光斑面积S95（包含95%通量的区域）的最小化作为优化目标，使“结构形变→表面法向→光路→光斑”对机械设计变量端到端可微。框架的直接产物是一种此前不可行的分析：将面型优化差距分解为优化器可达与支撑几何可达两个分量，从而回答"给定支撑布局下，面型调节的物理上限在哪里"。在20面定日镜、全年334个太阳方向的实验揭示：重力经发现偏转造成结构化光学扰动，惩罚随镜位相差 3–4 倍，80–90% 源于螺栓点位间的悬挑弯曲；固定 35 螺栓布局下，84–87% 的优化空间结构性不可达。以上限分析指导结构层重设计，使优化结构与理想几何结构的光斑面积差距收窄至 4%–10%，红利集中于上限分析预先判定的镜位。结果表明，将物理代理嵌入可微渲染不仅使跨域优化可行，更使"优化器边界"与"物理系统边界"的区分成为可计算的对象。

**关键词**：可微渲染；物理信息渲染；GPU 光线追踪；薄板样条；结构-光学耦合；定日镜；

---

## 1. 引言

塔式太阳能聚光（CSP）电站以数千面定日镜将太阳直射光反射至塔顶接收器，镜场投资与光学精度是电站成本与效率的关键瓶颈 [1]。单镜面型决定其反射光斑的形状与尺寸：光斑越大，溢出接收器的能量越多，聚光效率越低。面型质量因此贯穿镜面制造、安装与服役的全生命周期，是塔式电站光学设计的核心关切。工程中镜面由螺栓排布支撑，出厂面型是各螺栓行程在薄板上的力学平衡结果，螺栓顶升成型的光-机集成分析已建立支撑参数与光学精度之间的定量关系 [2, 3]。镜面投入运行后，重力、风载与热膨胀持续作用于板面，使其偏离出厂设计形状，产生连续形变，反射光斑随之退化（图 1），结构有限元分析是评估这类载荷形变的常规手段 [4]。面型设计因而不能停留在理想几何曲面，物理载荷作用下的服役面型才是优化应当面对的对象。

CSP 工程仿真体系长期以单一标量斜率误差 $\sigma_S$ 刻画镜面质量，主流蒙特卡洛光线追踪工具（SolTrace [5]、Tonatiuh [6]）与解析卷积模型（HFLCAL [7]、UNIZAR [8]）将其与太阳日轮做统计卷积，以高斯随机法向扰动计入形变的光学影响。标量化对随机制造误差是合理的近似，但服役载荷作用下的镜面形变具有确定性的空间结构：已有工作以有限元与计算流体动力学求解重力与风载下的镜面形变，并将其显式编码用于光学性能分析 [9]；螺栓顶升成型的光-机集成分析同样表明面型随支撑参数确定性地变化 [2, 3]。这类确定性形变模式与标量刻画预设的随机误差统计存在性质差异，其光学后果难以由标量统计完整回答。

在标量刻画的传统之外，可微蒙特卡洛光线追踪近年为 CSP 光学引入了梯度驱动的设计手段：镜场瞄准策略优化 [10]、子镜倾角优化 [11]、在役电站原位计量 [12]，以及由光斑反演面型的逆向深度学习方法 [13, 14]。这些工作验证了可微光追梯度在 CSP 光学中的工程可用性，是本文光学模块的直接技术基础。然而这些工作的优化对象仍是抛物面、椭圆面、Bezier 曲面等理想参数曲面，设计变量停留在瞄准点、倾角等面板级刚体自由度上，真实形变的发生过程始终位于可微计算图之外。

结构工程一侧则沿离线串行路线处理面型设计：以有限元求解载荷下的真实形变，再串行接入光线追踪评估，螺栓顶升成型的光-机集成分析 [2, 3]、伞形与三脚架定日镜的联合设计 [15, 16]、风致形变的多物理场评估 [17] 与自动调形定日镜 [18] 均属此列。这一路线物理上真实，但每一步评估需一次完整有限元求解加一次完整光追，参数空间探索受限于枚举步长。可微路线与离线路线各自的梯度止于几何参数或物理量，均无法穿越力学与光学两个域，现有方法因此无从回答"给定支撑布局下，面型调节的物理上限在哪里"这一设计性问题。

为突破这一两难，本文提出物理耦合可微渲染（physics-coupled differentiable rendering）框架：以薄板样条代理把螺栓行程映射为连续表面场，嵌入多倾角有限元重力解，经 GPU 可微蒙特卡洛光线追踪渲染，以光斑面积 S95 为优化目标（图 2），使结构形变、光路与光斑对机械设计变量端到端可微。面型优化差距由此可分解为优化器可达与支撑几何可达两个分量，从而使"给定支撑布局下，面型调节的物理上限"成为可计算的问题。框架首先被用于探究形变成因：重力惩罚的镜位差异与结构性界限由梯度子空间分析定量给出，依据成因的支撑结构重设计（螺栓边距、网格密度、镜面材料）进一步把优化面型推向无重力理想面型。

本文的主要贡献如下：
1. **物理耦合可微渲染框架**：以显式表面场为渲染管线一等输入，使结构形变到光斑的因果链对机械设计变量端到端可微（§3）。
2. **梯度可达性的界限分析**：将面型优化差距分解为优化器可达与支撑几何可达两个分量，对重力惩罚显著的镜位，84%–87% 的差距位于梯度不可达的支撑几何子空间，且集中于螺栓支撑点间的悬挑区域（§4，§5.3）。
3. **界限驱动的结构层重设计**：以螺栓边距、网格密度与镜面材料压低结构性界限，使优化结构与理想几何结构的光斑面积差距收窄至 4%–10%，红利集中于分析预先判定的悬挑主导镜位（§5.4–5.5）。

全文其余部分安排如下：§2 回顾相关工作并明确本文定位，§3 阐述框架，§4 给出验证实验，§5 报告应用结果与结构层重设计，§6 总结全文。

---

## 2. 相关工作

定日镜工程一侧，能流仿真（§2.1）给出光斑计算工具与两条面向真实形变的路线，面型与结构优化（§2.2）给出设计变量的层级与优化边界；方法基础一侧，物理信息仿真（§2.3）与可微渲染（§2.4）分别从科学计算与图形学逼近"梯度穿越物理域边界"的问题。本章按从应用场景到方法根源的顺序回顾，四条脉络止步之处构成本文要接通的四个断点。

### 2.1 定日镜能流仿真：可微光追系与离线结构-光学耦合系

吸热器能流密度预测是定日镜光学设计的计算基石，直接服务于接收器设计与镜场布局评估。成熟工具构成一条前向管线：蒙特卡洛光线追踪（MCRT）是公认的精度基准，代表为 SolTrace [5] 与 Tonatiuh [6]；解析卷积模型以误差统计均匀假设换取解析速度，代表为 HFLCAL [7] 与 UNIZAR [8]；学习器路线以紧凑网络回归光斑参数，如 Fast-NCM [19] 在 16 ms 内完成全场能流仿真；采样方案的精度与成本权衡也有专门研究 [20]。这些工具把镜面质量压缩为单一标量斜率误差 $\sigma_S$，再与太阳日轮做统计卷积。服役载荷下的形变具有确定性的空间结构 [9]，标量统计难以完整承担其光学后果（定量论证见 §5.2）。

面向真实形变的能流计算沿两条路线展开。可微光追系以可微蒙特卡洛光线追踪从表面法向场直接生成能流并回传梯度，覆盖瞄准策略、子镜倾角、原位计量与面型反演四类任务 [10, 11, 12, 13, 14]；其表面仍是理想参数曲面，梯度止于瞄准点、倾角等面板级自由度，形变过程不进入计算图。离线结构-光学耦合系以有限元或计算流体动力学求解载荷形变，再串行接入光线追踪评估，代表工作包括螺栓顶升成型 [2, 3]、伞形与三脚架定日镜 [15, 16]、风致形变多物理场 [17]、重力与风载形变编码 [9] 与面型调节机构 [18]；其形变场显式进入光路，代价是每次评估需一次结构求解加一次全场光追。两条路线的分工清晰：一条提供梯度但表面理想化，一条提供真实形变但没有梯度。

### 2.2 定日镜面型优化：设计变量与优化边界

面型优化的必要性来自服役形变：出厂面型由支撑结构决定，载荷作用下的形变直接改变光斑 [2, 3, 9]。既有工作的设计变量沿层级上行：几何配置层的瞄准策略与子镜倾角 [10, 11]，结构参数层的螺栓间距、数量与顶升行程 [2, 3]，把结构尺寸与光学误差联合权衡的伞形与三脚架定日镜 [15, 16]，纳入风致载荷的多物理场评估 [17]；面型本身作为可调对象出现在面型调节机构 [18] 与子镜倾角调试实践 [21] 中。变量层级越高，可补偿的光学误差越丰富，对评估方式的要求也越高。

现有优化方式在该层级上留下三处边界。第一是优化粒度：离线路线的每次评估都要完整求解两个物理域，参数空间只能按枚举步长探索，梯度无法引导搜索方向。第二是评估指标：离线路线的光学指标是变形网格导出的斜率误差，并未直接以光斑面积 S95 为目标（两者的定量差距见 §5.2），而可微路线的目标虽为光斑，其表面却停留在理想几何。第三是分析深度：参数扫描回答"哪组参数更好"，无法回答"给定支撑布局下，任何调节策略的物理上限在哪里"；后者要求把优化差距按梯度可达性分解，只有端到端可微的管线才提供这种分解能力（§5.3）。

### 2.3 物理信息仿真：梯度终止于物理量

科学计算一侧，物理信息机器学习 [22] 把物理约束嵌入学习系统；可微结构优化 [23] 与物理信息数字孪生 [24, 25] 使设计变量经由物理模型获得梯度；图形学内部的可微物理模拟同样实现了物理状态对仿真参数的微分，代表为可微弹性体 [26] 与可微流体 [27]。这一脉络证明"物理状态对参数可微"在工程与图形学中均已可行，与本文的目标方向一致。

本文与上述工作存在两点系统性差异。第一点在梯度终端：这些工作的梯度终点是位移、应力、流场等物理状态本身，本文的梯度继续延伸至经光学渲染后的辐射度分布，两个域的梯度在表面法线处衔接；终端位置的不同直接影响物理代理的设计，代理的精度需求取决于位移误差经光学低通滤波后产生的光斑面积误差（§4.2）。第二点在代理形态：主流范式训练神经代理逼近物理求解器，误差随训练分布漂移，难以审计；本文采用解析推导的 TPS 几何代理，梯度精确，误差预算可与有限元解直接对比，这一可审计性是 §5.3 界限分析成立的前提。

### 2.4 可微渲染：固定表面的隐含前提

图形学可微渲染把逆图形学问题转化为梯度驱动优化，Mitsuba 2 [28] 建立了可重定向的可微前向与逆向渲染基础设施，ZeroGrads [29] 把梯度估计扩展到含可见性不连续性的复杂光路，镜面高光等病态逆渲染问题也因可微正则化而可解 [30]。这些框架共享一个隐含前提：表面几何是渲染的固定输入，物理载荷不参与表面的形成，梯度反传止于位置、法向、材质系数等表面交点参数。本文将连续表面场（高度场与法向场）提升为渲染管线的一等输入，使梯度经表面场继续反传至机械设计变量；这一"稀疏控制点驱动连续曲面"的表示与几何处理中的形变控制结构同源，如 cage 形变 [31] 与 blendshape 形变 [32]，其方法论联系在 §6 讨论。

---

## 3. 框架介绍 Method：Physics-Coupled Differentiable Rendering

物理耦合可微渲染框架把机械设计变量、镜面形变与接收器光斑串成一条可微链条（图 2）。力学端以薄板样条影响函数与多倾角重力查找表把螺栓行程映射为显式表面场（§3.3）；光学端以 GPU 可微蒙特卡洛光线追踪把表面场渲染为接收器能流，并给出光斑面积 S95（§3.2）；反向阶段让光斑损失的梯度沿表面法线穿回力学端，投影为螺栓梯度（§3.5）。损失函数中的能量项与行程约束把优化限制在物理可行的解域内（§3.4）。问题形式化与记号先于三者给出（§3.1）。

### 3.1 问题陈述与符号规定

**定日镜面板与局部坐标系。** 定日镜面板为矩形玻璃镜，宽 $W$、长 $L$、厚 $t$，由 $N_b$ 根支撑螺栓按矩形网格支撑（图 3）。板上建立局部坐标系 $O_{uvy}$：$u$ 轴沿板宽方向，$v$ 轴沿板长方向，$y$ 轴沿板法向朝外。镜面在局部坐标下的法向位移场记作 $w(u, v)$，单位为 m，正位移指向 $+y$。倾角 $\theta$ 定义为板法向与铅垂方向的夹角，$\theta = 0°$ 对应板面水平朝天，$\theta = 90°$ 对应板面竖直，其瞬时值由镜位、时刻与跟踪策略共同决定。

**设计变量、目标与约束。** 设计变量为各螺栓的法向调节量 $h \in \mathbb{R}^{N_b}$，正方向指向板法向，物理上对应螺栓顶升行程。给定太阳方向 $s$，螺栓行程经物理代理映射为表面场（§3.3），渲染器据此产生接收器能流分布（§3.2）；光斑面积 $S_{95}$ 定义为包含 95% 接收能量的最小像素集合的面积。优化问题写为

$$\min_{h} \quad \sum_{s \in \mathcal{S}} S_{95}\big(\mathrm{Flux}(h; s)\big) \tag{1}$$

其中 $\mathcal{S}$ 为全年太阳方向样本集，目标取样本方向上的平均光斑面积，属于面型质量指标，不引入能量权重；样本集的构造方式与月间分布见 §5.1。约束为行程界 $|h_b| \leq h_{\max}$，由有界参数化在优化过程中严格满足（§3.4）。$S_{95}$ 的定义包含排序，该操作不可微，目标函数实际由 sigmoid 替代函数驱动（§3.2）。本文实验所用系统的具体取值集中在 §5.1 表 1 给出。

**符号表。**

| 符号 | 含义（单位） |
|------|------|
| $W, L, t$ | 面板宽、长、厚（m） |
| $N_b$ | 支撑螺栓数 |
| $h, h_b$ | 螺栓行程向量及其第 $b$ 个分量（m） |
| $w(u,v)$ | 板局部坐标下的法向位移场（m） |
| $w_{\mathrm{grav}}$ | 零螺栓纯重力 FEA 解（m） |
| $\phi_b$ | 第 $b$ 根螺栓的 TPS 影响函数 |
| $\theta$ | 倾角（板法向与铅垂方向夹角，rad） |
| $S_{95}$ | 含 95% 能量的最小光斑面积（m²） |
| $\mathcal{S}$ | 全年太阳方向样本集 |
| $h_{\max}$ | 螺栓行程界（m） |
| $\sigma_S$ | 高斯统计斜率误差（rad） |
| $y_u, y_v$ | 表面场对 $u$、$v$ 的一阶导数 |
| $N_{spp}$ | 每像素采样光线数 |
| $R, H$ | 接收器半径与高度（m） |
| $N_x, N_y$ | 接收器方位向与高度向像素数 |
| $A_{\mathrm{px}}$ | 接收器像素面积（m²） |
| $n, d$ | 玻璃折射率与单层厚度（m） |
| $E, E_{\mathrm{ref}}$ | 当前接收总能量、迭代 0 的参考总能量（W） |
| $\lambda_E$ | 能量效率项权重 |
| CSR, DNI | 太阳环日比、直射辐照（W/m²） |


### 3.2 GPU 可微蒙特卡洛光线追踪渲染器

**光学路径与能量模型。** 渲染器在 Vulkan 计算着色器上实现，光学端沿用本课题组可微蒙特卡洛光线追踪框架的设计 [10, 11]，包括距离衰减模型与太阳形状归一化方式。光线从接收器像素反向发出，在镜面交点由表面场的高度与切向斜率构造法向，经双层玻璃折射（折射率 $n$、单层厚度 $d$）偏转，并叠加高斯统计斜率误差（$\sigma_S$，两层各一次）后按与太阳方向的夹角采样太阳形状。太阳光源取 Buie 日轮模型 [33]（环日比 CSR，直射辐照 DNI），接收器为圆柱面（半径 $R$、高度 $H$），离散为 $N_x \times N_y$ 像素。每个接收器像素向镜面射出 $N_s$ 条光线，每条光线对应一个镜面网格点，对像素能流的贡献为

$$e = \mathrm{DNI} \cdot \frac{A_m}{N_s} \cdot \frac{\cos(\mathrm{inc}) \cdot \cos(\mathrm{px})}{r^{2}} \cdot \tau(r) \cdot \frac{SS(\theta_{\mathrm{sun}})}{2\pi \int SS\,\mathrm{d}\Omega} \tag{2}$$

其中 $A_m = W \cdot L$ 为镜面面积，$\cos(\mathrm{inc})$ 为镜面入射余弦，$\cos(\mathrm{px})$ 为接收器像素朝向与光线方向的余弦，$r$ 为镜面点到像素的距离，$\tau(r)$ 为距离衰减，$SS(\theta_{\mathrm{太阳}})$ 为日轮角分布。渲染器的设计约束是：任意显式表面场（高度与两个切向斜率）可以直接作为一等输入，且整条光路对该输入可微。这一约束把本文渲染器与把表面质量压缩为标量 $\sigma_S$ 的前向工具区分开来。

**S95 的可微化。** $S_{95}$ 的原始定义 [11] 包含排序：把像素按能流从高到低累加，取达到总能量 95% 所需的最小像素面积。排序不可微，阈值处又带有硬边界，两者都不能直接进入梯度优化。框架保持阈值按原始定义在设备端求解，并另用 logistic 函数在阈值处做光滑替代：

$$L_{S95} = \sum_{p} \sigma\!\Big(\kappa \big(\mathrm{flux}_p / \mathrm{level} - 1\big)\Big), \qquad \sigma(x) = \frac{1}{1 + e^{-x}}, \quad \kappa = 6 \tag{3}$$

其中 $\kappa$ 为光滑替代的陡度参数，由本文固定取 6，不随工况与镜位调整。高于阈值的像素贡献正损失，低于阈值的像素贡献负损失，梯度把像素能流推向阈值轮廓；接收器像素面积 $A_{\mathrm{px}} = 2\pi R H / (N_x N_y)$ 为常数，阈值以上像素数与 $A_{\mathrm{px}}$ 的乘积即评估阶段的 $S_{95}$ 面积，优化目标与评估指标因此使用同一阈值语义。阈值求解与损失累加都在设备端完成，优化循环内不需要把能流分布传回主机。

$\kappa$ 的作用是设定阈值附近过渡带的宽度：自变量 $\mathrm{flux}_p / \mathrm{level} - 1$ 已完成阈值归一化，过渡带宽度约为 $\pm 1/\kappa$。该取值使阈值附近的梯度既不因过度平滑而抹掉光斑边界，也不因过度陡峭而饱和；替代损失随 $\kappa$ 增大趋近硬阈值指标，$\kappa = 6$ 下的梯度一致性由 §4.3 的有限差分对照检验。

### 3.3 FEA 衍生的 TPS 物理代理模型

#### 3.3.1 表面参数化

物理代理把机械设计变量映射为渲染器的一等输入。板局部坐标下的法向位移场由两项叠加：

$$w(u, v) = w_{\mathrm{grav}}(u, v; \theta) + \sum_{b=1}^{N_b} h_b \, \phi_b(u, v) \tag{4}$$

第一项为零螺栓纯重力解，随倾角变化（§3.3.2）；第二项为螺栓单位位移影响函数的线性叠加（§3.3.3）。影响函数取薄板样条形式，理由是它与薄板弯曲理论的同源性：核 $r^2 \log(r^2)$ 是双调和方程的基本解，TPS 插值等价于在插值约束下最小化弯曲能泛函 $\iint (w_{uu}^{2} + 2w_{uv}^{2} + w_{vv}^{2})\,\mathrm{d}u\,\mathrm{d}v$ [34]，其形变模式在几何上复现 Kirchhoff 薄板的最小弯曲能形状。代理是几何意义上的，不含板的材料刚度与边界条件，作用是在解析可微的前提下复现形变模式，与有限元解的偏差在 §4.1 定量给出。影响函数满足单位分解 $\sum_b \phi_b \equiv 1$，整体平移可由所有螺栓等量增减表达，代理因此不把刚体位移混入面型自由度。

#### 3.3.2 重力模型：20-bin 三平面查找表

重力项 $w_{\mathrm{grav}}$ 承担表面场中与设计变量无关的部分。板在支撑点上成型后，自重产生的弯沉由支撑布局与材料刚度决定，螺栓行程只提供围绕这一基线的局部调节。把两项分开的直接好处是重力场只随倾角 $\theta$ 变化：它可以离线求解并按角度查找，优化循环中不需要重复求解结构，设计变量只进入螺栓影响函数的线性叠加项。这一分解有一项代价需要预先说明：螺栓行程改变板内应力状态，从而对重力弯沉产生二阶影响，本文的线性分解忽略该耦合，其偏差在 §4.1 与有限元解的对比中定量给出。

重力场由零螺栓纯重力有限元解给出。板按四节点壳单元离散，壳单元以中面位移描述薄板弯曲，附加的非协调模式用于改善低阶单元在弯曲主导问题中的精度；网格取规则映射网格，节点排布确定，便于与点云逐点比对；求解打开几何非线性，以计入大倾角下膜应力带来的几何刚化。所有螺栓在零螺栓状态下固定为零位移，板的材料参数、几何尺寸与网格设置在 §5.1 给出。重力弯沉随倾角呈显著非线性变化。查找表取 20 个倾角 bin（10°–80°，间距不超过 4°），倾角方向线性插值；每个 bin 存三个平面，即位移 $w$ 与两个物理斜率 $\partial w / \partial x$、$\partial w / \partial z$。三个平面在 $32 \times 32$ pixel-centered 网格上以中央差分计算，差分前可做高斯平滑以抑制离散噪声，20 个 bin 合并为单个 GPU buffer 供着色器按角度索引读取。倾角插值残余的定量评估在 §4.1 给出。

三平面格式的动机是法向耦合。渲染器由切向量 $\mathbf{t}_u = (W, y_u, 0)$ 与 $\mathbf{t}_v = (0, y_v, L)$ 的叉积构造法向 $\mathbf{n} = -(\mathbf{t}_u \times \mathbf{t}_v)/\|\mathbf{t}_u \times \mathbf{t}_v\|$，重力导数经单位换算 $y_u = (\partial w/\partial x)\,W$、$y_v = (\partial w/\partial z)\,L$ 进入切向量。若查找表只存位移而把斜率置零，弯沉不改变表面朝向，重力形变对反射方向的影响随之消失；三平面格式让重力同时进入表面高度与表面朝向，形变到光路的因果链在渲染器中闭合。

#### 3.3.3 TPS 影响函数

对每根螺栓 $b$，在 $32 \times 32$ 归一化网格上求解薄板样条系统：

$$\begin{bmatrix} \mathbf{K} & \mathbf{P} \\ \mathbf{P}^{\mathsf{T}} & \mathbf{0} \end{bmatrix} \begin{bmatrix} \mathbf{c} \\ \mathbf{d} \end{bmatrix} = \begin{bmatrix} \mathbf{e}_b \\ \mathbf{0}_3 \end{bmatrix} \tag{5}$$

其中 $K_{ij} = r_{ij}^{2} \log(r_{ij}^{2})$ 为 TPS 核，$r_{ij}$ 为网格点 $i$ 与螺栓 $j$ 的距离，$\mathbf{P} = [\mathbf{1}, \mathbf{x}, \mathbf{z}]$ 为多项式项，用于精确恢复仿射分量，$\mathbf{e}_b$ 为第 $b$ 个标准基向量。对角加 Tikhonov 正则 $\lambda = 10^{-6}$，作用是在保持插值约束的前提下稳定数值求解：TPS 系统的条件数随节点规模增长，本文规模下量级为 $10^{6}$，微小对角项把求解从接近奇异的状态拉回可解范围。核在原点取极限为零，而系统对角元为 $\phi(0) + \lambda$，因此需要在每根螺栓最近的网格点上补回 $\lambda$ 项，避免螺栓自位置的影响被系统性压低。系统规模为 $(N_b + 3) \times (N_b + 3)$，一次性直接求解，全部影响函数的生成在秒级完成。

求解后，网格点上的 $\phi_b$ 及其一阶导数 $\partial \phi_b / \partial u$、$\partial \phi_b / \partial v$ 按归一化坐标解析给出，与位移场一同存为三张查找表。两组性质用于检查构造是否正确，也用于判断正则项是否扭曲了插值：单位分解 $\sum_b \phi_b \equiv 1$ 的峰谷值约 $1.3 \times 10^{-6}$；螺栓自影响（影响函数在自身位置的值）经网格修正后落在 $[0.94, 1.02]$，均值 0.98，接近理论值 1。网格采用与渲染一致的 pixel-centered 约定，避免影响函数与表面采样之间存在半像素偏移。

### 3.4 正则化与约束

**能量效率项。** 只最小化 $S_{95}$ 时，优化器可以把光线驱出接收器，让光斑因能量不足而虚假收缩，因此损失中加入能量效率项：

$$L = L_{S95} + \lambda_E \cdot M \cdot \frac{E_{\mathrm{ref}}}{E} \tag{6}$$

其中 $M$ 为接收器像素数，$E$ 为当前接收总能量，$E_{\mathrm{ref}}$ 为迭代 0 时逐太阳方向记录的参考能量。$M$ 的作用是让该项与 sigmoid 损失同量级；$E$ 减小时该项增大，梯度方向是把能量保持住。$\lambda_E = 0$ 时损失退化为纯 $S_{95}$ 损失。该项权重按能量保持与光斑收益之间的权衡确定：近距镜的接收器张角大，光线不易溢出，可将 $\lambda_E$ 置零；远距镜下若只最小化 $S_{95}$，优化器会把光线驱出接收器以换取虚假的小光斑，需要非零权重，扫描结果与取值见 §5.1。

**行程约束。** 螺栓行程受物理界 $h_{\max}$ 约束（取值见 §5.1），框架把物理行程映射到无界参数 $\varepsilon$：$h_b = h_{\max} \tanh(\varepsilon_b)$，在 $\varepsilon$ 空间用 Adam [35] 更新，链式因子 $\mathrm{d}h/\mathrm{d}\varepsilon = h_{\max}(1 - \tanh^{2}\varepsilon)$ 使零点附近的物理步长与直接参数化一致，学习率按 $lr / h_{\max}$ 补偿。该参数化让约束在设计上严格满足，迭代中不需要截断或投影。

### 3.5 框架梯度链

损失对螺栓行程的梯度穿越力学与光学两个域。对每根螺栓 $b$，

$$\frac{\mathrm{d}L}{\mathrm{d}h_b} = \sum_{s \in \mathcal{S}} \sum_{p} \left[ \frac{\partial L}{\partial \mathrm{flux}_p} \left( \frac{\partial \mathrm{flux}_p}{\partial y} \phi_b + \frac{\partial \mathrm{flux}_p}{\partial y_u} \frac{\partial \phi_b}{\partial u} + \frac{\partial \mathrm{flux}_p}{\partial y_v} \frac{\partial \phi_b}{\partial v} \right) \right] \tag{7}$$

括号内三项分别对应表面高度、$u$ 向斜率与 $v$ 向斜率变化对像素能流的贡献。力学域的分量（$\phi_b$ 及其导数）由影响函数查找表解析给出，光学域的分量（能流对 $y$、$y_u$、$y_v$ 的偏导）由渲染器在反向通道上经自动微分给出，两个域在表面法线处衔接（图 4）。力学域的线性性 $\partial w / \partial h_b = \phi_b$ 精确成立，投影步骤因此只涉及固定系数加权求和，不需要在力学域再做一次自动微分。

梯度的计算与正向渲染共用同一套表面场数据，并在设备端完成：每个太阳方向执行一次前向与反向，方向集上的螺栓梯度求和后送入 Adam [35] 完成一次参数更新，优化循环内不需要把能流分布传回主机。由于梯度对设计变量逐分量可解，面型优化差距可以按梯度可达性进一步分解为优化器可达与支撑几何可达两个分量，这一分析在 §5.3 展开。

---

## 4. 框架验证实验（Framework Validation）
### 4.1 代理精度验证
    - 实验目的：验证提出的物理代理与FEA结果差距较小，以证明框架物理端流程可行
    - 实验方法：使用物理代理正向计算同一螺栓排布、不同倾角下的表面形变场，并于Ansys Mechical结果进行对比
    - 实验结果：R2>0.98, RMS<0.2mm, 法向误差<0.99
### 4.2 光斑仿真验证
    - 实验目的：验证移植后的光学模块与已发表 RMCRT 前向模型一致，并给出代理面型误差的光斑级误差预算
    - 实验方法：绘制不同镜面倾角下，本框架正向渲染出的光斑与现有成熟光追框架渲染出的光斑
    - 实验结果：面型匹配度>0.998，光斑总能量差距<1%
### 4.3 梯度正确性验证
        解析梯度 vs 有限差分。
### 4.4 端到端性能分析
    - 评估框架自身时空开销
    - 与传统离线串行优化范式的对比
## 5. 框架应用实验（Application: Gravity-Limited Heliostat Surface Design）
### 5.1 实验设置
    说明镜面参数、镜场设置、螺栓排布、太阳方向采样策略
### 5.2 重力形变影响分析
        说明重力影响镜面的机理——局部高阶凹陷
### 5.3 可补偿性界限分析
        说明优化空间中有哪些部分是由于螺栓排布造成的结构性地板。并指明结构重构的必要性
### 5.4 结构层重设计
        包含螺栓排布/螺栓密度/镜面材料三个方向，最终使得优化结果光斑逼近纯几何结果光斑。
### 5.5 全镜场泛化实验
        推广到全镜场进行实验。并进行讨论。
## 6.讨论与结论（Discussion & Conclusion）
### 6.1 设计规则与方法论意义
### 6.2 局限与未来工作

## 参考文献



1. [Zhu-roadmap-2022] Guangdong Zhu, Chad Augustine, Rebecca Mitchell, Matthew Muller, Parthiv Kurup, Alexander Zolan, Shashank Yellapantula, Randy Brost, Kenneth Armijo, Jeremy Sment, Rebecca Schaller, Margaret Gordon, Mike Collins, Joe Coventry, John Pye, Michael Cholette, Giovanni Picotti, Maziar Arjomandi, Matthew Emes, Daniel Potter, Michael Rae. "Roadmap to Advance Heliostat Technologies for Concentrating Solar-Thermal Power." NREL Technical Report NREL/TP-5700-83041, 2022. (verified from local PDF)
2. [Yan-bolt-2024] Bin Li, Jian Yan*, Wei Zhou, Youduo Peng. "Influence of Service Load and Structural Parameters on Optical Accuracy of Solar Tower Heliostat"（服役载荷与结构参数对塔式太阳能定日镜光学精度的影响）. *Acta Optica Sinica*, 2024, 44(6): 0623001. DOI: 10.3788/AOS231688. (verified)
3. [Yan-bolt-jacking-2025] Jian Yan*, Tianchi Song, Youduo Peng, Wei Zhou. "Optical Accuracy Study of Pentagonal Tower Solar Heliostat Based on Support Bolt Jacking Molding"（基于支撑螺栓顶压成型的五边形塔式太阳能定日镜光学精度研究）. *Acta Optica Sinica*, 2025, 45(6): 0608001. DOI: 10.3788/AOS241006. (verified)
4. [FEA-CFD-FEM-2018] "Heliostat structural optimization: A study of wind load effects with CFD-FEM methods." *AIP Conference Proceedings* 2033: 210001, 2018（SolarPACES 2017, Santiago, Chile）. DOI: 10.1063/1.5067203. (venue/DOI verified via AIP 与 Zenodo record 1483403；作者列表待核)
5. [SolTrace-2003] T. Wendelin. "SolTRACE: A New Optical Modeling Tool for Concentrating Solar Optics." *Proc. ASME International Solar Energy Conference (ISEC2003)*, 2003: 253–260. (verified)
6. [Tonatiuh-2005] M. J. Blanco, J. M. Amieva, A. Mancillas. "The Tonatiuh Software Development Project: An Open Source Approach to the Simulation of Solar Concentrating Systems." *Proc. ASME IMECE2005*, 2005: 157–164. (verified)
7. [HFLCAL-2006] S. Schmitz, P. Schwarzbözl, R. Buck, R. Pitz-Paal. "Assessment of the Potential Improvement due to Multiple Apertures in Central Receiver Systems with Secondary Concentrators." *Solar Energy*, 2006, 80(1): 111–120. (verified)
8. [UNIZAR-1986] F. J. Collado, A. Gómez, J. A. Turégano. "An Analytic Function for the Flux Density due to Sunlight Reflected from a Heliostat." *Solar Energy*, 1986, 37(3): 215–234. (verified)
9. [deformation-encoding-2025] "Heliostat Surface Deformation and Encoding under Gravity and Wind Loads for Optical Performance Analysis." *Renewable Energy*, 2025, 250. (PII: S0960148125008419；作者列表待核，机构为浙江大学 CAD&CG 国家重点实验室)
10. [aiming-DMCRT-2025] Xiaoxia Lin, Cangping Zheng, Wenjun Huang, Yuhong Zhao, Jieqing Feng. "A Novel Heliostat Aiming Optimization Framework via Differentiable Monte Carlo Ray Tracing for Solar Power Tower Systems." *Applied Energy*, 2025, 388: 125640. (verified)
11. [canting-DRT-2025] Yichen Yuan, Xiaoxia Lin, Xiaoling Mi, Jieqing Feng*, Yuhong Zhao*. "The Optimization of Heliostat Paraboloid Canting via Differentiable Ray Tracing." *Solar Energy*, 2025, 301: 113901. (verified from local PDF)
12. [Pargmann-2024] Max Pargmann, Jan Ebert, Markus Götz, Daniel Maldonado Quinto, Robert Pitz-Paal, Stefan Kesselheim. "Automatic Heliostat Learning for In Situ Concentrating Solar Power Plant Metrology with Differentiable Ray Tracing." *Nature Communications*, 2024, 15: 6997. (verified)
13. [inverse-DL-RT-2025] Jan Lewen, Max Pargmann, Mehdi Cherti, Jenia Jitsev, Robert Pitz-Paal, Daniel Maldonado Quinto. "Inverse Deep Learning Raytracing for Heliostat Surface Prediction." *Solar Energy*, 2025, 289: 113312. (verified)
14. [sim2real-DL-RT-2025] J. Lewen, M. Pargmann, J. Jitsev, M. Cherti, R. Pitz-Paal, D. Maldonado Quinto. "Scalable Heliostat Surface Predictions from Focal Spots: Sim-to-Real Transfer of Inverse Deep Learning Raytracing." *Solar Energy*, 2025, 300: 113726. (verified)
15. [Yang-umbrella-2022] Moucun Yang, Yiluo Zhang, Qinggang Wang, Yuezhao Zhu, Robert A. Taylor. "A Coupled Structural-Optical Analysis of a Novel Umbrella Heliostat." *Solar Energy*, 2022, 231: 880–888. DOI: 10.1016/j.solener.2021.12.031. (verified)
16. [Thalange-tripod-2017] Vinayak C. Thalange, Vishwanath H. Dalvi, Sanjay M. Mahajani, Sudhir V. Panse, Jyeshtharaj B. Joshi, Raosaheb N. Patil. "Design, Optimization and Optical Performance Study of Tripod Heliostat for Solar Power Tower Plant." *Energy*, 2017, 135: 610–624. DOI: 10.1016/j.energy.2017.06.116. (verified)
17. [CFD-FEM-optical-2026] Wen Zhang, Guohua Xing, Junjie Tao, Mingtong Wei, Yanru Wu, Yin Liu, José F. Gallego. "Multi-Physics Investigation of Concentrating Efficiency Degradation in Heliostats Caused by Wind-Induced Deformations." *Renewable Energy*, 2026, 258: 124939. (verified)
18. [Angel-autoshape-2022] Roger Angel, Nick Didato, Matt Rademacher. "Heliostat with Automatic Shape Adjustment for High Concentration Throughout the Day." *SolarPACES 2022* conference proceedings, 2022. (verified from local PDF; 卷期/DOI 待核)
19. [Fast-NCM-2026] Lin et al. "Real-Time Radiative Flux Density Distribution Simulation via Data-Driven Neural Convolution Model for Solar Power Tower Systems." Preprint / under review, 2026. (lab-internal; bibliographic status TBC)
20. [Ye-sampling-2026] 叶晋炜, 何才透. "定日镜场地光学效率模拟中的蒙特卡洛光线跟踪方法中时间采样点灵敏度分析研究." 计算机科学与应用 (Computer Science and Application), 2026, 16(3): 96–105. DOI: 10.12677/csa.2026.163090. (verified from local PDF)
21. [canting-practice-2023] "Terrestrial Laser Scanning for Heliostat Surface Shape Determination and Canting Errors Correction." *SolarPACES 2023 Conference Proceedings*（TIB Open Publishing）, 2023. (标题/出处 verified；作者列表与 DOI 待核；正文论断需按选定文献核对)
22. [Karniadakis-2021] G. E. Karniadakis, I. G. Kevrekidis, L. Lu, P. Perdikaris, S. Wang, L. Yang. "Physics-Informed Machine Learning." *Nature Reviews Physics*, 2021, 3(6): 422–440. (verified)
23. [diff-struct-opt-2024] C. Zhang, M.-X. Tao, C. Wang, C. Yang, J.-S. Fan. "Differentiable Automatic Structural Optimization Using Graph Deep Learning." *Advanced Engineering Informatics*, 2024, 60: 102363. (verified)
24. [AEI-crane-2025] Zhuomin Zhou, Brandon Johns, Yihai Fang, Yu Bai, Elahe Abdi. "Physics-Informed Neural Network for Load Sway Prediction in Travelling Autonomous Mobile Cranes." *Advanced Engineering Informatics*, 2025, 65: 103269. (verified)
25. [ECM-wind-2023] Jincheng Zhang, Xiaowei Zhao. "Digital Twin of Wind Farms via Physics-Informed Deep Learning." *Energy Conversion and Management*, 2023, 293: 117507. (verified)
26. [DiffTaichi-2020] Y. Hu, L. Anderson, T.-M. Li, Q. Sun, N. Carr, J. Ragan-Kelley, F. Durand. "DiffTaichi: Differentiable Programming for Physical Simulation." *ICLR*, 2020. arXiv:1910.00935.
27. [PhiFlow-2020] P. Holl, V. Koltun, N. Thuerey. "Learning to Control PDEs with Differentiable Physics." *ICLR*, 2020.
28. [Mitsuba2-2019] Merlin Nimier-David, Delio Vicini, Tizian Zeltner, Wenzel Jakob. "Mitsuba 2: A Retargetable Forward and Inverse Renderer." *ACM Transactions on Graphics*, 2019, 38(6): 203 (Proc. SIGGRAPH Asia). (verified)
29. [ZeroGrads-2024] Michael Fischer, Tobias Ritschel. "ZeroGrads: Learning Local Surrogates for Non-Differentiable Graphics." *ACM Transactions on Graphics*, 2024, 43(4) (Proc. SIGGRAPH). (verified)
30. [glints-diff-2023] Jiahui Fan, Beibei Wang, Wenshi Wu, Miloš Hašan, Jian Yang, Ling-Qi Yan. "Efficient Specular Glints Rendering with Differentiable Regularization." *IEEE Transactions on Visualization and Computer Graphics*, 2023, 29(6): 2940–2949. (verified)
31. [Ju:2005:MVC] T. Ju, S. Schaefer, J. Warren. "Mean Value Coordinates for Closed Triangular Meshes." *ACM SIGGRAPH*, 2005.
32. [Lewis:2000:PSD] J. P. Lewis, M. Cordner, N. Fong. "Pose Space Deformation: A Unified Approach to Shape Interpolation and Skeleton-Driven Deformation." *ACM SIGGRAPH*, 2000.
33. [Buie-2003] D. Buie, A. G. Monger, C. J. Dey. "Sunshape Distributions for Terrestrial Solar Simulations." *Solar Energy*, 2003, 74(2): 113–122. (verified)
34. [Bookstein-1989] F. L. Bookstein. "Principal Warps: Thin-Plate Splines and the Decomposition of Deformations." *IEEE TPAMI*, 1989, 11(6): 567–585. (verified)
35. [Adam-2015] D. P. Kingma, J. Ba. "Adam: A Method for Stochastic Optimization." *ICLR*, 2015. arXiv:1412.6980. (verified)
