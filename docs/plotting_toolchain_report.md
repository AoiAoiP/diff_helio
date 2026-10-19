# 论文绘图方案调研与建议

日期：2026-10-19　｜　适用：AEI（Advanced Engineering Informatics）投稿，备选 CVM

---

## 0. 结论先行

1. **示意图（图 1–4）用 TikZ**，不要用 PPT 做主力。PPT 可以出草图，但不适合作为最终矢量稿。
2. **数据图（图 5–8、10–12）用 matplotlib 直接导 PDF**，不要导 PNG 再转换。
3. **3D 面型/光路（图 9 可选，图 12 可选）**：优先 matplotlib `pcolormesh`，需要真 3D 时用 PyVista，不必上 Blender。
4. **DSH 没有绘图类插件**。它的插件机制是客户端 UI 扩展，不解决"画一张可投稿的图"这件事；本仓库已装的 7 个 skill 里也没有绘图 skill。
5. **AI 生图不能用于数据图**；示意图若用了生成式 AI，Elsevier 要求在投稿时披露。

---

## 1. 投稿硬约束（先看这个，再选工具）

以下摘自本仓库 `docs/作者指南 - 高级工程信息学 - ISSN 1474-0346 _爱思唯尔 ScienceDirect.com.html`（AEI 官方作者指南的中文版）：

| 图类型 | 可接受格式 | 要求 |
|---|---|---|
| 矢量图 | EPS、PDF | 嵌入字体，或把文字保存为图形 |
| 照片（彩色/灰度） | TIFF、JPG、PNG | ≥300 dpi；单栏最小宽度 1063 px，整页 2244 px |
| 位图线图 | TIFF、JPG、PNG | **≥1000 dpi**；单栏最小宽度 3543 px，整页 7480 px |
| 带注释的图像 | PPT、PPTX | 注释与文字必须清晰可读；嵌入图像 ≥300 dpi |

另外四条禁令/要求：

- 不要把多张图合成一个文件（相互比较的前中后对比图例外）。
- 文字相对图幅不能过小；缩放后字号要可读。
- 彩色图必须对色觉障碍者可读（Okabe-Ito 配色正好满足）。
- 生成式 AI 参与制图需按期刊政策披露。

**这条规则直接决定策略**：位图线图要 1000 dpi，等于逼你用矢量。matplotlib 的 PDF 后端与 TikZ 都是矢量，天然合规；PPT 导出 PNG 必然落在"位图线图"一栏，要 1000 dpi 才合规。

---

## 2. 本机工具链盘点（2026-10-19 实测）

| 工具 | 状态 | 用途 |
|---|---|---|
| TeXLive 2025（`latexmk`、`pdflatex`，`D:\texlive\2025`） | 已装 | TikZ / PGFPlots，示意图首选 |
| Python 3.12 + matplotlib 3.10.9 | 已装 | 全部数据图 |
| numpy 2.4.6、Pillow 12.2.0 | 已装 | 数据处理、拼版预处理 |
| ImageMagick 7.1.1 | 已装 | 分辨率/格式转换、拼版、PDF→PNG 预览 |
| Vulkan + 本项目渲染器 | 已装 | 光斑图（能流场） |
| Inkscape | **未装** | 矢量手绘（可选安装） |
| Adobe Illustrator / Affinity | 未装 | 商业矢量（不必需） |
| PyVista / ParaView | 未装 | 真 3D（`pip install pyvista` 即可） |
| SciencePlots | 未装 | matplotlib 期刊风格（`pip install SciencePlots`） |

结论：**现有链路已经够用**，不需要为绘图再买软件。缺的只是"脚本 + 样式 + 规范"，不是工具。

---

## 3. 候选方案对比

| 方案 | 最适合 | 输出 | 学习成本 | 本机 | 许可 | 对本文的适配 |
|---|---|---|---|---|---|---|
| **TikZ / PGFPlots** | 管线图、坐标示意、框图 | PDF/EPS 矢量，与正文同字体 | 中高 | ✅ | 免费 | **图 2/3/4 最优**；图 1 可做但工作量大 |
| **matplotlib** | 折线、柱状、散点、场图、光斑 | PDF/SVG/PNG | 低 | ✅ | BSD | **图 5–12 主力**；已有 7 个脚本可改造 |
| PowerPoint / Keynote | 快速草图、照片拼贴、给合作者标注 | PPTX；可导 PDF | 极低 | ✅ | 商业 | 只做草图；Elsevier 接受 pptx 但仅限"带注释图像" |
| draw.io（diagrams.net） | 流程图、系统框图 | SVG/PDF/PNG | 低 | ✅（网页/桌面） | 免费 | 图 2 的备选；导出 SVG 后字体易丢 |
| Inkscape | 手绘矢量、改 PDF 细节 | SVG/PDF/EPS | 中 | ❌ 需装 | 免费 | 可选：给 TikZ 图做后期微调 |
| Illustrator / Affinity Designer | 出版级矢量手绘 | AI/PDF/EPS | 中高 | ❌ | 商业 | 不必需；团队没有就别引入 |
| Figma | 协作排版、示意图 | PDF/PNG | 低 | 网页 | 免费/商业 | 协作画草图可以，正式稿不推荐（字体与矢量导出不稳） |
| Blender（+ Freestyle） | 3D 场景、光路动画、写实渲染 | PNG/EXR（位图） | 高 | ❌ | 免费 | 只在要做"光路 3D 示意"时考虑，成本高 |
| PyVista / ParaView | 3D 面型、点云、流场 | PNG/SVG（部分矢量） | 中 | ❌ 需装 | 免费 | 图 9 若要 3D 形变场可用；否则 matplotlib 够 |
| manim | 动画/动态示意 | MP4/GIF | 中高 | ❌ 需装 | 免费 | 静态论文不需要 |
| R ggplot2 | 统计图 | PDF/PNG | 中 | ❌ | 免费 | 无必要（团队用 Python） |
| Origin / Prism / MATLAB | 实验数据图 | 矢量/位图 | 中 | ❌ | 商业 | 无必要，matplotlib 等价 |
| Excel | 快速看数 | 位图 | 极低 | ✅ | 商业 | 不作为投稿图 |
| AI 生图（Midjourney/SD 等） | 概念插画 | 位图 | 低 | 网页 | 商业 | **不用于数据图**；示意图用了要披露，且风格不可控 |

---

## 4. 为什么 PPT 不适合做主力（以及什么时候可以用）

**不适合**：

1. 导出是位图（或半矢量），线条与文字在缩放/印刷时容易糊，落在"位图线图 1000 dpi"的严格要求下。
2. 字号、线宽、配色靠手调，12 张图很难保持一致；改一次全局样式要重画。
3. 无法用 git diff 审阅；也没有"脚本→图"的可追溯性，违背本仓库的图映射规则。
4. 与正文 LaTeX 字体不一致（TikZ 天然同字体）。
5. 组合图对齐靠肉眼，误差累积。

**可以用**：

- 图 1 的"照片/渲染拼贴"面板（Elsevier 明确接受带注释的 pptx）。
- 与导师/合作者讨论时的草图，定稿再用 TikZ 重画。
- 紧急情况下把 matplotlib 输出的 PDF 贴进 PPT 加箭头标注，再整体导出 PDF（标注层仍是位图，需接受）。

---

## 5. 本文 12 张图的推荐分工

| 图 | 类型 | 推荐工具 | 输出 | 备注 |
|---|---|---|---|---|
| 1 | 系统 + 单镜剖面示意 | TikZ 主体 + matplotlib 光斑插图 | PDF | 工作量大，可拆成 (a)(b)(c) 三个 standalone 再拼 |
| 2 | 管线图（teaser） | **TikZ** | PDF | 最高优先；力学域/光学域/反向链三栏 |
| 3 | 坐标与螺栓布局 | TikZ | PDF | 标注用符号不写数值 |
| 4 | 跨域梯度链 | TikZ | PDF | 可并入图 2 面板 |
| 5 | Proxy vs FEA 三面板 | matplotlib | PDF | 改造 `run_fea_validation.py` 的出图段 |
| 6 | 光斑对比 + 剖面 | matplotlib | PDF | 改造 `run_flux_validation.py` |
| 7 | 梯度散点 + 步长扫描 | matplotlib | PDF | 新脚本 |
| 8 | 性能堆叠条 + 扩展曲线 | matplotlib | PDF | 需先补计时点 |
| 9 | 多倾角形变场 + PV 曲线 | matplotlib `pcolormesh` | PDF | 素材齐备；3D 版可选 PyVista |
| 10 | 三档 S95 + 可达/不可达场 | matplotlib（柱状 + 场图） | PDF | 贡献 2 的核心证据 |
| 11 | margin/密度/材料三面板 | matplotlib | PDF | 素材齐备 |
| 12 | 20 镜位空间着色 | matplotlib（散点/极坐标 + 色标） | PDF | 素材齐备；若要 3D 镜场用 PyVista |

经验比例：**TikZ 4 张（示意图），matplotlib 8 张（数据图）**。这与 draft.md 里"示意图用 TikZ、数据图用 matplotlib"的既定规范一致。

---

## 6. 推荐工作流（与 AGENTS.md 的图规则对齐）

```
figures/
├── scripts/
│   ├── _style.mplstyle          # 统一字号/线宽/配色/字体
│   ├── fig5_proxy_vs_fea.py
│   ├── ...
│   └── tikz/
│       ├── _preamble.tex        # 共用宏包与颜色定义
│       ├── fig2_pipeline.tex
│       └── ...
├── generated/                   # 脚本原始输出（PDF + PNG 预览）
└── paper/
    ├── fig2_pipeline.pdf
    └── fig2_pipeline.md         # 映射：脚本 / 数据 / 时间
```

**matplotlib 侧**

- 统一 rcParams：`pdf.fonttype=42`（文字可编辑）、`svg.fonttype=none`、字号 8 pt、线宽 1.0、Okabe-Ito 配色。
- 图幅按期刊：单栏 90 mm、1.5 栏 140 mm、双栏 190 mm，用 `figsize=(mm/25.4, ...)` 直接算。
- 只导 PDF 进 `paper/`；PNG（600 dpi）只作审阅预览，不进投稿包。
- 每张图一个脚本，数据路径参数化，禁止把数字写死在脚本里。

**TikZ 侧**

- 每个图一个 `standalone` 文档，`latexmk -pdf` 单独编译，主稿 `\includegraphics` 引入 PDF。
- 共用 `_preamble.tex` 定义颜色（与 matplotlib 的 Okabe-Ito 完全一致）与节点样式。
- 节点文字用 `\small` 起步，缩放后不小于 7 pt。

**交付前检查**

| 检查 | 方法 |
|---|---|
| 字体是否嵌入 | `pdffonts fig.pdf`（TeXLive 自带 poppler 时可查）；或 Adobe Acrobat 属性 |
| 尺寸与字号 | 按 90/140/190 mm 打印预览，缩到 100% 看最小字号 |
| 色盲可读 | 灰度打印一次；或用 Coblis 模拟 |
| 分辨率 | 位图 ≥300 dpi（照片）/≥1000 dpi（线图） |
| 可追溯 | `figures/paper/figN_*.md` 三行齐全（脚本/数据/时间） |

---

## 7. 关于 DSH 插件

- DSH 有客户端插件机制（前端扩展 + HMR），但**没有面向"论文绘图"的插件**；`~/.dsh` 下只有 `data/profiles/sessions/storages`，没有插件目录。
- 本仓库已装的 7 个 skill（academic-paper、academic-paper-reviewer、academic-pipeline、deep-research、autoresearch、research-paper-writing、papercraft）都是写作/调研/实验类，不含绘图能力。
- 可行且轻量的做法：把"图 2 的 TikZ 模板 + matplotlib 样式 + 检查清单"固化成一个**自己的 skill**（`skills/figure-studio/SKILL.md`），由 agent 按模板出图。这比等第三方插件现实。

---

## 8. 建议的最小行动（约半天）

1. 建 `figures/scripts/`、`figures/scripts/tikz/`、`figures/generated/`，写 `_style.mplstyle` 与 `_preamble.tex`（配色统一 Okabe-Ito）。
2. 先做**图 2**（TikZ，零数据依赖，决定第一印象）。
3. 再做**图 10**（matplotlib，贡献 2 的唯一证据，素材齐备）。
4. 用 `pdffonts` + 90 mm 打印预览过一遍检查清单。
5. 其余图按 §5 的表逐个补，每张补完写 `figures/paper/figN_*.md`。

---

## 9. 参考

- AEI 作者指南（本地）：`docs/作者指南 - 高级工程信息学 - ISSN 1474-0346 _爱思唯尔 ScienceDirect.com.html`（图幅、dpi、格式、AI 披露条款）
- [Elsevier artwork FAQ](https://https-www-elsevier-com-443.webvpn1.xju.edu.cn/es-es/about/policies-and-standards/author/artwork-and-media-instructions/artwork-faq)
- [TikZ・PGFPlots・matplotlib の使い分け（zenn）](https://zenn.dev/tex64/articles/fa2b5464d6a641)
- [科研人常用的 10 款画图工具（AJE）](https://www.aje.cn/arc/figtools-20251120)
- [2025–2026 AI 科研绘图工具三大场景选型](https://software.it168.com/a2026/0915/6950/000006950014.shtml)
