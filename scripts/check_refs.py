#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参考文献 DOI 批量核验

为什么需要它
------------
本项目的参考文献表是分批检索来的，**检索最大的失效模式是编造或记错卷期页**。抽样复核
只能发现一部分；**逐个 DOI 到 Crossref 取权威元数据**可以整批筛掉点不存在的条目。

用法
----
  python3 -I check_refs.py                       # 扫 docs/参考文献.md（默认）
  python3 -I check_refs.py --file docs/参考文献.md --csv refs_authoritative.csv
  python3 -I check_refs.py --doi 10.1257/aer.20181169

输出
----
  stdout                    每个 DOI 的权威元数据（作者/题名/刊名/卷期页/年）
  --csv PATH                同上，写成 CSV 供逐条比对
  退出码                    有任一 DOI 解析失败则为 1

⚠️ 本脚本只核"DOI 是否成立、元数据是什么"，**不比对它与正文引文是否一致**——
   那一步得人看。脚本的价值是把"这条到底存不存在"这件事一次性做完。

来源：Crossref REST API，无需密钥。带 mailto 的 User-Agent 是 Crossref 的礼貌要求。
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "public-finance-essay/1.0 (mailto:chenyq24@mails.tsinghua.edu.cn)"

# 中文期刊常见 DOI 前缀（10.xxxxx）；这里只做通用提取，不限定前缀
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")


def extract_dois(path):
    """从任意文本里抽 DOI，去重保序，去掉句末标点。"""
    seen, out = set(), []
    for m in DOI_RE.finditer(open(path, encoding="utf-8", errors="replace").read()):
        d = m.group(0).rstrip(".,;)、。；）")
        if d.lower() not in seen:
            seen.add(d.lower())
            out.append(d)
    return out


def fetch(doi):
    """返回 (ok, dict|str)。dict 为 Crossref message。"""
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    r = subprocess.run(["curl", "-sk", "-m", "30", "-A", UA, url],
                       capture_output=True, text=True)
    if not r.stdout.strip():
        return False, "无响应"
    try:
        return True, json.loads(r.stdout)["message"]
    except Exception as e:
        return False, "解析失败: %s" % e


def doi_resolves(doi):
    """DOI 是否已注册。

    ⚠️ **不要跟随重定向**：doi.org 对已注册的 DOI 返回 301/302，指向出版社。
    跟到出版社后拿到的状态是**出版社站点**的状态（可能是 500/403/超时），与"DOI 是否存在"
    无关。早先本脚本用了 -L，把"出版社页面挂了"误判成"DOI 不存在"——差一点把两条正确
    引文报成坏的。**判断 DOI 只看 doi.org 的首次响应。**

    返回 (已注册?, doi.org 状态码, 出版社目标状态码或 None)。
    """
    r = subprocess.run(
        ["curl", "-sk", "-o", "/dev/null", "-w", "%{http_code}", "-m", "25",
         "-A", UA, "https://doi.org/" + urllib.parse.quote(doi, safe="")],
        capture_output=True, text=True)
    code = (r.stdout or "").strip()
    registered = code.isdigit() and 300 <= int(code) < 400
    target = None
    if registered:   # 仅作参考信息：出版社站点是否可达，与 DOI 有效性无关
        t = subprocess.run(
            ["curl", "-sk", "-o", "/dev/null", "-w", "%{http_code}", "-m", "25",
             "-A", UA, "-L", "https://doi.org/" + urllib.parse.quote(doi, safe="")],
            capture_output=True, text=True)
        target = (t.stdout or "").strip() or None
    return registered, code, target


def summarize(m):
    au = m.get("author") or []
    names = "; ".join((a.get("family", "") + " " + a.get("given", "")).strip() for a in au[:4])
    if len(au) > 4:
        names += " 等(%d 人)" % len(au)
    dp = m.get("issued", {}).get("date-parts", [[None]])[0]
    return {
        "doi": m.get("DOI", ""),
        "title": (m.get("title") or [""])[0],
        "journal": (m.get("container-title") or [""])[0],
        "volume": m.get("volume", ""),
        "issue": m.get("issue", ""),
        "page": m.get("page", ""),
        "year": dp[0] if dp else "",
        "authors": names,
        "type": m.get("type", ""),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=os.path.join(ROOT, "docs", "参考文献.md"))
    ap.add_argument("--doi", action="append", default=[],
                    help="直接指定 DOI（可重复）；给了就不扫文件")
    ap.add_argument("--csv", default="",
                    help="把权威元数据写成 CSV")
    args = ap.parse_args()

    dois = args.doi or (extract_dois(args.file) if os.path.exists(args.file) else [])
    if not dois:
        print("!! 没有找到任何 DOI（检查 --file 或 --doi）", file=sys.stderr)
        return 1
    print("待核 DOI：%d 条\n" % len(dois))

    rows, failed, alive_rows = [], [], []
    for i, doi in enumerate(dois, 1):
        ok, m = fetch(doi)
        if not ok:
            # Crossref 查不到 ≠ DOI 不存在：中文期刊的 DOI 常由万方/CNKI 另行注册。
            alive, code, target = doi_resolves(doi)
            if alive:
                alive_rows.append(doi)
                extra = ("；出版社站点返回 %s（**与 DOI 有效性无关**）" % target) if target and target != "200" else ""
                print("  %2d. ○ %-42s  Crossref 未收录，但 doi.org 已注册（%s）%s"
                      % (i, doi, code, extra))
                print("         → DOI 有效，只是不在 Crossref；卷期页须到期刊页核对")
            else:
                failed.append((doi, "Crossref 未收录，且 doi.org 返回 %s（非 3xx 重定向）" % code))
                print("  %2d. ✗ %-42s  doi.org 返回 %s，未注册" % (i, doi, code))
            continue
        s = summarize(m)
        rows.append(s)
        cite = "%s. %s. %s, %s, %s(%s): %s." % (
            s["authors"], s["title"], s["journal"], s["year"],
            s["volume"], s["issue"] or "–", s["page"] or "–")
        print("  %2d. ✓ %s" % (i, s["doi"]))
        print("        %s" % cite)

    print("\n" + "=" * 74)
    print("  Crossref 逐条核实 %d / %d" % (len(rows), len(dois)))
    if alive_rows:
        print("  ○ DOI 有效但不在 Crossref %d 条（卷期页须另核）：" % len(alive_rows))
        for d in alive_rows:
            print("      %s" % d)
    if failed:
        print("  ✗ 无法解析 %d 条：" % len(failed))
        for d, why in failed:
            print("      %-44s %s" % (d, why))
        print("  ⚠️ 这一档才是真问题。**不要改数字凑一个能解析的 DOI**——")
        print("     要么找到正确 DOI，要么把该条从参考文献里删掉。")

    if args.csv and rows:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("\n写入 %s（%d 行权威元数据）" % (args.csv, len(rows)))

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
