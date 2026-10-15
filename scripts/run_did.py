#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 4 后半：第一层估计（自实现，供与 Stata 的 did_multiplegt 对表）

⚠️ 关于本脚本的性质，先说清楚
------------------------------
`did_multiplegt`（Stata）与 R 的对应实现是官方版本，本脚本是**用 Python 自实现的
对照版**，只为在没有 Stata 时也能跑出可比数字、并让口径可复核。它与官方实现存在
已知差异（权重细节、推断方法）。**论文的主结果应报告官方实现的结果，本脚本用于
交叉核对。** 两处不一致时以官方实现为准，并把差异写进稳健性说明。

三个估计量并列
--------------
1. 事件研究：以政策切换年为 0，画切换前后各年的 DID 路径（非切换城市提供反事实趋势）
2. DCDH 式估计（de Chaisemartin & D'Haultfœuille 2020 的核心思路）：
   逐期把城市分为「进入处理」「退出处理」「本期未变动」，以未变动者为对照分别估计，
   再按切换单位数加权汇总。**不要求处理不可逆**，因此适用于 2023 年后的"禁改限"。
3. TWFE：双向固定效应回归（平衡面板下用双向去均值精确实现），标准误聚类到城市。
   报告它是为了展示三者差异的来源，**不作为主结果**。

关键设计前提（务必先读）
------------------------
* **非切换城市不等于"未处理城市"。** 据公安部口径，2018 年已有 803 个城市全面禁放；
  而我们的政策库目前只覆盖十几个城市。因此：
  - DCDH 的对照是"**本期状态未变动**"的城市，不要求它们未受管制——这一点是 DCDH
    相对 TWFE 的优势，本脚本正是利用它；
  - 但"未变动"本身是**假设**：一个没有政策记录的城市，可能恰好在这一期改了政策而
    我们不知道。这类测量误差会把效应**推向零**。政策库覆盖得越全，这个偏误越小。
* 因此脚本会打印"本期未变动"的城市数与被剔除的城-年数，**不要忽略**。

用法
----
  python3 -I run_did.py
  python3 -I run_did.py --treat full_ban --outcome spike_increment
  python3 -I run_did.py --treat ban --outcome pm25_d1   # 与上一行对照，符号应一致

输出
----
  data/did_results.csv    逐期与汇总估计
  stdout                  样本构成、事件研究路径、三法对照
"""

import argparse
import csv
import os
import statistics as st
from collections import defaultdict

def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def build_treat(row, kind):
    """由政策列构造 0/1 处理变量。

    ⚠️ 空值按 **0（无禁令记录）** 处理，不当作缺失剔除。理由：政策库目前只覆盖十几个
    城市，若把空值当缺失，样本里就只剩武汉和郑州，一个对照单位都不剩。
    但要注意这是**记录口径而非事实主张**——一个没有政策记录的城市可能其实有禁令。
    这类测量误差会把效应**推向零**，政策库覆盖越全偏误越小。论文中必须写明。
    """
    pt = (row.get("policy_type") or "").strip()
    sl = (row.get("scope_level") or "").strip()
    if kind == "ban":
        return 1 if pt == "3" else 0
    if kind == "full_ban":
        return 1 if (pt == "3" and sl == "1") else 0
    if kind == "scope1":
        return 1 if sl == "1" else 0
    raise ValueError(kind)


def twfe_cluster(y, d, units, times):
    """平衡面板双向固定效应：双向去均值求 β，标准误聚类到单位。"""
    n = len(y)
    gm_y, gm_d = st.mean(y), st.mean(d)
    uy, ud = defaultdict(list), defaultdict(list)
    ty, td = defaultdict(list), defaultdict(list)
    for i in range(n):
        uy[units[i]].append(y[i]); ud[units[i]].append(d[i])
        ty[times[i]].append(y[i]); td[times[i]].append(d[i])
    my = {k: st.mean(v) for k, v in uy.items()}
    md = {k: st.mean(v) for k, v in ud.items()}
    ny = {k: st.mean(v) for k, v in ty.items()}
    nd = {k: st.mean(v) for k, v in td.items()}
    yd = [y[i] - my[units[i]] - ny[times[i]] + gm_y for i in range(n)]
    dd = [d[i] - md[units[i]] - nd[times[i]] + gm_d for i in range(n)]
    var = sum(v * v for v in dd)
    if var == 0:
        return None, None, 0
    beta = sum(yd[i] * dd[i] for i in range(n)) / var
    resid = [yd[i] - beta * dd[i] for i in range(n)]
    # 聚类稳健方差（单位层面）
    g = defaultdict(float)
    for i in range(n):
        g[units[i]] += dd[i] * resid[i]
    G = len(g)
    meat = sum(v * v for v in g.values())
    se = None
    if G > 1 and var > 0:
        se = (meat / (var ** 2)) * (G / (G - 1))
        se = se ** 0.5
    return beta, se, G


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/panel_cityyear.csv")
    ap.add_argument("--out", default="data/did_results.csv")
    ap.add_argument("--treat", default="ban",
                    choices=["ban", "full_ban", "scope1"])
    ap.add_argument("--outcome", default="pm25_d1",
                    choices=["pm25_d1", "pm25_win", "spike_increment"])
    ap.add_argument("--min-year", type=int, default=0,
                    help="只用该年及以后的观测（默认自动取处理城市首条记录的年份）")
    args = ap.parse_args()

    raw = list(csv.DictReader(open(args.inp, encoding="utf-8-sig")))
    # 构造处理变量；无法判定的城-年剔除
    recs, dropped = [], 0
    for r in raw:
        d = build_treat(r, args.treat)
        y = fnum(r[args.outcome])
        if y is None:
            dropped += 1
            continue
        r["_d"], r["_y"] = d, y
        r["_year"] = int(r["cny_year"])
        recs.append(r)

    # 处理城市 = 有政策记录的城市；未变动 = 记录内该期前后相同
    pol_cities = {r["city"] for r in raw if (r.get("policy_type") or "").strip()}
    first_year = defaultdict(lambda: 10 ** 9)
    for r in raw:
        if (r.get("policy_type") or "").strip():
            first_year[r["city"]] = min(first_year[r["city"]], int(r["cny_year"]))
    # 窗口起点：取"首条记录就是禁放（type=3）"的城市中**最晚**的首记录年份。
    # 理由——首记录为禁放的城市，若窗口早于其首记录，前面被当成 0（无记录）就会造出
    # 一次假的 0→1 切换（山西各市会假切换于 2021）。首记录本就是限放或无记录的城市
    # 不受此影响（它们在各年都是非切换者）。
    first_ban = {}
    for r in raw:
        if (r.get("policy_type") or "").strip() == "3":
            c = r["city"]
            first_ban[c] = min(first_ban.get(c, 10 ** 9), int(r["cny_year"]))
    min_year = args.min_year or (max(first_ban.values()) if first_ban else 0)
    recs = [r for r in recs if r["_year"] >= min_year]
    print("窗口起点 %d（= 政策城市中首条记录最晚的年份，避免把「首次入记录」误当切换）"
          % min_year)

    # 平衡筛查：剔除年份不全的城市
    bycity = defaultdict(dict)
    for r in recs:
        bycity[r["city"]][r["_year"]] = r
    years = sorted({r["_year"] for r in recs})
    keep = [c for c, dd in bycity.items() if len(dd) == len(years)]
    recs = [r for r in recs if r["city"] in keep]
    units = sorted({r["city"] for r in recs})
    print("样本：%d 城 × %d 年 = %d 行（%d—%d）；因处理变量或结果缺失剔除 %d 个城-年"
          % (len(units), len(years), len(recs), years[0], years[-1], dropped))
    print("处理变量 %s；结果变量 %s" % (args.treat, args.outcome))
    n_pol = len([c for c in units if c in pol_cities])
    print("其中政策库覆盖 %d 城，其余 %d 城无政策记录（在 DCDH 中只能充当"
          "「本期未变动」的对照，不能视为未受管制）" % (n_pol, len(units) - n_pol))

    # 逐期切换者
    idx = {(r["city"], r["_year"]): r for r in recs}
    events = []
    for t0, t1 in zip(years, years[1:]):
        ins = [c for c in units if idx[(c, t0)]["_d"] == 0 and idx[(c, t1)]["_d"] == 1]
        outs = [c for c in units if idx[(c, t0)]["_d"] == 1 and idx[(c, t1)]["_d"] == 0]
        stay = [c for c in units if idx[(c, t0)]["_d"] == idx[(c, t1)]["_d"]]
        if not ins and not outs:
            continue
        def dy(c):
            return idx[(c, t1)]["_y"] - idx[(c, t0)]["_y"]
        base = st.mean([dy(c) for c in stay]) if stay else 0.0
        e_in = (st.mean([dy(c) for c in ins]) - base) if ins else None
        e_out = (-(st.mean([dy(c) for c in outs]) - base)) if outs else None
        events.append({"period": "%d→%d" % (t0, t1), "n_in": len(ins), "n_out": len(outs),
                       "n_stay": len(stay), "ctrl_change": round(base, 2),
                       "est_in": round(e_in, 2) if e_in is not None else "",
                       "est_out": round(e_out, 2) if e_out is not None else ""})
        print("\n[%d→%d] 进入处理 %d 城，退出处理 %d 城，本期未变动 %d 城"
              % (t0, t1, len(ins), len(outs), len(stay)))
        print("   对照组的平均变化 %+.2f；进入处理的效应 %s；退出处理的效应 %s"
              % (base,
                 "%+.2f" % e_in if e_in is not None else "—",
                 "%+.2f" % e_out if e_out is not None else "—"))
        if ins:
            print("   进入的城市：%s" % "、".join(ins[:12]))
        if outs:
            print("   退出的城市：%s" % "、".join(outs[:12]))

    # ---------- 事件路径：平行趋势的安慰剂证据 ----------
    # 把"在窗口内发生过切换"的城市与"始终未切换"的城市逐期对比。切换之前的期对
    # 若已显示系统性差异，平行趋势就不成立；那时主估计不可信。
    switchers = set()
    for t0, t1 in zip(years, years[1:]):
        for c in units:
            if idx[(c, t0)]["_d"] != idx[(c, t1)]["_d"]:
                switchers.add(c)
    never = [c for c in units if c not in switchers]
    print("\n=== 事件路径：最终切换城市（%d 个）vs 始终未切换城市（%d 个）==="
          % (len(switchers), len(never)))
    print("逐期相对变化（正值 = 切换城市比其他城市涨得多）")
    for t0, t1 in zip(years, years[1:]):
        if not switchers or not never:
            break
        a = st.mean([idx[(c, t1)]["_y"] - idx[(c, t0)]["_y"] for c in switchers])
        b = st.mean([idx[(c, t1)]["_y"] - idx[(c, t0)]["_y"] for c in never])
        has_ev = any(idx[(c, t0)]["_d"] != idx[(c, t1)]["_d"] for c in units)
        print("  %d→%d  %+7.2f   %s" % (t0, t1, a - b,
              "← 含切换事件" if has_ev else "（切换前，安慰剂）"))

    # 加权汇总（按切换单位数）
    num = den = 0.0
    for ev in events:
        for k, w in (("est_in", ev["n_in"]), ("est_out", ev["n_out"])):
            if ev[k] != "" and w:
                num += ev[k] * w; den += w
    agg = (num / den) if den else None
    print("\nDCDH 式汇总（按切换单位数加权）：%s"
          % ("%+.2f" % agg if agg is not None else "无切换事件，无法估计"))
    if den and den < 20:
        print("   ⚠️ 切换单位合计仅 %d 个，置信区间会很宽，结论只能作为方向性证据。" % den)

    # TWFE 对照
    y = [r["_y"] for r in recs]; d = [r["_d"] for r in recs]
    us = [r["city"] for r in recs]; ts = [r["_year"] for r in recs]
    beta, se, G = twfe_cluster(y, d, us, ts)
    print("\nTWFE 对照：β = %s，聚类标准误 = %s（聚类数 %d）"
          % ("%+.2f" % beta if beta is not None else "—",
             "%.2f" % se if se else "—", G))
    print("   （TWFE 在交错实施且效应异质时有负权重问题，此处仅作对照，不作主结果）")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["period", "n_switch_in", "n_switch_out", "n_stay",
                    "control_mean_change", "est_switch_in", "est_switch_out"])
        for ev in events:
            w.writerow([ev["period"], ev["n_in"], ev["n_out"], ev["n_stay"],
                        ev["ctrl_change"], ev["est_in"], ev["est_out"]])
        w.writerow(["AGGREGATE", "", "", "", "", agg if agg is not None else "", ""])
    print("\n写入 %s（%d 个切换期）" % (args.out, len(events)))
    print("提醒：**不要**改动结果变量或处理变量的定义来让估计变显著；"
          "两套口径的符号应一致，不一致就要如实报告。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
