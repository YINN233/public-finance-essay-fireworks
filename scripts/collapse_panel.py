#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 4 前置：把「城市 × 日」折叠为「城市 × 春节年份」

为什么需要这一步
----------------
政策变异只发生在**年度**上，所以 DiD 的观测单位是城市 × 春节年份，不是城市 × 日。
城市 × 日面板用于描述（尖峰形态、安慰剂），折叠后面板用于估计。

结果变量的口径（沿用 spec §5.2）
------------------------------
  pm25_d1        正月初一（rel_day = +1）的日均 PM2.5
  pm25_win       整个春节窗口（rel_day −7 … +7）的日均
  pm25_base      基线，除夕前 7 日至前 2 日（rel_day −7 … −2）的日均
  spike_ratio    pm25_d1 / pm25_base
  spike_increment pm25_d1 − pm25_base

⚠️ 主口径是 **pm25_d1**（初一），不是除夕。燃放最密集的是除夕深夜跨零点至初一凌晨，
按日历日切分大部分排放落于初一；用除夕（rel_day = 0）会取到被稀释的日均值。

政策状态的取法
--------------
取自**正月初一当日**（rel_day = +1），因为结果变量测的就是那一天的污染。
若该日缺记录，则取窗口内最接近的一日，并在 `policy_day_rel` 列写明实际取的是哪一天。
（窗口内政策若发生变动——例如通告恰在春节前生效——这一列可用来核查。）

用法
----
  python3 -I collapse_panel.py                          # 平衡面板（308 城）
  python3 -I collapse_panel.py --all                    # 全部城市
  python3 -I collapse_panel.py --in data/panel_with_policy.csv

输出
----
  data/panel_cityyear.csv
  stdout 行数校验与覆盖率报告
"""

import argparse
import csv
import os
import statistics as st
from collections import defaultdict

D1_REL = 1
BASE_RELS = (-7, -6, -5, -4, -3, -2)
ALL_RELS = list(range(-7, 8))

# 从政策变量里原样带过来的列（在 policy.csv 里存在才带）
POLICY_COLS = ["policy_type", "scope_level", "ban", "restrict",
               "agency_cat", "tax_instrument", "penalty_detention"]

# 机制变量（spec §5.2）：同样取初一日均／日最大
MECH_COLS = [("so2", "so2_d1"), ("no2", "no2_d1"), ("o3_max", "o3max_d1"),
             ("ratio_pm25_pm10", "ratio_d1")]


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def mean(vals):
    vals = [v for v in vals if v is not None]
    return st.mean(vals) if vals else None


def rnd(v, n=1):
    return round(v, n) if v is not None else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/panel_with_policy.csv")
    ap.add_argument("--out", default="data/panel_cityyear.csv")
    ap.add_argument("--coverage", default="data/coverage_city_year.csv",
                    help="用于核对平衡面板定义；不存在则跳过核对")
    ap.add_argument("--all", action="store_true", help="不限定平衡面板")
    args = ap.parse_args()

    if not os.path.exists(args.inp):
        raise SystemExit("!! 找不到 %s。先运行 scripts/merge_policy.py" % args.inp)

    rows = list(csv.DictReader(open(args.inp, encoding="utf-8-sig")))
    # (city, cny_year) -> {rel_day: row}
    g = defaultdict(dict)
    for r in rows:
        g[(r["city"], int(r["cny_year"]))][int(r["rel_day"])] = r
    years = sorted({y for _, y in g})
    all_cities = sorted({c for c, _ in g})

    out, skipped = [], []
    for (city, yr), byrel in g.items():
        d1 = byrel.get(D1_REL)
        base_vals = [fnum(byrel[k]["pm25"]) for k in BASE_RELS if k in byrel]
        base_vals = [v for v in base_vals if v is not None]
        if d1 is None or fnum(d1["pm25"]) is None or not base_vals:
            skipped.append((city, yr))
            continue
        d1v = fnum(d1["pm25"])
        bv = st.mean(base_vals)
        win_vals = [fnum(byrel[k]["pm25"]) for k in ALL_RELS if k in byrel]
        win_vals = [v for v in win_vals if v is not None]

        # 政策状态：优先初一当日，缺失则取窗口内最接近的一天
        pol_rel, pol_row = None, None
        for k in sorted(byrel, key=lambda x: (abs(x - D1_REL), x)):
            pol_rel, pol_row = k, byrel[k]
            break

        rec = {"city": city, "cny_year": yr,
               "n_days": len(win_vals),
               "n_hours_d1": d1.get("n_hours", ""),
               "pm25_d1": rnd(d1v), "pm25_win": rnd(mean(win_vals)),
               "pm25_base": rnd(bv),
               "spike_ratio": rnd(d1v / bv, 3) if bv else "",
               "spike_increment": rnd(d1v - bv),
               "policy_day_rel": pol_rel}
        for c in POLICY_COLS:
            rec[c] = (pol_row.get(c, "") if pol_row else "")
        for src, dst in MECH_COLS:
            rec[dst] = rnd(fnum(d1.get(src))) if d1.get(src) not in (None, "") else ""
        out.append(rec)

    # 平衡面板：在**全部年份**上都有可用记录的城
    cnt = defaultdict(set)
    for r in out:
        cnt[r["city"]].add(r["cny_year"])
    balanced = sorted(c for c, ys in cnt.items() if len(ys) == len(years))
    if not args.all:
        out = [r for r in out if r["city"] in balanced]

    cols = (["city", "cny_year", "n_days", "n_hours_d1",
             "pm25_d1", "pm25_win", "pm25_base", "spike_ratio", "spike_increment"]
            + POLICY_COLS + ["policy_day_rel"] + [d for _, d in MECH_COLS])
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)

    # ---------- 校验 ----------
    print("输入 %s：%d 行，%d 城，%d 个春节年份"
          % (args.inp, len(rows), len(all_cities), len(years)))
    print("年份：%s" % "、".join(str(y) for y in years))
    print("因缺初一或基线而被跳过的城-年：%d 个" % len(skipped))
    if skipped[:5]:
        print("  例：%s" % "、".join("%s/%d" % s for s in skipped[:5]))
    print("\n可用城-年 %d 个；其中在全部 %d 年可用的城市 %d 个（平衡面板）"
          % (len(out) if args.all else len(out), len(years), len(balanced)))
    print("写入 %s：%d 行" % (args.out, len(out)))

    expect = len(balanced) * len(years)
    if not args.all:
        flag = "OK" if len(out) == expect else "!! 不符，检查是否有城-年被剔除"
        print("行数校验：%d 城 × %d 年 = %d 行  →  实际 %d 行  %s"
              % (len(balanced), len(years), expect, len(out), flag))

    # 与 coverage 文件的平衡面板定义核对
    if os.path.exists(args.coverage):
        cov = {r["city"] for r in csv.DictReader(
            open(args.coverage, encoding="utf-8-sig")) if r["in_balanced"] == "Y"}
        a, b = set(balanced), cov
        if a != b:
            print("\n⚠️ 平衡面板定义与 %s 不一致：" % args.coverage)
            print("   本脚本独有：%s" % "、".join(sorted(a - b)[:8]) or "无")
            print("   coverage 独有：%s" % "、".join(sorted(b - a)[:8]) or "无")
            print("   （coverage 以「可用天数 ≥13」判定；本脚本要求初一与基线日均俱全，")
            print("     口径略严，差异属预期。论文中需说明用哪一个。）")
        else:
            print("平衡面板与 %s 一致（%d 城）" % (args.coverage, len(a)))

    # 逐年城数
    per = defaultdict(int)
    for r in out:
        per[r["cny_year"]] += 1
    print("\n逐年城数：%s" % "  ".join("%d:%d" % (y, per[y]) for y in years))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
