# work_template（归档于 2026-10-19）

## 这是什么

一份 **Word 任务书（docx）的解包工作区**，与定日镜论文无关，来自 2026-10-11 的一次文档改写任务：

| 文件 | 说明 |
|---|---|
| `baseline.docx` | 原始任务书基线（15.5 KB），改写前的副本 |
| `unpacked/` | docx 解包后的 OOXML（`word/document.xml` 等在 09:59 被改写） |
| `view.txt` | 解包工具的块/样式预览（段落、字符、编号的文本化视图） |
| `state.json` | 记录源 docx 路径、各文件哈希与部件清单 |

任务书主题是「基于计算几何排样与 GPU 光线追踪的多边形定日镜效能评估系统设计与实现」，
属于另一条学生课题线，不是当前论文。

## 为什么归档而不是删

- 仓库里**没有**源 docx，也没有最终导出的成品 docx；`unpacked/word/document.xml` 是改写后内容的唯一副本。
- 一旦确认最终的 `.docx` 已导出到别处（或任务书不再需要），本目录可以整个删掉。

## 它原来配的脚本

改写脚本 `build_renwushu.py` 曾放在仓库根目录，通过字符串替换把新文本写进
`unpacked/word/document.xml`；该脚本已于 2026-10 被手动删除，仓库里不再有对应工具。
`state.json` 里的 `src` 路径（一个根目录下的 `.docx`）也已不存在。

## 恢复方式

```powershell
# 整个目录挪回仓库根
Move-Item archive\work_template_2026-10-11 work_template
```

需要重新生成 docx 时，用 Word 打开 `unpacked` 对应的包或重新解包 `baseline.docx` 即可。
