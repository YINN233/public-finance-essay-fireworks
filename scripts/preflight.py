#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交前自检：页数、编译告警、占位符、文档口径。

用法
----
    cd paper && python3 -I ../scripts/preflight.py
    # 或：make -C paper check
"""
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
PAPER = os.path.join(ROOT, "paper")
FAIL = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (("： " + detail) if detail else ""))
    if not ok:
        FAIL.append(name)


def warn(name, detail=""):
    """已知的人工待办：不阻断自检，但必须显眼。"""
    print("  WARN  " + name + (("： " + detail) if detail else ""))


def main():
    log_path = os.path.join(PAPER, "main.log")
    aux_path = os.path.join(PAPER, "main.aux")
    pdf_path = os.path.join(PAPER, "main.pdf")

    print("== 编译产物 ==")
    check("main.pdf 存在", os.path.exists(pdf_path))
    log = open(log_path, encoding="utf-8", errors="replace").read() if os.path.exists(log_path) else ""
    m = re.search(r"Output written on main\.pdf \((\d+) pages", log)
    check("能读到总页数", bool(m), m.group(1) + " 页" if m else "缺 main.log")

    aux = open(aux_path, encoding="utf-8", errors="replace").read() if os.path.exists(aux_path) else ""
    m2 = re.search(r"newlabel\{app:identification\}\{\{[^}]*\}\{(\d+)\}", aux)
    if m2:
        main_pages = int(m2.group(1)) - 2
        check("正文不超过 30 页", main_pages <= 30, "%d 页（页脚 2—%d）" % (main_pages, main_pages + 1))
    else:
        check("能定位附录起始页", False, "main.aux 缺 app:identification")

    print("== 编译告警 ==")
    check("无 Overfull", "Overfull" not in log, str(log.count("Overfull")) + " 处")
    check("无未定义引用", "undefined" not in log.lower(), str(log.lower().count("undefined")) + " 处")
    check("无缺字", "Missing character" not in log, str(log.count("Missing character")) + " 处")

    print("== 占位符 ==")
    tex = ""
    for base, _, files in os.walk(PAPER):
        for f in files:
            if f.endswith(".tex"):
                tex += open(os.path.join(base, f), encoding="utf-8", errors="replace").read()
    check("无【待核】", "待核" not in tex)
    if "姓名待填" in tex:
        warn("封面姓名未填", "这是唯一的人工待办；填完即通过")
    else:
        print("  PASS  封面姓名已填")
    check("无裸 XXX", "XXX" not in tex)

    print("== 文档口径 ==")
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    agents = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
    paper_readme = open(os.path.join(PAPER, "README.md"), encoding="utf-8").read()
    total = m.group(1) if m else "?"
    check("README 写 %s 页" % total, "%s 页" % total in readme)
    check("README 写正文 %d 页" % main_pages, "正文 %d 页" % main_pages in readme)
    check("README 不再写 53 页", "53 页" not in readme)
    check("AGENTS 写 %s 页" % total, "%s 页" % total in agents)
    check("paper/README 写 %s 页" % total, "%s 页" % total in paper_readme)
    check("数字台账存在", os.path.exists(os.path.join(ROOT, "docs", "数字台账.md")))
    check("气象清单存在", os.path.exists(os.path.join(ROOT, "docs", "气象数据清单.md")))

    print()
    if FAIL:
        print("未通过 %d 项：%s" % (len(FAIL), "；".join(FAIL)))
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
