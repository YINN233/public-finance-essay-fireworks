#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
精确随机化推断：省内的「哪几个城市改了政策」是不是随机分配的？

为什么需要这个脚本
------------------
本项目的切换城市只有十几个。在这种样本量下，聚类标准误给出的 t 值**不可信**——
它衡量的是「模型设定正确时的抽样不确定性」，而模型设定本身（平行趋势）恰恰是被
质疑的那一条。安慰剂期系数与"效应"同量级，就是设定错误的直接证据。

随机化推断绕开这个问题：**不去估标准误，而是直接问"如果政策是随机分配给省内的
任意几个城市，我们观察到这么大的系数有多罕见"。**

为什么能穷举
------------
河南 17 个城市在面板里，其中 5 个在 2023 年由禁放改为限放。C(17,5) = 6188，
可以直接**全部枚举**，得到的是精确分布而非抽样近似。

⚠️ 解读边界（务必写进论文）
--------------------------
随机化推断检验的是「观测分配相对于省内随机分配有多极端」，**它检验的不是平行趋势**。
若那 5 个城市本来就走在下行/上行趋势上（政策内生），随机化推断仍会给出很小的 p 值。
因此它必须与前缀安慰剂期（`run_did.py` 的事件路径）**一起**报告：
前者说"不像随机分配"，后者说"趋势本来就不平行"。两个都过，结论才站得住。

用法
----
  python3 -I rand_inference.py --province 河南 --year 2023
  python3 -I rand_inference.py --province 河南 --year 2023 --outcome spike_increment
  python3 -I rand_inference.py --province 河南 --year 2023 --placebo-year 2022

输出
----
  stdout                    观测统计量、精确 p 值、分布的若干分位点
  data/rand_inference.csv   每个组合的统计量（供画图）
"""

import argparse
import csv
import itertools
import os
import random
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from merge_policy import PROVINCE_CITIES   # noqa: E402

# 需要检查的省份缺省成员表（用于判断"省内哪些城市在面板里"）
MAX_ENUM = 300000      # 组合数超过此值就改为随机抽样，避免卡死


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/panel_cityyear.csv")
    ap.add_argument("--province", required=True, help="如 河南")
    ap.add_argument("--year", type=int, required=True,
                    help="切换年（春节年份口径）；比较的是 (year-1) → year")
    ap.add_argument("--outcome", default="pm25_d1",
                    choices=["pm25_d1", "pm25_win", "spike_increment", "pm25_base"])
    ap.add_argument("--placebo-year", type=int, default=0,
                    help="把统计量改在这一次（无政策变动的）转移上计算，用来测检验"
                         "自身的假阳性率。不填则用 --year 指定的那次")
    ap.add_argument("--treat", default="ban", choices=["ban", "full_ban", "scope1"])
    ap.add_argument("--draws", type=int, default=20000,
                    help="组合数过多时的随机抽样次数")
    ap.add_argument("--out", default="data/rand_inference.csv")
    args = ap.parse_args()
    # 默认参数是相对路径；从项目目录之外运行会解析到错误位置，甚至抛 FileNotFoundError
    # 而报错信息看不出是路径问题。统一以仓库根目录为基准；绝对路径不受影响。
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    rows = list(csv.DictReader(open(args.inp, encoding="utf-8-sig")))
    members = set(PROVINCE_CITIES.get(args.province, []))
    prov_rows = [r for r in rows if r["city"] in members]
    cities = sorted({r["city"] for r in prov_rows})
    if len(cities) < 3:
        print("!! 省份 %s 在面板里只有 %d 个城市，无法做省内随机化推断"
              % (args.province, len(cities)), file=sys.stderr)
        return 1

    idx = {(r["city"], int(r["cny_year"])): r for r in prov_rows}
    # 处理组的定义期（政策真正变动的那一次转移）
    s0, s1 = args.year - 1, args.year
    # 统计量的计算期：默认就是变动期；--placebo-year 把它挪到一次没有政策变动的转移
    if args.placebo_year:
        t0, t1 = args.placebo_year - 1, args.placebo_year
    else:
        t0, t1 = s0, s1
    for y in (s0, s1, t0, t1):
        want = [c for c in cities if (c, y) not in idx]
        if want:
            # 逐城检查年份完整性：只查第一个城市会让其余城市缺年时在下游抛 KeyError
            print("!! 面板缺少 %d 年数据的有 %d 个城市：%s"
                  % (y, len(want), "、".join(want[:8])), file=sys.stderr)
            return 1

    def ptype(c, y):
        return (idx[(c, y)].get("policy_type") or "").strip()

    # 实际处理组：在 s0→s1 之间由禁放（3）转为非禁放。**安慰剂模式下不变**——
    # 保持 k 不变，才能比较两种情形下的假阳性率。
    real = sorted(c for c in cities if ptype(c, s0) == "3" and ptype(c, s1) != "3")
    if args.treat != "ban":
        print("   注：--treat=%s 仅影响处理变量的构造；本脚本的处理组一律按"
              "「policy_type 由 3 转为非 3」定义，以免随机化对象与处理的定义脱节"
              % args.treat)
    if not real:
        print("!! 在 %s 的 %d→%d 转移中找不到「禁放→非禁放」的城市"
              % (args.province, s0, s1), file=sys.stderr)
        return 1
    if args.placebo_year:
        print("【安慰剂模式】处理组仍是那 %d 个真正改过政策的城市，但统计量在"
              "%d→%d 这次**没有政策变动**的转移上计算。" % (len(real), t0, t1))
        print("   这给出的是本检验自身的假阳性率：政策没变时，它多久误报一次。")

    k = len(real)
    dy = {}
    for c in cities:
        a = fnum(idx[(c, t0)].get(args.outcome))
        b = fnum(idx[(c, t1)].get(args.outcome))
        dy[c] = None if (a is None or b is None) else b - a
    usable = [c for c in cities if dy[c] is not None]
    if len(usable) < len(cities):
        print("   注意：%d 个城市因结果变量缺失被剔除" % (len(cities) - len(usable)))
    real = [c for c in real if c in usable]
    k = len(real)          # 可能因缺失而变小，必须重算
    if k == 0:
        print("!! 处理组城市的结果变量全部缺失", file=sys.stderr)
        return 1

    def stat(grp):
        """处理组相对**同省其余城市**的平均变化的差。"""
        other = [c for c in usable if c not in grp]
        if not other:
            return None
        return st.mean([dy[c] for c in grp]) - st.mean([dy[c] for c in other])

    obs = stat(real)
    total = 1
    for i in range(k):
        total = total * (len(usable) - i) // (i + 1)
    print("\n省份 %s；面板内 %d 城，其中处理组 %d 城：" % (args.province, len(usable), k))
    print("   %s" % "、".join(real))
    print("统计量计算期 %d→%d；结果变量 %s" % (t0, t1, args.outcome))
    print("观测统计量 = 处理组平均变化 − 同省其余城市平均变化 = %+.2f μg/m³" % obs)
    print("全部可能分配：C(%d,%d) = %d" % (len(usable), k, total))

    vals = []
    if total <= MAX_ENUM:
        for combo in itertools.combinations(usable, k):
            s = stat(combo)
            if s is not None:
                vals.append(s)
        how = "穷举全部 %d 种分配" % len(vals)
    else:
        rnd = random.Random(20261015)
        seen = set()
        while len(vals) < args.draws:
            combo = tuple(sorted(rnd.sample(usable, k)))
            if combo in seen:
                continue
            seen.add(combo)
            s = stat(combo)
            if s is not None:
                vals.append(s)
        how = "随机抽样 %d 种分配（组合数 %d 过大，未穷举）" % (len(vals), total)
    print("随机化分布：%s" % how)

    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    ge = sum(1 for v in vals if abs(v) >= abs(obs) - 1e-9)
    p = ge / n
    print("\n=== 精确随机化推断 ===")
    print("  |统计量| ≥ |观测值| 的分配占比：%d / %d = %.4f" % (ge, n, p))
    print("  双侧 p 值 = %.4f" % p)
    q = lambda f: vals_sorted[min(n - 1, max(0, int(f * n)))]
    print("  分布分位点：  1%% %+.1f   5%% %+.1f   25%% %+.1f   50%% %+.1f   "
          "75%% %+.1f   95%% %+.1f   99%% %+.1f"
          % (q(.01), q(.05), q(.25), q(.50), q(.75), q(.95), q(.99)))
    mu = st.mean(vals); sd = st.pstdev(vals)
    print("  均值 %+.2f，标准差 %.2f  →  观测值位于 %+.2f 个标准差处"
          % (mu, sd, (obs - mu) / sd if sd else 0))
    print("\n  解读：本检验回答的是「**哪几个城市**改了政策这件事，相对于省内随机"
          "分配有多罕见」。")
    print("  它**不检验平行趋势**——若那 5 城本来就在下行，p 值仍会很小。"
          "必须与 run_did.py 的前缀安慰剂期一起报告。")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["statistic", "is_observed"])
        for v in vals:
            w.writerow(["%.6f" % v, 0])
        w.writerow(["%.6f" % obs, 1])
    print("\n写入 %s（%d 个组合 + 观测值）" % (args.out, n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
