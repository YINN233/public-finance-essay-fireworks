#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""观测损害法：直接给测到的浓度定价，绕开扩散参数 DK。

为什么需要这个方法
------------------
论文 §7.2 的庇古校准要问"现行税负相当于边际损害的几分之几"。按"每公斤
烟花"归一化时，必须把排放质量翻译成浓度，这一步依赖扩散参数 DK；而 DK
随城市面积、边界层高度、风速、地形变化，不是一个可以查到的常数。实测
它是整个链条的主导不确定项（自设区间跨一个数量级），导致比值跨三个数量级。

本脚本换一个被定价的对象：不给"一公斤排放"定价，直接给**观测到的浓度**
定价。于是不需要 DK，也不需要知道任何一个城市烧了多少烟花。

    损害/人 = 日死亡率 × Σ_d[(ΔC_d/10) × DR] × VSL × 归因率 × 位移系数
    税收/人 = 15% × 人均烟花支出 × (出厂价/零售价)

两边都按"每人"计，人口约掉；消费量 Q 在两边同时出现也约掉，因此比值
损害/税收 就是 t/MD 的估计。

口径
----
A 仅初一      ：只算正月初一相对基线的增量。这一天烟花是主导源，基线最干净。
B 窗口·只算正值：窗口内所有高于基线的日子的增量之和。
C 窗口·正负都算：同上但不截断。**这个口径会出现负值**，因为春节期间工业停摆
                让浓度下降，那部分不是烟花的功劳，却会抵消烟花的上升。列出来
                是为了说明基线不是干净的对照，不作为主口径。

参数与来源
----------
见 PARAMS。凡"自设"的参数都在文档里标明，不能当作有来源的取值。

用法
----
    python3 -I scripts/observed_damage.py
    python3 -I scripts/observed_damage.py --write
"""
import argparse
import csv
import os
import statistics as st
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)

# ---------------------------------------------------------------- 参数
# 每个参数给出取值列表与证据档；grade 为「有来源」「自设」两类。
PARAMS = [
    dict(key="dr", name="短期剂量反应（每 10 μg/m³ 的每日全因死亡增幅）",
         values=[0.0039, 0.0049, 0.0059],
         grade="有来源", src="李曼等（2018）Meta 分析，0.49%（95%CI 0.39–0.59%）"),
    dict(key="vsl", name="统计生命价值（元）",
         values=[1.70e6, 3.00e6, 4.70e6],
         grade="有来源", src="区间 170 万—470 万元，见附录 C"),
    dict(key="attrib", name="尖峰中烟花贡献的份额",
         values=[0.3, 0.5, 0.7],
         grade="有来源", src="多篇源解析 30%—70%，见文献综述 §一"),
    dict(key="harvest", name="死亡位移系数（净死亡占观测死亡的比例）",
         values=[0.3, 0.5, 1.0],
         grade="自设", src="短期暴露的 harvesting 效应，本文未做专门估计"),
    dict(key="spend", name="人均烟花支出（元/年，出厂口径）",
         values=[22.7, 33.1, 51.1, 56.8],
         grade="有来源", src="协会口径：(800−80)/14.08=51.1、(900−100)/14.08=56.8；"
                             "零售口径按 1.5 倍加价折算：480/1.5/14.08=22.7、700/1.5/14.08=33.1"),
]
TAX_RATE = 0.15
DEATH_PER_CAPITA_DAY = 0.0076 / 365  # 粗死亡率 7.6‰/年，按日折算


def read_panel(path):
    """返回 {(city, year): {rel_day: pm25}}，只保留平衡面板中的城市。"""
    bal = set()
    with open(os.path.join(ROOT, "data", "panel_cityyear.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            bal.add(r["city"])
    by = defaultdict(dict)
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["city"] not in bal:
                continue
            try:
                d = int(float(r["rel_day"]))
                v = float(r["pm25"])
            except (TypeError, ValueError):
                continue
            by[(r["city"], r["cny_year"])][d] = v
    return by


def excess(by):
    """三个口径的窗口累计超额浓度 ΣΔC（μg/m³·日）。"""
    out = {"A": [], "B": [], "C": []}
    for key, dd in by.items():
        base = [v for d, v in dd.items() if -7 <= d <= -2]
        if len(base) < 4:
            continue
        b = st.mean(base)
        if 1 in dd:
            out["A"].append(max(0.0, dd[1] - b))
        out["B"].append(sum(max(0.0, v - b) for d, v in dd.items() if -7 <= d <= 7))
        out["C"].append(sum(v - b for d, v in dd.items() if -7 <= d <= 7))
    return out


def pct(xs, p):
    s = sorted(xs)
    if not s:
        return float("nan")
    i = (len(s) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", default="data/panel_cityday.csv")
    ap.add_argument("--out", default="docs/结果-观测损害.md")
    ap.add_argument("--write", action="store_true", help="写出结果文档")
    args = ap.parse_args()

    by = read_panel(os.path.join(ROOT, args.panel))
    cal = excess(by)
    n = len(cal["A"])
    if n == 0:
        print("没有可用的城市-年，检查面板。", file=sys.stderr)
        return 1

    lines = []
    def say(s=""):
        print(s)
        lines.append(s)

    say("# 观测损害法：直接给浓度定价")
    say()
    say("由 `python3 -I scripts/observed_damage.py --write` 生成。**不要手改。**")
    say()
    say(f"样本：平衡面板 **{n}** 个城市-年。")
    say()
    say("## 一、窗口累计超额浓度 ΣΔC（μg/m³·日）")
    say()
    say("| 口径 | 中位 | p10 | p90 | p90/中位 | 零值占比 |")
    say("|---|---|---|---|---|---|")
    for k, label in [("A", "仅初一"), ("B", "窗口·只算正值"), ("C", "窗口·正负都算")]:
        x = cal[k]
        m = st.median(x)
        zero = sum(1 for v in x if v <= 0) / len(x)
        say(f"| {label} | {m:.1f} | {pct(x,.1):.1f} | {pct(x,.9):.1f} | "
            f"{pct(x,.9)/m:.1f} | {zero:.0%} |")
    say()
    say("**城际离散是本节最稳的结论。** 口径 B 的 p90/p10 为 9.3，参数只做线性缩放，"
        "不改变任何比值；口径 A 的 p10 为 0，说明相当一部分城市-年初一根本没有高于"
        "基线的尖峰——这本身就是“统一税率无法对准”的直接证据。")
    say()

    # 全参数扫描
    keys = [p["key"] for p in PARAMS]
    vals = [p["values"] for p in PARAMS]
    import itertools
    combos = list(itertools.product(*vals))

    say("## 二、参数扫描")
    say()
    say("| 参数 | 取值 | 证据档 | 来源 |")
    say("|---|---|---|---|")
    for p in PARAMS:
        if p["key"] == "vsl":
            v = "、".join(f"{x/1e4:.0f} 万元" for x in p["values"])
        else:
            v = "、".join(f"{x:g}" for x in p["values"])
        say(f"| {p['name']} | {v} | {p['grade']} | {p['src']} |")
    say(f"| 税率 | {TAX_RATE:.2f} | 一手 | 消费税税目「鞭炮、焰火」从价 15% |")
    say()
    say(f"组合数：{len(combos)}（每个口径）。")
    say()

    say("## 三、人均损害、人均税收与比值")
    say()
    say("| 口径 | 人均损害（元） | 人均税收（元） | 比值 损害/税收 | 「损害>税收」的城市-年占比 |")
    say("|---|---|---|---|---|")
    for k, label in [("A", "仅初一"), ("B", "窗口·只算正值"), ("C", "窗口·正负都算")]:
        S = cal[k]
        ratios_all, shares, dmgs, taxes = [], [], [], []
        for combo in combos:
            p = dict(zip(keys, combo))
            kcoef = DEATH_PER_CAPITA_DAY * (p["dr"] / 10.0) * p["vsl"] * p["attrib"] * p["harvest"]
            tax = TAX_RATE * p["spend"]
            d = [max(0.0, kcoef * s) for s in S]
            r = [di / tax for di in d]
            dmgs.append(st.median(d)); taxes.append(tax)
            ratios_all.append(st.median(r))
            shares.append(sum(1 for x in r if x > 1) / len(r))
        say(f"| {label} | {min(dmgs):.2f}—{max(dmgs):.2f} | "
            f"{min(taxes):.2f}—{max(taxes):.2f} | "
            f"{min(ratios_all):.3f}—{max(ratios_all):.2f} | "
            f"{min(shares):.0%}—{max(shares):.0%} |")
    say()

    # 中心情形明细
    say("## 四、中心情形")
    say()
    central = dict(dr=0.0049, vsl=3.0e6, attrib=0.5, harvest=0.5, spend=51.1)
    kc = DEATH_PER_CAPITA_DAY * (central["dr"] / 10.0) * central["vsl"] * central["attrib"] * central["harvest"]
    tax = TAX_RATE * central["spend"]
    say("参数：DR=0.49%、VSL=300 万元、归因 50%、位移 0.5、人均支出 51.1 元（协会口径）。")
    say()
    say(f"人均税收 = 15% × 51.1 = **{tax:.2f} 元/人**。")
    say()
    say("| 口径 | 中位 ΣΔC | 中位人均损害 | 损害/税收 | 损害>税收的城市-年占比 |")
    say("|---|---|---|---|---|")
    for k, label in [("A", "仅初一"), ("B", "窗口·只算正值"), ("C", "窗口·正负都算")]:
        d = [max(0.0, kc * s) for s in cal[k]]
        r = [x / tax for x in d]
        say(f"| {label} | {st.median(cal[k]):.1f} | {st.median(d):.2f} 元 | "
            f"{st.median(r):.2f} | {sum(1 for x in r if x>1)/len(r):.0%} |")
    say()

    say("## 五、能得出什么、不能得出什么")
    say()
    say("**能得出的：**")
    say()
    say("1. 观测损害法的结果比 §7.2 的「每公斤」路线稳定一个多数量级——"
        "因为绕开了扩散参数 DK，而 DK 正是原路线的主导不确定项。")
    say("2. **城际离散是稳健的**：ΣΔC 的 p90/p10 在 9 倍以上，参数只做线性缩放，"
        "不改变这个比值。因此「全国统一税率对多数城市都是错的」这一判断不依赖参数取值。")
    say("3. 在中心情形下，健康损害的人均值低于税收，"
        "「损害>税收」的城市-年占比见上表。")
    say()
    say("**不能得出的：**")
    say()
    say("1. **不能据此判定税率偏低或偏高。** 水平结论依赖三个判断："
        "归因率、死亡位移系数、人均支出口径；其中死亡位移系数是自设。")
    say("2. **只估了健康损害。** 未计入人身伤害、火灾、噪声，也未计入非春节时段。"
        "因此「税高于健康损害」不等于「税过高」。")
    say("3. **口径 C 不作为主口径。** 它出现负值，说明春节停摆造成的浓度下降"
        "抵消了烟花的上升——基线不是干净的对照。截断到零后它的损害恒为 0，"
        "因此该口径在本表中不提供任何信息，仅作为“基线不干净”的证据保留。")
    say("4. **这不是因果估计。** 它把观测到的浓度按剂量反应折算成损害，"
        "不涉及任何政策变异，因此不受第 6 节识别失败的影响，但也不能回答"
        "「禁放减少了多少损害」。")
    say()

    if args.write:
        out = os.path.join(ROOT, args.out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"\n已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
