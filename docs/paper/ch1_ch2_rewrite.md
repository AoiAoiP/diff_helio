# 第一章 & 第二章 重写参考稿（v9，第二章按审阅意见重构，供审阅）

> 本稿在 v8 基础上重构第二章（§2）；第一章（§1）仅一处术语替换（canting → 子镜倾角）：
> 1. **两条路线归入 §2.1**（按框架括注）：§2.1 改写为两段，先前向工具线与标量化局限，再"可微光追系 vs 离线结构-光学耦合系"；
> 2. **§2.2 改写为"设计变量与优化边界"**：第一段给出必要性、变量层级，第二段给出优化粒度、评估指标、分析深度三处边界；
> 3. **删除 §2.5 小结**，"四个断点"的定位折入 §2 章首段；
> 4. **消除与 §1 的重复**：§2 不再复述 §1 的工作枚举，改为按机制分组引用（脚本检测的 9 处长句重复全部清除）；
> 5. **§2.1 无支撑断言修复**：改为引用 [9]（服役载荷形变的确定性结构），与第一章处理方式一致；
> 6. **§2.2 指标边界断言改为可核查表述**并交叉引用 §5.2；
> 7. **新增子镜倾角调试实践文献 [21]**（占位，书目待核）；正文 "canting" 统一改为中文"子镜倾角"（参考文献条目标签保留英文键名以便对应 ref/ 目录）。
> 引用编号重排为 [1]–[32]（新增 [21]，原 [21]–[31] → [22]–[32]，仍严格按首现顺序）；旧编号对照见附录 F。
> 语言规范：段首句直接承载内容，无元话语，无段尾模板式收束；无破折号；无"不是…而是…/而非"结构；无"正是/恰"；不设工作对比类表格。
> 定位：AEI（Advanced Engineering Informatics）。[4]、[21] 为待补占位引用，[9] 作者字段待核（见附录 D）。

---

## 1　引言

塔式太阳能聚光（CSP）电站以数千面定日镜将太阳直射光反射至塔顶接收器，镜场投资与光学精度是电站成本与效率的关键瓶颈 [1]。单镜面型决定其反射光斑的形状与尺寸：光斑越大，溢出接收器的能量越多，聚光效率越低。面型质量因此贯穿镜面制造、安装与服役的全生命周期，是塔式电站光学设计的核心关切。

工程中镜面由螺栓排布支撑，出厂面型是各螺栓行程在薄板上的力学平衡结果，螺栓顶升成型的光-机集成分析已建立支撑参数与光学精度之间的定量关系 [2, 3]。镜面投入运行后，重力、风载与热膨胀持续作用于板面，使其偏离出厂设计形状，产生连续形变，反射光斑随之退化（图 1），结构有限元分析是评估这类载荷形变的常规手段 [4]。面型设计因而不能停留在理想几何曲面，物理载荷作用下的服役面型才是优化应当面对的对象。

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

## 2　相关工作

定日镜工程一侧，能流仿真（§2.1）给出光斑计算工具与两条面向真实形变的路线，面型与结构优化（§2.2）给出设计变量的层级与优化边界；方法基础一侧，物理信息仿真（§2.3）与可微渲染（§2.4）分别从科学计算与图形学逼近"梯度穿越物理域边界"的问题。本章按从应用场景到方法根源的顺序回顾，四条脉络止步之处构成本文要接通的四个断点。

### 2.1　定日镜能流仿真：可微光追系与离线结构-光学耦合系

吸热器能流密度预测是定日镜光学设计的计算基石，直接服务于接收器设计与镜场布局评估。成熟工具构成一条前向管线：蒙特卡洛光线追踪（MCRT）是公认的精度基准，代表为 SolTrace [5] 与 Tonatiuh [6]；解析卷积模型以误差统计均匀假设换取解析速度，代表为 HFLCAL [7] 与 UNIZAR [8]；学习器路线以紧凑网络回归光斑参数，如 Fast-NCM [19] 在 16 ms 内完成全场能流仿真；采样方案的精度与成本权衡也有专门研究 [20]。这些工具把镜面质量压缩为单一标量斜率误差 $\sigma_S$，再与太阳日轮做统计卷积。服役载荷下的形变具有确定性的空间结构 [9]，标量统计难以完整承担其光学后果（定量论证见 §5.2）。

面向真实形变的能流计算沿两条路线展开。可微光追系以可微蒙特卡洛光线追踪从表面法向场直接生成能流并回传梯度，覆盖瞄准策略、子镜倾角、原位计量与面型反演四类任务 [10, 11, 12, 13, 14]；其表面仍是理想参数曲面，梯度止于瞄准点、倾角等面板级自由度，形变过程不进入计算图。离线结构-光学耦合系以有限元或计算流体动力学求解载荷形变，再串行接入光线追踪评估，代表工作包括螺栓顶升成型 [2, 3]、伞形与三脚架定日镜 [15, 16]、风致形变多物理场 [17]、重力与风载形变编码 [9] 与面型调节机构 [18]；其形变场显式进入光路，代价是每次评估需一次结构求解加一次全场光追。两条路线的分工清晰：一条提供梯度但表面理想化，一条提供真实形变但没有梯度。

### 2.2　定日镜面型优化：设计变量与优化边界

面型优化的必要性来自服役形变：出厂面型由支撑结构决定，载荷作用下的形变直接改变光斑 [2, 3, 9]。既有工作的设计变量沿层级上行：几何配置层的瞄准策略与子镜倾角 [10, 11]，结构参数层的螺栓间距、数量与顶升行程 [2, 3]，把结构尺寸与光学误差联合权衡的伞形与三脚架定日镜 [15, 16]，纳入风致载荷的多物理场评估 [17]；面型本身作为可调对象出现在面型调节机构 [18] 与子镜倾角调试实践 [21] 中。变量层级越高，可补偿的光学误差越丰富，对评估方式的要求也越高。

现有优化方式在该层级上留下三处边界。第一是优化粒度：离线路线的每次评估都要完整求解两个物理域，参数空间只能按枚举步长探索，梯度无法引导搜索方向。第二是评估指标：离线路线的光学指标是变形网格导出的斜率误差，并未直接以光斑面积 S95 为目标（两者的定量差距见 §5.2），而可微路线的目标虽为光斑，其表面却停留在理想几何。第三是分析深度：参数扫描回答"哪组参数更好"，无法回答"给定支撑布局下，任何调节策略的物理上限在哪里"；后者要求把优化差距按梯度可达性分解，只有端到端可微的管线才提供这种分解能力（§5.3）。

### 2.3　物理信息仿真：梯度终止于物理量

科学计算一侧，物理信息机器学习 [22] 把物理约束嵌入学习系统；可微结构优化 [23] 与物理信息数字孪生 [24, 25] 使设计变量经由物理模型获得梯度；图形学内部的可微物理模拟同样实现了物理状态对仿真参数的微分，代表为可微弹性体 [26] 与可微流体 [27]。这一脉络证明"物理状态对参数可微"在工程与图形学中均已可行，与本文的目标方向一致。

本文与上述工作存在两点系统性差异。第一点在梯度终端：这些工作的梯度终点是位移、应力、流场等物理状态本身，本文的梯度继续延伸至经光学渲染后的辐射度分布，两个域的梯度在表面法线处衔接；终端位置的不同直接影响物理代理的设计，代理的精度需求取决于位移误差经光学低通滤波后产生的光斑面积误差（§4.2）。第二点在代理形态：主流范式训练神经代理逼近物理求解器，误差随训练分布漂移，难以审计；本文采用解析推导的 TPS 几何代理，梯度精确，误差预算可与有限元解直接对比，这一可审计性是 §5.3 界限分析成立的前提。

### 2.4　可微渲染：固定表面的隐含前提

图形学可微渲染把逆图形学问题转化为梯度驱动优化，Mitsuba 2 [28] 建立了可重定向的可微前向与逆向渲染基础设施，ZeroGrads [29] 把梯度估计扩展到含可见性不连续性的复杂光路，镜面高光等病态逆渲染问题也因可微正则化而可解 [30]。这些框架共享一个隐含前提：表面几何是渲染的固定输入，物理载荷不参与表面的形成，梯度反传止于位置、法向、材质系数等表面交点参数。本文将连续表面场（高度场与法向场）提升为渲染管线的一等输入，使梯度经表面场继续反传至机械设计变量；这一"稀疏控制点驱动连续曲面"的表示与几何处理中的形变控制结构同源，如 cage 形变 [31] 与 blendshape 形变 [32]，其方法论联系在 §6 讨论。

---

## 参考文献

> 编号按正文首次引用顺序排列；旧编号对照见附录 F。标注 (TBC)/待核 的条目已在 2026.9.3 核对一轮：已补齐卷期页码与 DOI，[4]、[9]、[18]、[19]、[21] 的作者或卷期字段仍待核。

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

**未编号保留**（第 3 章起引用时按出现顺序接续编号）：
- [Buie-2003] D. Buie, A. G. Monger, C. J. Dey. "Sunshape Distributions for Terrestrial Solar Simulations." *Solar Energy*, 2003, 74(2): 113–122.（§3.2 光学模型将引用）
- [Bookstein-1989] F. L. Bookstein. "Principal Warps: Thin-Plate Splines and the Decomposition of Deformations." *IEEE TPAMI*, 1989, 11(6): 567–585.（§3.3 TPS 将引用）

---

## 附：参考说明（非正文）

### A. 与 v6 的主要差异

1. **引言第三、四段对调并重写**：标量化刻画（历史更久）置于可微光追（近年落地）之前；第五段改写为"结构工程一侧沿离线串行路线…"，删除与第四段重复的"可微路线以理想几何曲面为优化对象…"表述。
2. **原标量化段的研究结果填充句已删除**："高度结构化、连续、非高斯分布、单个标量无从刻画其空间模式"等表述改为由外部文献支撑的版本：载荷形变的确定性空间结构引新文献 [9]（重力/风载形变显式编码用于光学性能分析）与 [2, 3]（螺栓顶升成型面型随支撑参数确定性变化）；"非高斯"表述删除。
3. **新增文献 [9]**：Renewable Energy 2025 的重力/风载形变编码论文（浙江大学 CAD&CG，ScienceDirect PII S0960148125008419），同时引入 §2.2 离线结构-光学耦合一族。
4. 引用编号按新段序重排为 [1]–[31]（较 v6 增加 [9] 并整体后移）。
5. **（v8）第一章按审阅意见修订**：修复 P6 末句残句；贡献段改为编号列表并补回章节引用（§3／§4，§5.3／§5.4–5.5）；P2 的"空间结构化"断言降调为"连续形变"（确定性结构的证据统一由 P3 的 [9]、[2, 3] 承担），"服役形状"改为"服役面型"；组织段压缩为一句（124 → 60 字）。
6. **（v9）第二章按审阅意见重构**：① 按框架把"可微光追系 vs 离线结构-光学耦合系"归入 §2.1（§2.1 改为两段：前向工具线与标量化局限、两条路线与各自边界）；② §2.2 改为"设计变量与优化边界"（必要性 + 变量层级 + 三重边界）；③ 删除 §2.5 小结，其"四个断点"定位折入 §2 章首段；④ 消除 §2 与 §1 的长句重复，工作枚举改为按机制分组引用；⑤ §2.1 无支撑断言改为引用 [9]（即 v8 待办项，已完成）；⑥ §2.2 指标边界断言改为可核查表述并交叉引用 §5.2；⑦ 新增 [21] 子镜倾角调试实践（占位）；正文 "canting" 统一改为中文"子镜倾角"。引用编号重排为 [1]–[32]。

### B. 框架解读与取舍（请审阅确认）

1. **2.1 的括号内容**：最终框架在 2.1 下写了"（可微光追系 vs 离线结构-光学耦合系）"。本稿把这两族完整放在 §2.2 面型优化（与引言问题 2 的"两条路线"一一对应），§2.1 只评述前向仿真工具并以一句桥接到 §2.2。若你希望按字面把两族归入 2.1，§2.2 将与 2.1 大量重复引文，建议维持本稿安排。
2. **2.5 小结**：最终框架未列 2.5。本稿保留它，因为"四个断点 → 本文逐个接通"是全章定位的收束句，也承接引言问题 2。若不想保留，删去即可，但建议把最后一句并入 §2 章首段。
3. **贡献段位置**：最终框架把三条贡献列在 §0 文章定位。本稿仍按期刊惯例在引言末段列出贡献并给出章节引用（§0 与引言末段内容一致，仅多引用编号），投稿时正文保留引言版本。
4. **数字限定**：84%–87% 按 v3 口径加了"对重力惩罚显著的镜位"限定（东/南/西三镜），North 免罚镜约 36%。摘要目前无此限定，需同步修改（见 C 节）。
5. **[9] 的引用分寸**：本稿对 [9] 的描述严格取自其标题（"surface deformation and encoding under gravity and wind loads for optical performance analysis"）。该文与本课题组同源，请在核对全文后确认其定位是否需在 §2.2 中补充细节，以及是否需要列入贡献对比讨论（若与本文离线管线高度重叠，审稿人会要求明确差异）。

### C. 数字口径说明

- "3–4 倍""80%–90%""84%–87%""4%–10%"：与最新摘要口径一致。
- **"84%–87%"的限定**：正文按"对重力惩罚显著的镜位"限定。摘要建议同步改为"对重力惩罚显著的镜位，84%–87% 的优化空间结构性不可达"，避免审稿人对照 North 镜（约 36%）发现矛盾。
- **"4%–10%"的定义**：全文目前没有给出该数字的计算定义（相对理想结构的何种指标、哪些镜位、何种工况）。§5.4/§5.5 的表格必须落实该数字出处，否则贡献 3 的收窄声明不可检查。
- 摘要其他待改点："重力经发现偏转"笔误（应为"经法向偏转"）；结尾句"适用于任何结构形变影响光路的光学系统"建议降调为正文可支撑的表述。

### D. 待补清单（TBC）

| 占位 | 位置 | 处置 |
|------|------|------|
| [4] FEA-practice（原 [20]） | §1 第二段 | 定日镜结构 FEA 分析的代表性文献，书目核对阶段选定 |
| [9] deformation-encoding 2025 | §1 第三段、§2.2 | 作者列表、卷期页码从 ScienceDirect 核对（PII S0960148125008419）；核对全文后确认 §2.2 描述与定位 |
| [5][6][7][8][22][28][29] 等 (TBC) 条目 | 参考文献 | 书目核对（作者/卷期/DOI） |
| [21] canting-practice（原占位 [19]） | §2.2 第一段 | 子镜倾角调试/装配实践的代表性文献，书目核对阶段选定；该句论断需按所选文献核对后定稿 |
| Buie（原 [15]）、Bookstein（原 [33]） | 未编号保留 | §3 重写时按出现顺序接续编号 |
| 图 1 | §1 第二段 | CSP 系统示意 + 定日镜结构（待绘） |
| 图 2 | §1 第六段 | 全管线流程图（待绘） |

### E. 自审清单（写作质量）

1. **元话语扫描**：无"本段/本章/本小节说明…"、无"在…基础上，本段…"、无"构成本文…出发点"类填充句、无段尾"总之/综上/概括而言/由此可见/简言之"模板式收束（全文逐段检查）。
2. **研究结果前置检查**：引言中不再出现本研究实验结果的断言；第三段的"确定性形变"前提全部由 [9]、[2, 3] 支撑，本研究结果（3–4 倍、80%–90%、84%–87%、4%–10%）仅出现在贡献与"框架应用"段，明确以"本文…揭示/分析/使…"句式呈现。
3. **工作对比表**：已删除，正文不设任何对比类表格。
4. 术语一致性：能流 / 光斑面积 S95 / 斜率误差 $\sigma_S$ / 螺栓行程 / 镜位 / 显式表面场，全篇统一。
5. 禁用句式扫描：无破折号、无"不是…而是…/而非"、无"正是/恰"、无"其一/其二"。
6. 引用编号一致性：正文 [1]–[32] 均按首次出现顺序递增，参考文献列表与正文一一对应（逐条核对，脚本验证）。
7. 论点-证据映射（主要声明）：

| 声明 | 证据 | 状态 |
|------|------|------|
| 镜场成本与光学精度是关键瓶颈 | [1] NREL 路线图 | 文献支持 |
| 服役载荷下的镜面形变具有确定性空间结构 | [9]（形变显式编码）、[2, 3]（面型随支撑参数确定性变化） | 文献支持（[9] 作者字段待核） |
| 主流工具把表面质量压缩为 $\sigma_S$ | [5,6,7,8,19] + §2.1 | 文献支持 |
| 可微光追已在 CSP 落地 | [10,11,12,13,14] | 文献支持 |
| 惩罚随镜位相差 3–4 倍，80%–90% 源于悬挑 | §5.2 基线对比 | 本项目结果（§5.2 需落实） |
| 84%–87% 结构性不可达（限惩罚显著镜位） | §5.3 界限分析（东/南/西 87.4/84.0/85.6） | 本项目结果（摘要需同步加限定） |
| 差距收窄至 4%–10% | §5.4 结构重设计 | 本项目结果（定义需在 §5.4/5.5 落实） |
| 20 面镜、全年 334 方向 | §5.1 实验设置 | 本项目结果 |

### F. 编号映射（新 → 旧）

| 新编号 | 旧编号 | 条目 | 新编号 | 旧编号 | 条目 |
|:---:|:---:|------|:---:|:---:|------|
| 1 | 26 | Zhu-roadmap-2022 | 17 | 25 | CFD-FEM-optical-2026 |
| 2 | 21 | Yan-bolt-2024 | 18 | 27 | Angel-autoshape-2022 |
| 3 | 22 | Yan-bolt-jacking-2025 | 19 | 6 | Fast-NCM 2026 |
| 4 | 20 | FEA-practice TBC | 20 | 28 | Ye-sampling-2026 |
| 5 | 11 | SolTrace TBC | 21 | 新增 | 子镜倾角调试实践 TBC |
| 6 | 12 | Tonatiuh TBC | 22 | 7 | Karniadakis 2021 |
| 7 | 13 | HFLCAL TBC | 23 | 8 | diff-struct-opt 2024 |
| 8 | 14 | UNIZAR TBC | 24 | 9 | AEI-crane 2025 |
| 9 | 新增 | deformation-encoding 2025 | 25 | 10 | ECM-wind 2023 |
| 10 | 1 | aiming-DMCRT 2025 | 26 | 31 | DiffTaichi 2020 |
| 11 | 2 | canting-DRT 2025（子镜倾角优化） | 27 | 32 | PhiFlow 2020 |
| 12 | 3 | Pargmann 2024 | 28 | 16 | Mitsuba2 TBC |
| 13 | 4 | inverse-DL-RT 2025 | 29 | 17 | ZeroGrads TBC |
| 14 | 5 | sim2real-DL-RT 2025 | 30 | 18 | glints-diff TBC |
| 15 | 23 | Yang-umbrella-2022 | 31 | 29 | Ju:2005:MVC |
| 16 | 24 | Thalange-tripod-2017 | 32 | 30 | Lewis:2000:PSD |

未编号保留：旧 [15] Buie、旧 [33] Bookstein（§3 重写时按出现顺序接续编号）。
