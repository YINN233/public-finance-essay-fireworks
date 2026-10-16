@AGENTS.md

# CLAUDE.md

正本规约在 **`AGENTS.md`**（上面已导入）。本文件只放 Claude Code 专属的东西。

## 表达纪律

- **给判断，不要和稀泥。** 用户明确要求过"严禁客观"——意思是该说对错就说，不要用"一方面…另一方面"把结论摊平。
- **但事实陈述必须严谨**，并标注证据档（一手 / 官方发布稿 / 仅搜索摘要）。判断可以锋利，事实不能含糊。
- **不要用"已完成"掩盖没跑过的东西。** 测试失败就说失败并附输出；跳过的步骤就说跳过。

## 工具约定

- **Python 一律 `python3 -I`**（隔离模式）。注意它不把脚本目录放进 `sys.path`，也不加载用户 site-packages。
- **出图**用 `scipilot-figure-skill`。`make_figs.py` 已内置 matplotlib 回退，未安装该技能也不会报错（可用 `SCIPILOT_SKILL` 指定路径）。
- **写论文/审稿**可用 `/ars-*` 系列：`/ars-outline`、`/ars-plan`、`/ars-reviewer`、`/ars-citation-check`、`/ars-abstract`。
- **提交信息**末尾加：`Co-Authored-By: Claude Code <noreply@anthropic.com>`
- 本仓库是**公开**的，提交前检查有没有把课程根目录的策略性/评分相关材料带进来。

## 派发 agent

额度与独立性检验的固定做法见 `AGENTS.md` §六。**小任务 ≤ 3 个，大型复杂任务 ≤ 5 个。**
派发时必须在提示里**明写隔离禁令**（不得读哪些文件），否则复核结果不构成独立性检验。
