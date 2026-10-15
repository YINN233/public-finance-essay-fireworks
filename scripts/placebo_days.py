#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安慰剂「日」检验：把结果变量换成窗口内的每一个相对日，逐日跑同一个 DID。

为什么这是本项目最重要的一张诊断表
----------------------------------
前几轮诊断都失败了，但都不够决定性：
  * 安慰剂结果变量（pm25_base）—— 说明跨省对照被区域波动污染，但没说明**省内**对照
    是否锁定在燃放上；
  * 安慰剂「年份」—— 只有 1–2 个前置期可用（见 docs/结果-第一层估计.md），太薄；
  * 随机化推断 —— 它的零假设不是因果零假设。

本检验问的是一个更直接的问题：**这个估计量对燃放日有亲和性吗？**
若它真的在测"初一这天的燃放尖峰"，那么把结果变量换成窗口内其他日子时，系数应当
变小且不显著。实测恰恰相反：

    （河南，同省对照，2021—2026，n=17 城）
      rel_day  −6   β=+18.7  t=+2.38 ***
      rel_day  −4   β=−15.0  t=−2.60 ***
      rel_day  +1   β=−10.8  t=−0.56      ← 正月初一，唯一**不**显著的高方差日
      rel_day  +3   β=+35.3  t=+3.21 ***
      rel_day  +6   β=−14.2  t=−3.15 ***

    （山西 2026 放开，全国对照）
      rel_day  −7…−1  |t| = 3.0–7.1 全部 ***      ← "效应"全在除夕之前
      rel_day  +1     β=+22.9  t=+1.73            ← 燃放日本身不显著

**机制**：初一的自身方差最大（尖峰本身），SE 最大；安静日子残差方差小，"显著"是小
分母的产物。所以逐日扫描既说明**设计没有锁定燃放**，也说明那些"显著"的系数不是效应。

用法
----
  python3 -I placebo_days.py --province 河南 --treat-year 2023
  python3 -I placebo_days.py --province 山西 --treat-year 2026 --control all
  python3 -I placebo_days.py --province 河南 --treat-year 2023 --from 2020

  --control same  只用同省未处理城市作对照（该省必须有未处理城市）
  --control all   用全部面板城市作对照

输出
----
  stdout                     逐日 β / SE / t，标出主口径与"显著"日
  data/placebo_days.csv      同上，供画图
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from merge_policy import PROVINCE_CITIES   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_city_province():
    p = os.path.join(ROOT, "data", "city_province.csv")
    out = {}
    if not os.path.exists(p):
        print("!! 找不到 data/city_province.csv，--control same 将退化为全体对照",
              file=sys.stderr)
        return out
    with open(p, encoding="utf-8-sig") as fh:
        lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
    for r in csv.DictReader(lines):
        c, pv = (r.get("city") or "").strip(), (r.get("province") or "").strip()
        if c and pv:
            out[c] = pv
    return out


def demean(v, groups, tol=1e-13, maxit=300):
    """交替投影去多组固定效应。两组且平衡时一轮即精确。"""
    import itertools
    x = list(v)
    n = len(x)
    for _ in range(maxit):
        prev = list(x)
        for g in groups:
            s, c = defaultdict(float), defaultdict(int)
            for i in range(n):
                s[g[i]] += x[i]
                c[g[i]] += 1
            m = {k: s[k] / c[k] for k in s}
            x = [x[i] - m[g[i]] for i in range(n)]
        if max(abs(x[i] - prev[i]) for i in range(n)) < tol:
            break
    return x


def did(obs):
    """obs = [(city, year, y, treat)]。返回 (beta, se, 聚类数, 有效聚类数)。"""
    if len(obs) < 20:
        return None, None, 0, 0
    y = [o[2] for o in obs]
    t = [o[3] for o in obs]
    cs = [o[0] for o in obs]
    ys = [o[1] for o in obs]
    yd = demean(y, [cs, ys])
    td = demean(t, [cs, ys])
    var = sum(v * v for v in td)
    if var <= 0:
        return None, None, 0, 0
    b = sum(yd[i] * td[i] for i in range(len(y))) / var
    e = [yd[i] - b * td[i] for i in range(len(y))]
    g = defaultdict(float)
    for i in range(len(y)):
        g[cs[i]] += td[i] * e[i]
    G = len(g)
    # 有效聚类数 = 残差化处理变量非零的城市数。在城市+年份设定下通常等于 G；
    # 一旦改成省份×年份固定效应，未处理省份的整省都会被吸收，这个数会骤降
    # （见 docs/结果-第一层估计.md：306 → 17）。报告它，避免"306 个聚类"虚高。
    nz = {cs[i] for i in range(len(y)) if abs(td[i]) > 1e-12}
    if G < 2:
        return b, None, G, len(nz)
    se = ((sum(v * v for v in g.values()) / var ** 2) * (G / (G - 1))) ** 0.5
    return b, se, G, len(nz)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--province", required=True)
    ap.add_argument("--treat-year", type=int, required=True,
                    help="处理生效的春节年份（该年起处理组不再处于禁放）")
    ap.add_argument("--control", default="same", choices=["same", "all"])
    ap.add_argument("--direction", default="out", choices=["out", "in"],
                    help="out = 禁放→非禁放（放开）[默认]；in = 非禁放→禁放（收紧）。"
                         "本项目两个批次方向相反：河南 2023 是 out，山东 2024 是 in。"
                         "**早先本脚本硬编码为 out，导致山东批次根本找不到处理组。**")
    ap.add_argument("--from", dest="y0", type=int, default=2021,
                    help="样本起始春节年份（默认 2021，避开各省「首次入记录」造成的假切换）")
    ap.add_argument("--to", dest="y1", type=int, default=2026)
    ap.add_argument("--policy", default="policy/policy.csv")
    ap.add_argument("--out", default="data/placebo_days.csv")
    args = ap.parse_args()
    os.chdir(ROOT)

    prov = read_city_province()
    members = set(PROVINCE_CITIES.get(args.province, []))
    if not members:
        members = {c for c, p in prov.items() if p == args.province}
        if not members:
            print("!! 无法确定 %s 的城市列表" % args.province, file=sys.stderr)
            return 1

    # 城市 × 年 × 相对日
    cell = defaultdict(dict)
    all_city = set()
    with open(os.path.join(ROOT, "data/panel_cityday.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["pm25"] == "":
                continue
            all_city.add(r["city"])
            cell[(r["city"], r["cny_year"])][int(r["rel_day"])] = float(r["pm25"])

    pt = {}
    with open(os.path.join(ROOT, "data/panel_cityyear.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            pt[(r["city"], r["cny_year"])] = (r["policy_type"] or "").strip()

    prev_year = str(args.treat_year - 1)
    if args.direction == "out":
        # 放开：上年禁放、当年不再是禁放
        treat = sorted(c for c in members
                       if pt.get((c, prev_year)) == "3"
                       and pt.get((c, str(args.treat_year))) not in ("3", ""))
    else:
        # 收紧：上年不是禁放（含"无记录"）、当年成为禁放
        treat = sorted(c for c in members
                       if pt.get((c, prev_year)) not in ("3",)
                       and pt.get((c, str(args.treat_year))) == "3")
    if not treat:
        print("!! %s 在 %d 年找不到「%s」的城市（--direction %s）"
              % (args.province, args.treat_year,
                 "禁放 → 非禁放" if args.direction == "out" else "非禁放 → 禁放",
                 args.direction), file=sys.stderr)
        return 1
    tset = set(treat)

    if args.control == "same":
        pool = sorted(c for c in members if c not in tset)
        if not pool:
            print("!! %s 全省都是处理组，同省对照库为空——改 --control all，"
                  "但要记住全国对照已被证明含区域共同波动" % args.province, file=sys.stderr)
            return 1
    else:
        pool = sorted(all_city - tset)
    units = treat + pool
    years = [str(y) for y in range(args.y0, args.y1 + 1)]

    print("省份 %s；处理年 %d（%d→%d）" % (args.province, args.treat_year,
                                            args.treat_year - 1, args.treat_year))
    print("处理组 %d 城：%s" % (len(treat), "、".join(treat)))
    print("对照 %d 城（%s）" % (len(pool), "同省" if args.control == "same" else "全国"))
    print("样本年份 %d–%d；固定效应：城市 + 年份；聚类到城市" % (args.y0, args.y1))
    print("\n=== 逐「相对日」扫描：把结果变量换成每一天，跑同一个 DID ===")
    print("  %-8s %8s %8s %7s %7s  %s"
          % ("rel_day", "β", "SE", "t", "有效聚类", ""))
    rows = []
    for d in range(-7, 8):
        obs = []
        for c in units:
            for y in years:
                v = cell.get((c, y), {}).get(d)
                if v is None:
                    continue
                obs.append((c, y, v, 1.0 if (c in tset and int(y) >= args.treat_year) else 0.0))
        b, se, G, nz = did(obs)
        if b is None:
            print("  %+d       无法估计" % d)
            continue
        t = (b / se) if se else float("nan")
        tag = "← 正月初一（主口径）" if d == 1 else ("← 除夕" if d == 0 else "")
        star = " ***" if se and abs(t) > 2 else ""
        print("  %-8d %+8.1f %8.1f %7.2f %7d  %s%s" % (d, b, se, t, nz, tag, star))
        rows.append([d, round(b, 3), round(se, 3) if se else "", round(t, 3), nz])

    print("\n读法：")
    print("  * 若估计量确实锁定在燃放上，应当**只有 rel_day=+1 大且显著**。")
    print("  * 若其他日子也出现 |t|>2，说明它测的是城市/省份层面的春节前后整体走位，")
    print("    不是烟花。此时主口径的系数不可解读为政策效应。")
    print("  * 注意初一自身方差最大、SE 最大；安静日子的「显著」是小分母造成的。")

    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["province", "treat_year", "rel_day", "beta", "se", "t", "n_eff_clusters"])
        for r in rows:
            w.writerow([args.province, args.treat_year] + r)
    print("\n写入 %s（%d 行）" % (args.out, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
