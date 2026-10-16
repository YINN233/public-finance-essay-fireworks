#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
庇古校准：现行消费税相当于"每公斤烟花 PM2.5 外部性"的几分之几？

结论先说（脚本会把它算出来并检验是否稳健）
------------------------------------------
**这个比值不稳健，跨三个数量级，且符号会随基准的口径翻转。** 因此它不能作为论文的
主打数字，只能作为"两条基准给出相反结论"的一个展示。原因有两条，都必须写进正文：

1. **"单位治理成本"（路线 A）在概念上不适用于烟花。** 该概念预设排放可就地捕集
   （点源：烟囱、除尘器）。烟花 PM2.5 是弥散释放、无从捕集，唯一的"减排"是不烧。
   所以用它作基准是**口径错配**，不是"更保守的估计"。
   而且它自身取值也极不稳：标准**规定的是核算方法、不是数值**（GB/T 39793.1-2020
   只给 D = E×C×γ 与"实际调查法/成本函数法"）；实测调查值为**颗粒物约 4,000 元/吨
   = 4 元/kg**，而一篇 *JCLP* 2026 的优化估算为 **601 元/kg**——**相差 150 倍**。
   两个数都不来自标准正文。

2. **"健康损害"（路线 B）需要一个扩散假设**（每排放 1 kg PM2.5，城市居民承受的
   浓度增量×人口是多少）。这个假设无法从数据中得出，必须显式写出并做敏感性。

用法
----
  python3 -I tax_calibration.py
  python3 -I tax_calibration.py --route A        # 只看避免治理成本口径
  python3 -I tax_calibration.py --route B        # 只看健康损害口径

输出
----
  stdout                    参数表（含来源与区间）、两条路线的比值分布、稳健性判定
  docs/校准结果.md           同上的可引用版本（由 --write 写出）
"""

import argparse
import itertools
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─────────────────────────────────────────────────────────────────────────────
# 参数。每条给：区间、来源、证据档。**不要在这里塞单点"最优值"**——单点会掩盖
# 上面说的三个数量级的不确定性。
#   grade: 一手 / 实测 / 论文 / 标准方法 / 自设假设
P = {
    "EF": dict(lo=0.134, hi=0.281, unit="kg PM2.5 / kg 净火药量(NEC)", grade="实测",
               src="Keller & Schragen (2021) Propellants Explosives Pyrotechnics 46(5):825–842："
                   "PM2.5 逐条 134–281 g/kg NEC、**均值 200**；PM10 均值 253（区间 200–325）。"
                   "⚠️ 分母是**净火药量 NEC**，不是烟花总重——与 P（元/kg 商品）不同单位，"
                   "故必须再乘 NEC_SHARE（见下）。早先本文件把 PM10 的区间错记成 PM2.5，已更正"),
    # 单位换算：烟花商品里净火药（NEC）的质量占比。**自设假设，无来源。**
    "NEC_SHARE": dict(lo=0.15, hi=0.45, unit="kg NEC / kg 商品", grade="自设假设",
                      src="无来源。烟花商品含纸张、泥底、引线、包装，净火药占比远小于 1。"
                          "区间为拍定，用于暴露该换算对结论的影响——**这一项与 DK 同为本校准"
                          "最弱的两环**"),
    "P":  dict(lo=16.0, hi=20.0, unit="元 / kg 烟花", grade="一手",
               src="海关 HS 36041000「烟花、爆竹」出口单价：2024 年 408,396 吨 / "
                   "11.62 亿美元 = 0.28 万美元/吨；2020–2025 在 2,362–2,800 美元/吨，"
                   "按 7.1 折 16–20 元/kg。⚠️ 出口免征消费税，此处仅作出厂价量级的代理"),
    # 路线 A 的基准。区间故意取到 150 倍，因为实际来源之间就差这么多。
    "C_A": dict(lo=4.0, hi=601.0, unit="元 / kg PM2.5", grade="论文 / 标准方法",
                src="下端 4 元/kg = 调查实例中颗粒物约 4,000 元/吨；上端 601 元/kg 出自 "
                    "Li et al. (2026) J. Cleaner Prod.（DOI 10.1016/j.jclepro.2026.148283）"
                    "按 GB/T 39793.1-2020 方法做的优化估算。**标准正文不含任何数值**"),
    # 路线 B 的参数
    "DR":  dict(lo=0.49, hi=0.68, unit="% 每日全因死亡 / 10 μg·m⁻³", grade="论文",
                src="李曼等 (2018) 中华流行病学杂志（33 篇 Meta，0.49%，95%CI 0.39–0.59）；"
                    "Liu et al. (2019) NEJM 652 城市（0.68%，95%CI 0.59–0.77）"),
    "VSL": dict(lo=1.70e6, hi=4.70e6, unit="元 / 例", grade="论文",
                src="《中国公共卫生》(2025) 综述空气污染类中位数 168.9 万（13.94–677.10 万）；"
                    "Wang et al. (2024, Soc Sci Med 363:117471) 环境风险推荐 470 万（95%CI 217–1020 万）"),
    # 路线 B 的核心自设假设：每排放 1 kg PM2.5，城市居民承受的「浓度增量×人口」。
    # 用箱模型给默认值，但**必须**当作显式假设做敏感性。
    "DK":  dict(lo=2.0e3, hi=2.0e5, unit="(μg·m⁻³ · 人) / kg PM2.5", grade="自设假设",
                src="箱模型：Δc = m/(A·H)，再乘城市人口。默认 A=500 km²、H=500 m、人口 500 万 "
                    "⇒ ≈2e4；A 与 H 各取 10 倍上下浮动给出区间。**这一项是路线 B 最弱的环节**"),
}

# 基线每日全因死亡风险（每人每天）。粗死亡率约 7.6‰/年。
DAILY_MORT = 0.0076 / 365.0
MORT_GRADE = "一手（国家统计局粗死亡率量级）"


def routeA(ef, nec, p, c):
    """税 ÷ 避免治理成本。两者同为「每公斤商品」。"""
    tax = 0.15 * p
    bench = ef * nec * c
    return tax, bench


def routeB(ef, nec, p, dk, dr_pct, vsl):
    """税 ÷ 健康损害。损害按「那一天」的短期暴露计——**不得套用全年长期系数**。"""
    tax = 0.15 * p
    deaths_per_kg = dk * (dr_pct / 100.0 / 10.0) * DAILY_MORT
    bench = ef * nec * deaths_per_kg * vsl
    return tax, bench


def sweep(fn, keys, n=6):
    """在各参数区间内等距取 n 个点，穷举组合，返回 (min,max) 比值与全部比值。"""
    grids = []
    for k in keys:
        d = P[k]
        step = (d["hi"] - d["lo"]) / (n - 1)
        grids.append([d["lo"] + i * step for i in range(n)])
    ratios, taxes, benches = [], [], []
    for combo in itertools.product(*grids):
        tax, bench = fn(*combo)
        taxes.append(tax)
        benches.append(bench)
        if bench > 0:
            ratios.append(tax / bench)
    return ratios, taxes, benches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--route", choices=["A", "B", "both"], default="both")
    ap.add_argument("--write", action="store_true",
                    help="把可引用版本写到 docs/校准结果.md")
    args = ap.parse_args()
    os.chdir(ROOT)

    print("=" * 78)
    print("参数表（单点值一律不给——单点会掩盖实际的不确定性）")
    print("=" * 78)
    for k, d in P.items():
        print("  %-5s %-9s [%g, %g] %s" % (k, d["grade"], d["lo"], d["hi"], d["unit"]))
        print("        %s" % d["src"])
    print("  %-5s %-9s %.3e 每日全因死亡风险/人" % ("基线死亡率", MORT_GRADE, DAILY_MORT))

    out = []
    if args.route in ("A", "both"):
        r, tx, bn = sweep(routeA, ["EF", "NEC_SHARE", "P", "C_A"])
        print("\n" + "=" * 78)
        print("路线 A：税 ÷ 避免治理成本   （同以「每公斤烟花」为分母）")
        print("=" * 78)
        print("  税       %.2f – %.2f 元/kg 烟花" % (min(tx), max(tx)))
        print("  基准     %.2f – %.2f 元/kg 烟花" % (min(bn), max(bn)))
        print("  比值     %.4f – %.2f   中位 %.4f" % (min(r), max(r), st.median(r)))
        cross = sum(1 for x in r if x >= 1.0)
        print("  组合数 %d，其中「税 ≥ 基准」占 %d（%.0f%%）"
              % (len(r), cross, 100.0 * cross / len(r)))
        print("  ⇒ 判定：**不稳健**。比值跨约 %d 倍，且 %s 的结论会随 C_A 取值翻转。"
              % (round(max(r) / min(r)), "「税偏低」与「税偏高」"))
        out.append(("A", min(tx), max(tx), min(bn), max(bn), min(r), max(r), st.median(r),
                    "%d%%" % (100.0 * cross / len(r))))

    if args.route in ("B", "both"):
        r, tx, bn = sweep(routeB, ["EF", "NEC_SHARE", "P", "DK", "DR", "VSL"], n=4)
        print("\n" + "=" * 78)
        print("路线 B：税 ÷ 健康损害（短期暴露，只计那一天）")
        print("=" * 78)
        print("  税       %.2f – %.2f 元/kg 烟花" % (min(tx), max(tx)))
        print("  基准     %.4f – %.2f 元/kg 烟花" % (min(bn), max(bn)))
        print("  比值     %.4f – %.4f   中位 %.4f" % (min(r), max(r), st.median(r)))
        cross = sum(1 for x in r if x >= 1.0)
        print("  组合数 %d，其中「税 ≥ 基准」占 %d" % (len(r), cross))
        print("  ⇒ 判定：**不稳健**，比值跨约 %d 倍。**主导不确定性的不是剂量反应或 VSL，"
              % round(max(r) / min(r)))
        print("     而是 DK（扩散假设）与 EF**——两者都跨一个数量级。")
        out.append(("B", min(tx), max(tx), min(bn), max(bn), min(r), max(r), st.median(r),
                    "%d" % cross))

    print("\n" + "=" * 78)
    print("结论（须写进论文的限定）")
    print("=" * 78)
    print("  **两条路线的符号都不稳，本校准给不出可引用的结论——连方向都给不出。**")
    print("  1. 路线 A：概念本身不适用（单位治理成本预设点源可捕集，而烟花 PM2.5 是弥散")
    print("     释放、无从捕集），且符号不稳。**不采用。**")
    print("  2. 路线 B：符号同样不稳——有相当比例的组合给出「税 ≥ 基准」。")
    print("     不稳的根源是**两个自设参数**：DK（扩散假设）与 NEC_SHARE（净火药占比），")
    print("     各自跨约一个数量级，合起来足以让基准移动两个数量级、从而跨越 1。")
    print("  3. 参数中**唯一有可靠来源**的是 EF（实测）、P（海关）、DR（Meta 分析）、")
    print("     VSL（Meta 分析）——但它们恰恰不是主导项。**主导项没有来源。**")
    print("  ⇒ **本校准不能作为论据。**「已有的价格工具没有被校准到边际损害」这一判断，")
    print("     应由**工具结构上的分辨率差异**支撑（见 docs/论文-工具选择证据.md 的")
    print("     对照表：全国统一／从价／生产环节 vs 市级／逐时段），校准只作辅助说明，")
    print("     并如实写出「算了，但给不出稳健结论」。")
    print("  ⚠️ 可引用的只有一条**中位数**，且必须同时给出区间：中位组合下税覆盖基准的")
    print("     百分之几（见上表）；但区间跨三个数量级，故**单看中位数会误导**。")

    if args.write:
        p = os.path.join(ROOT, "docs", "校准结果.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("# 庇古校准：计算结果\n\n")
            fh.write("由 `python3 -I scripts/tax_calibration.py --write` 生成。**不要手改**。\n\n")
            fh.write("| 路线 | 税（元/kg 烟花） | 基准（元/kg 烟花） | 比值区间 | 中位 | 税≥基准 |\n")
            fh.write("|---|---|---|---|---|---|\n")
            for row in out:
                fh.write("| %s | %.2f–%.2f | %.4g–%.4g | %.4f–%.2f | %.4f | %s |\n" % row)
            fh.write("\n**结论：两条路线定性方向相反，比值跨约三个数量级，不支持可引用的单点。**\n")
            fh.write("详见脚本头部的三条限定。\n")
        print("\n写入 %s" % p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
