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
import sys
from collections import defaultdict

# -I（隔离模式）不会把脚本所在目录放进 sys.path，故显式加入，才能从同目录导入。
# ⚠️ 必须在 main() 里 chdir 之前算好 ROOT：chdir 之后再对 __file__ 取 abspath，
# 若调用时给的是相对路径就会解析到错误位置。
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
from merge_policy import PROVINCE_CITIES   # 复用省级展开表，避免两处维护同一份名单


def province_map(policy_path, units):
    """城市 → 省份。

    优先读 data/city_province.csv（覆盖全部面板城市，由 check_province_map.py 校验）；
    该文件不存在时退回 policy.csv 的 province 列 + PROVINCE_CITIES 省级展开表——
    但那只能覆盖十几个城市，会让 --same-province 对其余省份**静默失效**，故仅为兜底。
    """
    pv = {}
    mp = os.path.join(ROOT, "data", "city_province.csv")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8-sig") as fh:
            lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
        for r in csv.DictReader(lines):
            c = (r.get("city") or "").strip()
            p = (r.get("province") or "").strip()
            if c and p:
                pv[c] = p
    else:
        print("   !! 未找到 data/city_province.csv，退回 policy.csv 的省份列——"
              "同省对照将只对 policy.csv 覆盖的省份有效", file=sys.stderr)
    try:
        with open(policy_path, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(
                [l for l in fh if not l.lstrip().startswith("#")]))
    except OSError:
        rows = []
    for r in rows:
        c = (r.get("city_name") or "").strip()
        p = (r.get("province") or "").strip()
        if c and p:
            pv.setdefault(c, p)
    for prov, cities in PROVINCE_CITIES.items():
        for c in cities:
            pv.setdefault(c, prov)
    return {c: pv[c] for c in units if c in pv}


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


def demean(vals, groups, tol=1e-12, maxit=5000):
    """交替投影（Frisch–Waugh–Lovell）去掉多组固定效应。

    groups 是若干「id 向量」，每个元素给出该观测属于哪一组。多重固定效应没有闭式解，
    但交替"组内去均值"会收敛到正确的残差（两组时对平衡面板恰好一步即精确）。
    """
    n = len(vals)
    x = list(vals)
    for _ in range(maxit):
        prev = x
        x = list(prev)
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


def fe_cluster(y, d, groups, unit):
    """多组固定效应回归 y ~ d，标准误聚类到 unit。

    返回 (beta, se, 聚类数, 有效聚类数)。
    **有效聚类数 = 残差化处理变量非零的单位数**——在"城市 + 省份×年份"设定下，
    未处理省份的整省变异被省份×年份虚拟变量吸收，其残差化处理变量恒为 0，
    对 β 和 meat 的贡献都是 0。此时报出 306 会严重虚高（实测只有 17 个）。

    用部分消去（FWL）而不是构造虚拟变量矩阵：本脚本其余部分只用标准库，
    引入 numpy 会把依赖带到不必要的地方。

    ⚠️ 标准误口径：这里只乘 CR1 的 G/(G-1)。Stata/`reghdfe` 的 `vce(cluster)`
    默认还要再乘 (N-1)/(N-K)（K 含被吸收的固定效应），实测会大 10%–17%。
    两种约定下的数字都应报告，不要只给一个。
    """
    yd = demean(y, groups)
    dd = demean(d, groups)
    var = sum(v * v for v in dd)
    if var == 0:
        return None, None, 0, 0
    beta = sum(yd[i] * dd[i] for i in range(len(y))) / var
    resid = [yd[i] - beta * dd[i] for i in range(len(y))]
    g = defaultdict(float)
    for i in range(len(y)):
        g[unit[i]] += dd[i] * resid[i]
    G = len(g)
    n_eff = len({unit[i] for i in range(len(y)) if abs(dd[i]) > 1e-12})
    meat = sum(v * v for v in g.values())
    se = None
    if G > 1 and var > 0:
        se = ((meat / (var ** 2)) * (G / (G - 1))) ** 0.5
    return beta, se, G, n_eff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/panel_cityyear.csv")
    ap.add_argument("--out", default="data/did_results.csv")
    ap.add_argument("--treat", default="ban",
                    choices=["ban", "full_ban", "scope1"])
    ap.add_argument("--outcome", default="pm25_d1",
                    choices=["pm25_d1", "pm25_win", "spike_increment", "pm25_base", "spike_ratio"],
                    help="pm25_base（除夕前 7—2 日）是**安慰剂结果变量**：燃放管制不该"
                         "改变年前基线，若它在切换当期也出现大系数，说明估计量在捡拾"
                         "城市自身的趋势，而非政策效应")
    ap.add_argument("--min-year", type=int, default=0,
                    help="只用该年及以后的观测（默认自动取处理城市首条记录的年份）")
    ap.add_argument("--no-truncate", action="store_true",
                    help="关闭窗口截断。首记录晚于样本起点的城市会出现假切换，"
                         "**仅供诊断**，不要用它报告结果")
    ap.add_argument("--policy", default="policy/policy.csv",
                    help="用于建立城市→省份映射（同省对照需要）")
    ap.add_argument("--same-province", action="store_true",
                    help="对照组只取与处理城市同省的未变动城市。可吸掉区域共同冲击，"
                         "但要求该省有未变动的对照城市")
    ap.add_argument("--prov-year-fe", action="store_true",
                    help="TWFE 用「城市 + 省份×年份」固定效应代替「城市 + 年份」。"
                         "省份×年份固定效应是 --same-province 在回归里的对应物，"
                         "能吸掉各省自己的年际波动（安慰剂检验显示这一项很大）。"
                         "注意：省级统一政策的城市在此设定下**无对照可用**，会被吸收掉")
    args = ap.parse_args()
    # 默认参数是相对路径；从项目目录之外运行会解析到错误位置，甚至抛 FileNotFoundError
    # 而报错信息看不出是路径问题。统一以仓库根目录为基准；绝对路径不受影响。
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    # 一次假的 0→1 切换（河南各市会假切换于 2020、山西各市于 2021）。
    #
    # ⚠️ 已知代价（两次独立复核都点到）：这是**全局**截断，由山西的省级记录起始年
    #    （2021）决定，会让河南白丢一年前置期。更正确的做法是**按城市各自截断**，
    #    但那要求平衡筛查与 DCDH 循环都改成"按各城可用年份"，且恢复出来的
    #    2020 前置期本身被新冠污染（2020 春节初一 = 2020-01-25，武汉封城后第 2 天），
    #    故暂不实现，列为待办。用 --no-truncate 可关闭截断（会引入假切换，仅供诊断）。
    first_ban = {}
    for r in raw:
        if (r.get("policy_type") or "").strip() == "3":
            c = r["city"]
            first_ban[c] = min(first_ban.get(c, 10 ** 9), int(r["cny_year"]))
    if args.no_truncate:
        min_year = 0
        print("⚠️ --no-truncate：已关闭窗口截断。首记录晚于样本起点的城市会出现"
              "「首次入记录」被误当 0→1 假切换，结果仅供诊断。")
    else:
        min_year = args.min_year or (max(first_ban.values()) if first_ban else 0)
    recs = [r for r in recs if r["_year"] >= min_year]
    drv = sorted(c for c, y in first_ban.items() if y == min_year)
    print("窗口起点 %d（避免把「首次入记录」误当切换）%s"
          % (min_year,
             "；该值由以下城市的首条禁放记录年决定：%s"
             % "、".join(drv[:11]) if drv and not args.no_truncate else ""))

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
    prov = province_map(args.policy, units)
    n_prov = len({prov[c] for c in units if c in prov})
    print("省份映射覆盖 %d 城（%d 个省/市）；同省对照模式：%s"
          % (len(prov), n_prov, "开" if args.same_province else "关"))

    def ctrl_change(city, t0, t1, stay):
        """该城市的对照组平均变化。--same-province 时只取同省未变动城市。"""
        dy = lambda c: idx[(c, t1)]["_y"] - idx[(c, t0)]["_y"]
        if args.same_province:
            pv_ = prov.get(city)
            pool = [s for s in stay if prov.get(s) == pv_] if pv_ else []
            if not pool:
                return None
        else:
            pool = stay
        return st.mean([dy(c) for c in pool]) if pool else None

    events = []
    for t0, t1 in zip(years, years[1:]):
        ins = [c for c in units if idx[(c, t0)]["_d"] == 0 and idx[(c, t1)]["_d"] == 1]
        outs = [c for c in units if idx[(c, t0)]["_d"] == 1 and idx[(c, t1)]["_d"] == 0]
        stay = [c for c in units if idx[(c, t0)]["_d"] == idx[(c, t1)]["_d"]]
        if not ins and not outs:
            continue
        dy = lambda c: idx[(c, t1)]["_y"] - idx[(c, t0)]["_y"]

        def eff(group, sign):
            """逐城与其对照组比，再平均；返回 (估计, 用上的城市数)。"""
            ests = []
            for c in group:
                cb = ctrl_change(c, t0, t1, stay)
                if cb is not None:
                    ests.append(sign * (dy(c) - cb))
            return (st.mean(ests) if ests else None, len(ests))

        # 对照组口径的平均变化必须与 eff() 实际使用的对照同口径，否则同一段输出里
        # "对照均值"与"效应"对不上账（同省模式下会报出全体城市的均值）。
        if args.same_province:
            used = [ctrl_change(c, t0, t1, stay) for c in (ins + outs)]
            used = [v for v in used if v is not None]
            base = st.mean(used) if used else None
            base_note = "同省对照（%d 个切换城的同省对照均值之平均）" % len(used)
        else:
            base = st.mean([dy(c) for c in stay]) if stay else None
            base_note = "全体未变动城市（%d 城）" % len(stay)
        e_in, n_iu = eff(ins, +1)
        e_out, n_ou = eff(outs, -1)
        events.append({"period": "%d→%d" % (t0, t1), "n_in": n_iu, "n_out": n_ou,
                       "n_stay": len(stay),
                       "ctrl_change": round(base, 2) if base is not None else "",
                       "est_in": round(e_in, 2) if e_in is not None else "",
                       "est_out": round(e_out, 2) if e_out is not None else ""})
        print("\n[%d→%d] 进入处理 %d 城（可用 %d），退出处理 %d 城（可用 %d），"
              "本期未变动 %d 城"
              % (t0, t1, len(ins), n_iu, len(outs), n_ou, len(stay)))
        print("   对照组平均变化 %s；进入处理的效应 %s；退出处理的效应 %s"
              % ("%+.2f" % base if base is not None else "—",
                 "%+.2f" % e_in if e_in is not None else "—",
                 "%+.2f" % e_out if e_out is not None else "—"))
        print("   （对照口径：%s）" % base_note)
        if ins:
            print("   进入的城市：%s" % "、".join(ins[:12]))
        if outs:
            print("   退出的城市：%s" % "、".join(outs[:12]))

    # ---------- 事件路径：平行趋势的安慰剂证据 ----------
    # 把"在窗口内发生过切换"的城市与"始终未切换"的城市逐期对比。切换之前的期对
    # 若已显示系统性差异，平行趋势就不成立；那时主估计不可信。
    # ⚠️ 必须**按批次分开**画路径。把不同切换年份的城市混成一组，事件前后的路径会
    # 互相抵消——山西的 2026 效应会被河南 2023 已切换后的走势冲淡。
    # 批次 = 同一相对期发生切换的城市集合；方向（进/退处理）也要记下来，否则读路径
    # 的人会把"退出处理"的符号读反——本项目的两个批次**都是退出处理**（禁改限）。
    cohorts = defaultdict(set)
    cohort_dir = defaultdict(set)
    for t0, t1 in zip(years, years[1:]):
        for c in units:
            a, b = idx[(c, t0)]["_d"], idx[(c, t1)]["_d"]
            if a != b:
                cohorts[t1].add(c)
                cohort_dir[t1].add("进" if b == 1 else "退")
    switchers = set().union(*cohorts.values()) if cohorts else set()
    never = [c for c in units if c not in switchers]
    dy_all = lambda c, t0, t1: idx[(c, t1)]["_y"] - idx[(c, t0)]["_y"]
    print("\n=== 按批次的事件路径（相对切换年为 0；切换前各期就是平行趋势的安慰剂）===")
    print("  路径是**原始差**（处理组变化 − 对照组变化），未按处理方向翻符号。")
    print("  因此：批次为「退出处理」时，正值 = 放开后相对对照**上升**（即禁令原本在压低浓度）；")
    print("  批次为「进入处理」时含义相反。当期系数与上文 est_in/est_out 差一个负号。")
    for g in sorted(cohorts):
        grp = sorted(cohorts[g])
        dirn = "/".join(sorted(cohort_dir[g]))
        print("\n批次 %d（%d 城，方向：%s处理）：%s"
              % (g, len(grp), dirn, "、".join(grp[:12])))
        for t0, t1 in zip(years, years[1:]):
            ests = []
            for c in grp:
                cb = ctrl_change(c, t0, t1, never)
                if cb is not None:
                    ests.append(dy_all(c, t0, t1) - cb)
            if not ests:
                continue
            rel = t1 - g
            tag = "← 切换当期" if rel == 0 else ("切换前，安慰剂" if rel < 0 else "切换后")
            print("  相对期 %+d（%d→%d）  %+7.2f   %s"
                  % (rel, t0, t1, st.mean(ests), tag))
        if not any(ctrl_change(c, g - 1, g, never) is not None for c in grp) and g - 1 in years:
            print("   （该批次在本对照口径下无可用对照城市，故无路径——"
                  "若为同省对照模式，通常因该省城市全在处理组内）")
            continue
        # 逐城贡献：结论是否被单一城市驱动，必须看清楚
        per = []
        for c in grp:
            cb = ctrl_change(c, g - 1, g, never)
            if cb is not None:
                per.append((dy_all(c, g - 1, g) - cb, c))
        if per:
            per.sort()
            print("   切换当期逐城（与对照之差）："
                  + "；".join("%s %+.1f" % (c, v) for v, c in per))

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
    if args.prov_year_fe:
        noprov = [c for c in units if c not in prov]
        pt = [prov.get(r["city"], "_缺省") + "|" + str(r["_year"]) for r in recs]
        beta, se, G, n_eff = fe_cluster(y, d, [us, pt], us)
        spec = "城市 + 省份×年份"
        if noprov:
            print("\n   ⚠️ %d 个城市没有省份归属，其省份×年份组记为「_缺省」，"
                  "等于把它们放在同一个伪省份里——请先补 data/city_province.csv"
                  % len(noprov))
    else:
        beta, se, G, n_eff = fe_cluster(y, d, [us, ts], us)
        spec = "城市 + 年份"
    print("\nTWFE 对照（固定效应：%s）：β = %s，聚类标准误 = %s" % (
        spec, "%+.2f" % beta if beta is not None else "—",
        "%.2f" % se if se else "—"))
    print("   聚类数 %d；**有效聚类数 %d**（残差化处理变量非零的城市数）"
          % (G, n_eff))
    if n_eff < G * 0.5:
        print("   ⚠️ 有效聚类数远小于名义聚类数：该设定下 β 只由那 %d 个城市识别，"
              "其余 %d 城的残差化处理变量恒为 0，对 β 与标准误的贡献都是 0。"
              "按 G=%d 校正标准误会偏小（实测约小 3%%）。"
              % (n_eff, G - n_eff, n_eff))
    print("   ⚠️ 标准误口径：此处只乘 CR1 的 G/(G-1)。若按 Stata/`reghdfe` 默认再乘"
          " (N-1)/(N-K)，(N=%d) 会更大 10%%–17%%。两种约定都要报。" % len(y))
    print("   注：本行**不受 --same-province 影响**，它始终用全部样本；"
          "换设定请用 --prov-year-fe。")
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
