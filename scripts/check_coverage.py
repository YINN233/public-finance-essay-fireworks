#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
面板覆盖率诊断：查清各春节年份观测数下滑的原因，并判断是否可用平衡面板

为什么需要它
------------
各年份「城-日」观测数从 2021 年的 5,529 降到 2026 年的 5,023。样本量的下滑
恰好落在 2022 年之后——正是「禁改限」政策反转的窗口。若退出的城市与其他城市
在污染水平上系统不同，"政策效应"里就混进了"样本构成变化"。

本脚本做三件事
--------------
1. 分清成因：是城市没出现在原始文件表头里（城市缺席），还是出现了但有效小时
   数不足（缺测小时）。两者的处理方式完全不同。
2. 城市 × 年份 在场矩阵 → 全程在场城市数（平衡面板候选）。
3. **构成检验**：逐年比较「全样本」与「平衡面板」的除夕 PM2.5 均值。
   若两条线贴合，说明构成变化无害；若分叉，说明构成变化在污染结果上，
   必须在回归中处理。

用法
----
  python3 -I check_coverage.py
  python3 -I check_coverage.py --present-days 13 --min-hours 18
"""

import argparse
import csv
import glob
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta

CNY_DAY1 = {
    2015: (2, 19), 2016: (2, 8),  2017: (1, 28), 2018: (2, 16),
    2019: (2, 5),  2020: (1, 25), 2021: (2, 12), 2022: (2, 1),
    2023: (1, 22), 2024: (2, 10), 2025: (1, 29), 2026: (2, 17),
}
MAX_WINDOW = 15


def cny_eve_map():
    return {y: date(y, m, d) - timedelta(days=1) for y, (m, d) in CNY_DAY1.items()}


def rel_and_cny_year(day, eves):
    best, best_abs = (None, None), None
    for y, eve in eves.items():
        delta = (day - eve).days
        if abs(delta) <= MAX_WINDOW and (best_abs is None or abs(delta) < best_abs):
            best, best_abs = (delta, y), abs(delta)
    return best


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default="data/raw")
    ap.add_argument("--min-hours", type=int, default=18,
                    help="当日视为可用所需的最少有效小时数")
    ap.add_argument("--present-days", type=int, default=13,
                    help="某年视为「在场」所需的最少可用天数（窗口共 15 天）")
    ap.add_argument("--out", default="data/coverage_city_year.csv")
    args = ap.parse_args()
    # 默认参数是相对路径；从项目目录之外运行会解析到错误位置，甚至抛 FileNotFoundError
    # 而报错信息看不出是路径问题。统一以仓库根目录为基准；绝对路径不受影响。
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    files = sorted(glob.glob(os.path.join(args.raw_dir, "*china_cities_*.csv")))
    if not files:
        print("!! %s 下没有文件" % args.raw_dir, file=sys.stderr)
        return 1
    eves = cny_eve_map()

    in_header = defaultdict(int)   # (city, y) -> 该年出现在表头的天数
    usable = defaultdict(int)      # (city, y) -> 该年可用天数（>= min_hours）
    eveval = {}                    # (city, y) -> 除夕当天 PM2.5 日均
    years = set()
    print("解析 %d 个原始文件 ..." % len(files))

    for path in files:
        m = re.search(r"(\d{8})", os.path.basename(path))
        if not m:
            continue
        s = m.group(1)
        day = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        rel, y = rel_and_cny_year(day, eves)
        if y is None:
            continue
        years.add(y)
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            rows = list(csv.reader(fh))
        if len(rows) < 2:
            continue
        header = rows[0]
        idx = {name: i for i, name in enumerate(header)}
        pm_rows = {}
        for r in rows[1:]:
            if len(r) > 2 and r[2] == "PM2.5":
                pm_rows[r[1]] = r
        for city in header[3:]:
            if not city:
                continue
            ci = idx[city]
            in_header[(city, y)] += 1
            vals = []
            for hour in range(24):
                r = pm_rows.get(str(hour))
                if r is not None and ci < len(r):
                    v = fnum(r[ci])
                    if v is not None:
                        vals.append(v)
            if len(vals) >= args.min_hours:
                usable[(city, y)] += 1
                if rel == 0:
                    eveval[(city, y)] = sum(vals) / len(vals)

    years = sorted(years)
    cities = sorted({c for c, _ in usable} | {c for c, _ in in_header})
    print("城市 %d 个，春节年份 %s\n" % (len(cities), years))

    # ---------- 1. 成因分解 ----------
    print("=" * 78)
    print("1. 逐年覆盖率：区分「城市缺席」与「缺测小时」")
    print("=" * 78)
    print("%-6s %10s %10s %10s %10s" % ("年份", "表头城市数", "可用城市数",
                                        "缺席城市数", "缺测城市数"))
    for y in years:
        hdr = [c for c in cities if in_header.get((c, y), 0) > 0]
        ok = [c for c in cities if usable.get((c, y), 0) > 0]
        absent = len(cities) - len(hdr)
        short = len(hdr) - len(ok)
        print("%-6d %10d %10d %10d %10d" % (y, len(hdr), len(ok), absent, short))

    # ---------- 2. 平衡面板候选 ----------
    print()
    print("=" * 78)
    print("2. 城市 × 年份 在场矩阵：平衡面板候选（在场 = 该年可用天数 >= %d）"
          % args.present_days)
    print("=" * 78)
    per_city_years = {c: sum(1 for y in years if usable.get((c, y), 0) >= args.present_days)
                      for c in cities}
    from collections import Counter
    dist = Counter(per_city_years.values())
    for k in sorted(dist, reverse=True):
        print("  在场 %2d/%d 年: %4d 个城市" % (k, len(years), dist[k]))
    balanced = [c for c in cities if per_city_years[c] == len(years)]
    print("\n  → 全程在场（可构造平衡面板）：%d 个城市" % len(balanced))

    # ---------- 3. 构成检验 ----------
    print()
    print("=" * 78)
    print("3. 构成检验：全样本 vs 平衡面板 的除夕 PM2.5 均值")
    print("=" * 78)
    print("%-6s %10s %10s %10s %10s %10s" % ("年份", "全样本n", "全样本均值",
                                             "平衡n", "平衡均值", "差值"))
    for y in years:
        full = [eveval[(c, y)] for c in cities if (c, y) in eveval]
        bal = [eveval[(c, y)] for c in balanced if (c, y) in eveval]
        if not full:
            continue
        f, b = mean(full), mean(bal)
        print("%-6d %10d %10.1f %10d %10.1f %+10.1f"
              % (y, len(full), f, len(bal), b, (f - b) if bal else float("nan")))

    # ---------- 4. 退出城市是否系统不同 ----------
    print()
    print("=" * 78)
    print("4. 退出构成检验：在上一年退出的城市，其当时的除夕 PM2.5 是否异常")
    print("=" * 78)
    for y_prev, y in zip(years, years[1:]):
        leavers = [c for c in cities
                   if usable.get((c, y_prev), 0) >= 10 and usable.get((c, y), 0) <= 5]
        joiners = [c for c in cities
                   if usable.get((c, y_prev), 0) <= 5 and usable.get((c, y), 0) >= 10]
        lv = [eveval[(c, y_prev)] for c in leavers if (c, y_prev) in eveval]
        st = [eveval[(c, y_prev)] for c in balanced if (c, y_prev) in eveval]
        msg = "  %d→%d: 退出 %3d 城、新进 %3d 城" % (y_prev, y, len(leavers), len(joiners))
        if lv:
            msg += " | 退出城市在 %d 的除夕 PM2.5 %.1f (n=%d) vs 全程在场 %.1f" % (
                y_prev, mean(lv), len(lv), mean(st))
        print(msg)

    # ---------- 导出矩阵 ----------
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["city", "in_balanced"] + ["usable_%d" % y for y in years])
        for c in cities:
            w.writerow([c, "Y" if c in balanced else "N"]
                       + [usable.get((c, y), 0) for y in years])
    print("\n导出在场矩阵: %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
