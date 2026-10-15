#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 3：选样与代表性检验

用途
----
按数据可得性选样会引入系统偏差——愿意公开执法数据的城市，治理能力可能更强、
执行更严，从而高估执行效果。本脚本把入选城市与全国平衡面板逐项对比，**明示**
它们在哪些维度上不具代表性。这是披露，不是消除。

注意：不要为了让样本"看起来有代表性"而反复换城市——那正是偏差本身。

用法
----
  python3 -I select_sample.py
  python3 -I select_sample.py --out data/sample_20cities.csv

输出
----
  data/sample_20cities.csv   每城：基线、初一日均、倍数、增量，以及三者在
                             308 城平衡面板中的 z 值
  stdout                     入选城市与全国均值／中位数的对照
"""

import argparse
import csv
import os
import statistics as st
from collections import defaultdict

# 候选名单：来自 policy/切换城市名单.md。切换城市在前，对照城市在后。
# (城市名, 省份, 类型标记) —— 类型标记仅用于输出分组，不参与计算
CANDIDATES = [
    # 有类型或范围切换
    ("武汉", "湖北", "切换-范围"),
    ("石家庄", "河北", "切换-范围"),
    ("太原", "山西", "切换-省级"),
    ("忻州", "山西", "切换-省级"),
    ("大连", "辽宁", "切换-待核"),
    ("鞍山", "辽宁", "切换-待核"),
    ("昆明", "云南", "切换-待核"),
    ("郑州", "河南", "切换-双向待核"),
    ("洛阳", "河南", "切换-待核"),
    ("南阳", "河南", "切换-待核"),
    ("东营", "山东", "切换-待核"),
    ("滨州", "山东", "切换-待核"),
    ("珠海", "广东", "切换-待核"),
    ("东莞", "广东", "切换-待核"),
    ("杭州", "浙江", "切换-待核"),
    ("兰州", "甘肃", "切换-待核"),
    ("白银", "甘肃", "切换-待核"),
    # 对照（样本期内政策未变，仍全面禁放）
    ("北京", "北京", "对照"),
    ("上海", "上海", "对照"),
    ("成都", "四川", "对照"),
]

BASELINE_RELS = (-7, -6, -5, -4, -3, -2)
PEAK_REL = 1


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def city_stats(rows, city):
    """返回 (baseline, peak, ratio, increment)；数据不足返回 None。"""
    base, peak = [], []
    for r in rows:
        if r["city"] != city:
            continue
        v = fnum(r["pm25"])
        if v is None:
            continue
        rel = int(r["rel_day"])
        if rel in BASELINE_RELS:
            base.append(v)
        elif rel == PEAK_REL:
            peak.append(v)
    if not base or not peak:
        return None
    b, p = st.mean(base), st.mean(peak)
    return b, p, (p / b if b else float("nan")), p - b


def zscores(values):
    m, sd = st.mean(values), st.pstdev(values)
    return m, sd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default="data/sample_20cities.csv")
    args = ap.parse_args()
    # 默认参数是相对路径；从项目目录之外运行会解析到错误位置，甚至抛 FileNotFoundError
    # 而报错信息看不出是路径问题。统一以仓库根目录为基准；绝对路径不受影响。
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    panel = list(csv.DictReader(
        open(os.path.join(args.data_dir, "panel_cityday.csv"), encoding="utf-8-sig")))
    bal = {r["city"] for r in csv.DictReader(
        open(os.path.join(args.data_dir, "coverage_city_year.csv"), encoding="utf-8-sig"))
        if r["in_balanced"] == "Y"}

    # 全国平衡面板的分布（作为比较基准）
    nat = defaultdict(list)
    for c in bal:
        s = city_stats(panel, c)
        if s:
            nat["baseline"].append(s[0])
            nat["ratio"].append(s[2])
            nat["increment"].append(s[3])
    stats = {k: zscores(v) for k, v in nat.items()}
    print("全国平衡面板：%d 城" % len(nat["baseline"]))
    for k, (m, sd) in stats.items():
        print("  %-10s 均值 %8.2f   标准差 %8.2f   中位数 %8.2f"
              % (k, m, sd, st.median(nat[k])))

    # 逐城计算与 z 值
    out_rows, miss = [], []
    for city, prov, tag in CANDIDATES:
        if city not in bal:
            miss.append("%s（不在平衡面板内）" % city)
            continue
        s = city_stats(panel, city)
        if s is None:
            miss.append("%s（数据不足）" % city)
            continue
        b, p, ratio, inc = s
        z = lambda k, v: (v - stats[k][0]) / stats[k][1] if stats[k][1] else float("nan")
        out_rows.append({
            "city": city, "province": prov, "tag": tag,
            "baseline_pm25": round(b, 1), "day1_pm25": round(p, 1),
            "spike_ratio": round(ratio, 3), "spike_increment": round(inc, 1),
            "z_baseline": round(z("baseline", b), 2),
            "z_ratio": round(z("ratio", ratio), 2),
            "z_increment": round(z("increment", inc), 2),
        })

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    cols = ["city", "province", "tag", "baseline_pm25", "day1_pm25",
            "spike_ratio", "spike_increment", "z_baseline", "z_ratio", "z_increment"]
    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    print("\n写入 %s（%d 城）" % (args.out, len(out_rows)))
    if miss:
        print("未能计算：%s" % "；".join(miss))

    # 代表性判断
    print("\n=== 入选城市 vs 全国 ===")
    print("%-8s %-12s %8s %8s %8s   %s" % ("城市", "类型", "基线", "倍数", "增量", "z(基线,倍数,增量)"))
    for r in out_rows:
        print("%-8s %-12s %8.1f %8.2f %8.1f   (%+.2f, %+.2f, %+.2f)"
              % (r["city"], r["tag"], r["baseline_pm25"], r["spike_ratio"],
                 r["spike_increment"], r["z_baseline"], r["z_ratio"], r["z_increment"]))

    if out_rows:
        ab = st.mean([abs(r["z_baseline"]) for r in out_rows])
        ar = st.mean([abs(r["z_ratio"]) for r in out_rows])
        ai = st.mean([abs(r["z_increment"]) for r in out_rows])
        print("\n平均绝对 z 值：基线 %.2f，倍数 %.2f，增量 %.2f" % (ab, ar, ai))
        worst = max([("基线", ab), ("倍数", ar), ("增量", ai)], key=lambda t: t[1])
        print("→ 入选城市偏离全国最明显的是【%s】；论文数据部分必须写明这一点。" % worst[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
