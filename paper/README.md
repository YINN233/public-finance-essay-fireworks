# 论文 LaTeX 源文件

**编译**（需 XeLaTeX + ctex，中文字体用 TeX Live 自带的 Fandol，不依赖系统字体）：

```bash
make            # 等价于 xelatex main.tex 跑两遍
make clean
```

产物为 `main.pdf`，约 51 页。

## 结构

| 文件 | 内容 |
|---|---|
| `main.tex` | 主文件，只负责组装 |
| `preamble.tex` | 版式、宏、表格与字体设置 |
| `sections/00-cover.tex` | 封面与**成员贡献**（课程要求在摘要之前） |
| `sections/01-abstract.tex` | 摘要与关键词 |
| `sections/02-intro.tex` … `10-conclusion.tex` | 正文第一至九节 |
| `appendix/a-identification.tex` | 附录 A　第一层完整诊断 |
| `appendix/b-documents.tex` | 附录 B　34 城取证表 |
| `appendix/c-calibration.tex` | 附录 C　参数表与敏感性 |
| `sections/99-references.tex` | 参考文献（作者—年份制） |

分节存放是为了五人并行修改时减少冲突：**每人只改自己那一节的文件**。

## 与课程要求的对应

| 要求 | 落实 |
|---|---|
| 摘要 < 300 词 | `01-abstract.tex`，中文约 430 字（约 280—290 词） |
| 正文 ≤ 30 页、双倍行距、12 号字 | `preamble.tex`：`12pt` + `\doublespacing` + A4 边距 2.54 cm；正文为第 3—26 页 |
| 页边距 ≥ 1 英寸 | `geometry`：上下左右均 2.54 cm |
| 标题页写明每位成员贡献 | `00-cover.tex`，位于摘要之前 |
| 参考文献限于优质中英文期刊 | 全部为期刊或学术专著；政府文件与国家标准走正文出处，不进文献表 |
| 提交数据与代码 | 仓库根目录 `scripts/`、`policy/`、`data/` |

## 已知待办

1. `00-cover.tex` 中五处灰色“姓名（地区）”**必须替换为真实姓名**，并按实际情况调整贡献描述。
2. 三张图引用自 `../figs/`，若单独拷贝 `paper/` 目录需一并带上图片。
3. 编译无 overfull box、无未定义引用；仅有 hyperref 的书签告警（不影响版面）。
