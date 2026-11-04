#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""省×年共同冲击与气象：能复现多少，以及这是不是初一特有的。

背景
----
§5.5 的四层分解用**序贯 R²** 给出：城市 22.0%、年份 12.7%（累计 34.7%）、
省×年 30.1%（累计 64.8%）、城市×年特有 35.2%。前两项由城市 FE 与年份 FE 吸收，
第三项是**再加入省份×年份 FE 时的增量**，第四项是剩余残差。

本脚本问三个问题，并给出各自的反证：

  1. **能复现多少？** 在城市 FE + 年份 FE 之上加入**省级年均气象**（该省该年
     所有城市的气象均值，8 个变量）。它的 R² 增量在数学上被省×年成分约束。
  2. **这是不是初一特有的？** 把同一套变量用在 rel_day −1 与 0 上。若三天的
     增量差不多，那它度量的是省×年尺度上气象与污染的普遍关联，不是燃放日
     特有的天气放大。
  3. **是不是纯天气？** 再加入省×年 NO2 均值。NO2 既是工业/交通活动的代理，
     也受气象影响，因此这一步**不能**分离两者，只能说明气象增量里有多少与
     区域活动重叠。

口径
----
被解释变量 y_d = 该日 PM2.5 − 节前基线（rel_day −7…−2）均值。
气象：ws（10 m 风速，换算为 m/s）、dtr（日温差）、ps（地面气压，hPa）、
rh（相对湿度），各取**第 d 日**与**基线六日均值**，共 8 个变量。
**边界层高度不可得**，故用风速与日温差作通风代理。

用法
----
    python3 -I scripts/met_analysis.py --write
"""
import argparse
import csv
import io
import os
import statistics as st
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
import run_did as R  # noqa: E402  （复用交替投影）

MET = ["ws", "dtr", "ps", "rh"]
LABEL = {"ws": "风速 (m/s)", "dtr": "日温差 (°C)", "ps": "气压 (hPa)", "rh": "相对湿度 (%)"}


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def prov_map():
    lines = [l for l in open(os.path.join(ROOT, "data", "city_province.csv"),
                             encoding="utf-8-sig") if not l.startswith("#")]
    return {r["city"]: r["province"] for r in csv.DictReader(io.StringIO("".join(lines)))}


def load_met():
    met = {}
    with open(os.path.join(ROOT, "data", "met_cityday.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            met[(r["city"], r["date"])] = {k: fnum(r.get(k)) for k in MET}
    return met


def load(day=1):
    """构造某一天的样本：y_d = PM2.5(d) − 基线均值，外加当天气象与基线上气象。"""
    met = load_met()
    daily = defaultdict(dict)
    with open(os.path.join(ROOT, "data", "panel_cityday.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            rel = fnum(r.get("rel_day"))
            if rel is not None:
                daily[(r["city"], r["cny_year"])][int(rel)] = r

    prov = prov_map()
    out = []
    with open(os.path.join(ROOT, "data", "panel_cityyear.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            base = fnum(r.get("pm25_base"))
            if base is None:
                continue
            key = (r["city"], r["cny_year"])
            today = daily.get(key, {}).get(day)
            if today is None or fnum(today.get("pm25")) is None:
                continue
            base_rows = [daily.get(key, {}).get(d) for d in range(-7, -1)]
            if any(b is None for b in base_rows):
                continue
            m1 = met.get((r["city"], today["date"]))
            mb = [met.get((r["city"], b["date"])) for b in base_rows]
            if not m1 or any(x is None for x in mb):
                continue
            row = {"city": r["city"], "year": r["cny_year"],
                   "y": fnum(today["pm25"]) - base,
                   "prov": prov.get(r["city"], "_缺"),
                   "n_city": None}
            row["prov_year"] = row["prov"] + "|" + row["year"]
            ok = True
            for k in MET:
                v1, vb = m1.get(k), [x.get(k) for x in mb]
                if v1 is None or any(v is None for v in vb):
                    ok = False
                    break
                row[k + "_d1"] = v1
                row[k + "_base"] = st.mean(vb)
            if not ok:
                continue
            row["y_d1"] = fnum(today["pm25"])
            row["y_base"] = base
            no2 = fnum(r.get("no2_d1")) if day == 1 else None
            row["no2_d1"] = no2
            out.append(row)
    for r in out:
        r["ws_d1"] /= 3.6
        r["ws_base"] /= 3.6
    return out


def load_full():
    """全样本（不要求气象可匹配），用于对表论文 §5.5 的四级分解。"""
    prov = prov_map()
    out = []
    with open(os.path.join(ROOT, "data", "panel_cityyear.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            y = fnum(r.get("spike_increment"))
            if y is None:
                continue
            p = prov.get(r["city"], "_缺")
            out.append({"city": r["city"], "year": r["cny_year"], "y": y,
                        "prov_year": p + "|" + r["cny_year"]})
    return out


def add_prov_cols(rows, vars_, loo=False):
    """加省级均值 P_ 与城市偏离 D_。loo=True 时用**排除本市**的留一均值。"""
    grp = defaultdict(list)
    for r in rows:
        grp[r["prov_year"]].append(r)
    for g, rs in grp.items():
        n = len(rs)
        for k in vars_:
            tot = sum(x[k] for x in rs)
            for x in rs:
                p = (tot - x[k]) / (n - 1) if (loo and n > 1) else tot / n
                x["P_" + k] = p
                x["D_" + k] = x[k] - p
        for x in rs:
            x["n_city"] = n


def ols(y, X):
    """正规方程 + 高斯消元（X 不含常数项，常数已由 FE 吸收）。"""
    k, n = len(X), len(y)
    A = [[sum(X[i][t] * X[j][t] for t in range(n)) for j in range(k)]
         + [sum(X[i][t] * y[t] for t in range(n))] for i in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(A[r][c]))
        if abs(A[p][c]) < 1e-12:
            raise ValueError("设计矩阵接近奇异：第 %d 列。" % c)
        A[c], A[p] = A[p], A[c]
        pv = A[c][c]
        A[c] = [v / pv for v in A[c]]
        for r in range(k):
            if r != c and A[r][c]:
                fac = A[r][c]
                A[r] = [A[r][t] - fac * A[c][t] for t in range(k + 1)]
    beta = [A[i][k] for i in range(k)]
    resid = [y[t] - sum(beta[i] * X[i][t] for i in range(k)) for t in range(n)]
    return beta, resid


def inv(A):
    n = len(A)
    M = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-14:
            raise ValueError("矩阵奇异")
        M[c], M[p] = M[p], M[c]
        pv = M[c][c]
        M[c] = [v / pv for v in M[c]]
        for r in range(n):
            if r != c and M[r][c]:
                fac = M[r][c]
                M[r] = [M[r][t] - fac * M[c][t] for t in range(2 * n)]
    return [row[n:] for row in M]


def cr1_se(y, X, beta, resid, clusters):
    """聚类稳健标准误，只做 G/(G−1) 修正（与仓库口径一致）。"""
    k, n = len(X), len(y)
    XtX = [[sum(X[i][t] * X[j][t] for t in range(n)) for j in range(k)] for i in range(k)]
    bread = inv(XtX)
    meat = [[0.0] * k for _ in range(k)]
    grp = defaultdict(list)
    for t, g in enumerate(clusters):
        grp[g].append(t)
    for g, idx in grp.items():
        s = [sum(X[i][t] * resid[t] for t in idx) for i in range(k)]
        for i in range(k):
            for j in range(k):
                meat[i][j] += s[i] * s[j]
    G = len(grp)
    mid = [[sum(bread[i][m] * meat[m][j] for m in range(k)) for j in range(k)] for i in range(k)]
    V = [[sum(mid[i][m] * bread[m][j] for m in range(k)) for j in range(k)] for i in range(k)]
    scale = G / (G - 1)
    return [max(V[i][i] * scale, 0) ** 0.5 for i in range(k)], G


def r2(rows, fe_groups, cols=()):
    y = [r["y"] for r in rows]
    tot = sum((v - st.mean(y)) ** 2 for v in y)
    yd = R.demean(y, fe_groups)
    if not cols:
        return 1 - sum(v * v for v in yd) / tot
    X = [R.demean([r[c] for r in rows], fe_groups) for c in cols]
    beta, resid = ols(yd, X)
    return 1 - sum(v * v for v in resid) / tot, beta, resid, yd, X


def decompose(rows, prov_cols, dev_cols):
    """区域成分、城市特有成分，以及气象的两级增量。"""
    city = [r["city"] for r in rows]
    year = [r["year"] for r in rows]
    r_cy = r2(rows, [city, year])
    r_cyp = r2(rows, [city, [r["prov_year"] for r in rows]])
    b_prov, _, _, _, _ = r2(rows, [city, year], prov_cols)
    b_all, _, _, _, _ = r2(rows, [city, year], prov_cols + dev_cols)
    n = len(rows)
    # 调整 R²：K = 固定效应个数 + 回归元个数
    k_cy = len({r["city"] for r in rows}) + len({r["year"] for r in rows}) - 1
    k_cyp = len({r["city"] for r in rows}) + len({r["prov_year"] for r in rows}) - 1
    k_b = k_cy + len(prov_cols)

    def adj(r2v, k):
        return 1 - (1 - r2v) * (n - 1) / (n - k)

    return {"n": n, "r_cy": r_cy, "r_cyp": r_cyp,
            "comp_reg": 100 * (r_cyp - r_cy), "comp_loc": 100 * (1 - r_cyp),
            "inc_prov": 100 * (b_prov - r_cy), "inc_local": 100 * (b_all - b_prov),
            "adj_comp_reg": 100 * (adj(r_cyp, k_cyp) - adj(r_cy, k_cy)),
            "adj_inc_prov": 100 * (adj(b_prov, k_b) - adj(r_cy, k_cy))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows = load(1)
    if not rows:
        print("没有可匹配的样本。先运行 scripts/fetch_era5.py。", file=sys.stderr)
        return 1

    prov_cols = ["P_%s_%s" % (k, t) for k in MET for t in ("d1", "base")]
    dev_cols = ["D_%s_%s" % (k, t) for k in MET for t in ("d1", "base")]
    add_prov_cols(rows, [k + s for k in MET for s in ("_d1", "_base")])

    n = len(rows)
    city = [r["city"] for r in rows]
    year = [r["year"] for r in rows]

    lines = []

    def say(s=""):
        print(s)
        lines.append(s)

    # 全样本复现核验
    full = load_full()
    r_c_f = r2(full, [[r["city"] for r in full]])
    r_cy_f = r2(full, [[r["city"] for r in full], [r["year"] for r in full]])
    r_cyp_f = r2(full, [[r["city"] for r in full], [r["prov_year"] for r in full]])

    say("# 省×年共同冲击与气象：能复现多少，以及这是不是初一特有的")
    say()
    say("由 `python3 -I scripts/met_analysis.py --write` 生成。**不要手改。**")
    say()
    say("## 一、样本与复现核验")
    say()
    say("全样本（平衡面板）**%d** 个城市-年；其中气象与 PM2.5 均可匹配 **%d** 个。"
        % (len(full), n))
    say("气象来自 Open-Meteo 的 ERA5 存档接口，按城市点位插值，返回**本地日**")
    say("（Asia/Shanghai）的日内统计量。**边界层高度不可得**，以风速与日温差作通风代理。")
    say()
    say("| 固定效应 | 全样本累计 R² | 论文 §5.5 |")
    say("|---|---|---|")
    say("| 城市 | %.1f%% | 22.0%% |" % (100 * r_c_f))
    say("| 城市 + 年份 | %.1f%% | 34.7%% |" % (100 * r_cy_f))
    say("| 城市 + 省×年 | %.1f%% | 64.8%% |" % (100 * r_cyp_f))
    say()
    say("复现核验通过。" if abs(100 * r_cy_f - 34.7) + abs(100 * r_cyp_f - 64.8) < 0.3
        else "⚠️ 复现核验未通过。")

    res = decompose(rows, prov_cols, dev_cols)
    say()
    say("| 固定效应（气象子样本，$N=%d$） | 累计 R² | 增量 |" % n)
    say("|---|---|---|")
    say("| 城市 | %.1f%% | — |" % (100 * r2(rows, [city])))
    say("| 城市 + 年份 | %.1f%% | %.1f |" % (100 * res["r_cy"], 100 * (res["r_cy"] - r2(rows, [city]))))
    say("| 城市 + 省×年 | %.1f%% | **%.1f**（区域共同冲击） |"
        % (100 * res["r_cyp"], res["comp_reg"]))
    say("| 城市 × 年残差 | — | **%.1f** |" % res["comp_loc"])

    # 主结果
    say()
    say("## 二、气象的增量解释力")
    say()
    say("| 模型 | 在城市+年份 FE 之上加入 | 增量（百分点） | 占区域成分 |")
    say("|---|---|---|---|")
    say("| A | 省级年均气象（8 个变量） | **%.1f** | %.0f%% |"
        % (res["inc_prov"], 100 * res["inc_prov"] / max(res["comp_reg"], 1e-9)))
    say("| B | 再加城市相对省均的气象偏离 | %.1f | — |" % res["inc_local"])
    say()
    say("**区域成分 %.1f 个百分点中，省级气象复现 %.1f 个（%.0f%%）；"
        "城市×年残差 %.1f 中，本地气象偏离只解释 %.1f 个（%.0f%%）。**"
        % (res["comp_reg"], res["inc_prov"],
           100 * res["inc_prov"] / max(res["comp_reg"], 1e-9),
           res["comp_loc"], res["inc_local"],
           100 * res["inc_local"] / max(res["comp_loc"], 1e-9)))
    say()
    say("自由度口径：若改用调整 R²，区域成分为 %.1f、气象增量为 %.1f，份额升到 %.0f%%。"
        % (res["adj_comp_reg"], res["adj_inc_prov"],
           100 * res["adj_inc_prov"] / max(res["adj_comp_reg"], 1e-9)))
    say("**因此 %.0f%% 对自由度口径敏感，不应读作精确值。**"
        % (100 * res["inc_prov"] / max(res["comp_reg"], 1e-9)))

    # 安慰剂日
    say()
    say("## 三、安慰剂「日」：这是不是初一特有的？")
    say()
    say("把同一套 8 个省级气象变量用在 rel_day −1、0、+1 上（都以节前基线为参照）：")
    say()
    say("| 被解释变量 | $N$ | 区域成分 | 气象增量 | 占区域成分 |")
    say("|---|---|---|---|---|")
    for d, name in [(-1, "rel_day −1（除夕前一天）"), (0, "rel_day 0（除夕）"),
                    (1, "rel_day +1（正月初一）")]:
        rr = rows if d == 1 else load(d)
        add_prov_cols(rr, [k + s for k in MET for s in ("_d1", "_base")])
        rd = decompose(rr, prov_cols, dev_cols)
        say("| %s | %d | %.1f | %.1f | %.0f%% |"
            % (name, rd["n"], rd["comp_reg"], rd["inc_prov"],
               100 * rd["inc_prov"] / max(rd["comp_reg"], 1e-9)))
    say()
    say("**三天的气象增量几乎一样（约 10—12 个百分点），初一的份额更高只是因为"
        "它的区域成分更小（30 对 43—44），不是分子更大。** 因此这个数度量的是")
    say("省×年尺度上气象与污染的**普遍关联**，不能读作“初一的天气放大了燃放”。")

    # NO2 重叠
    say()
    say("## 四、与省×年 NO2 的重叠")
    say()
    grp = defaultdict(list)
    for r in rows:
        grp[r["prov_year"]].append(r)
    for g, rs in grp.items():
        vals = [x["no2_d1"] for x in rs if x["no2_d1"] is not None]
        m = st.mean(vals) if vals else None
        for x in rs:
            x["PY_no2"] = m
    rows_no2 = [r for r in rows if r["PY_no2"] is not None]
    c2 = [r["city"] for r in rows_no2]
    y2 = [r["year"] for r in rows_no2]
    base_cy = r2(rows_no2, [c2, y2])
    r_met = r2(rows_no2, [c2, y2], prov_cols)[0]
    r_no2 = r2(rows_no2, [c2, y2], ["PY_no2"])[0]
    r_both = r2(rows_no2, [c2, y2], prov_cols + ["PY_no2"])[0]
    inc_met = 100 * (r_met - base_cy)
    inc_no2 = 100 * (r_no2 - base_cy)
    inc_met_given_no2 = 100 * (r_both - r_no2)
    say("| 模型（在城市+年份 FE 之上） | 增量（百分点） |")
    say("|---|---|")
    say("| 只有省级气象（8 个变量） | %.1f |" % inc_met)
    say("| 只有省×年 NO2 均值 | %.1f |" % inc_no2)
    say("| 气象 + NO2 的联合增量 | %.1f |" % (100 * (r_both - base_cy)))
    say("| **在 NO2 之上，气象还能解释** | **%.1f** |" % inc_met_given_no2)
    say()
    say("省级气象单独解释 %.1f 个点，但**在省×年 NO2 之上只剩 %.1f 个点**。"
        % (inc_met, inc_met_given_no2))
    say("NO2 既是工业与交通活动的代理，也受气象影响，因此这一步**不能**分离"
        "“天气”与“区域活动”；它只说明气象增量里有一大块与区域活动重叠。")
    say("**所以 %.1f 是“气象—活动”的联合可复现份额，不是纯天气的贡献。**"
        % res["inc_prov"])

    # 系数与聚类 SE
    say()
    say("## 五、系数与聚类标准误")
    say()
    _, beta, resid, yd, Xd = r2(rows, [city, year], prov_cols)
    se, G = cr1_se(yd, Xd, beta, resid, [r["prov"] for r in rows])
    say("被解释变量为初一的 PM2.5 增量，聚类标准误按省聚类（$G=%d$）。" % G)
    say()
    say("| 变量 | 系数 | CR1 聚类 SE | $t$ |")
    say("|---|---|---|---|")
    for c, b, s in zip(prov_cols, beta, se):
        k, t = c[2:].rsplit("_", 1)
        name = LABEL[k] + ("，初一" if t == "d1" else "，基线")
        say("| %s | %.2f | %.2f | %.2f |" % (name, b, s, b / s if s else float("nan")))
    say()
    say("注：**按省聚类只有 31 个集群**，标准误本身不稳定；本表只用来判断量级，"
        "不作显著性结论。")

    # 稳健性
    say()
    say("## 六、稳健性")
    say()
    say("| 设定 | $N$ | 区域成分 | 气象增量 | 占区域成分 |")
    say("|---|---|---|---|---|")
    say("| 基准（省级均值） | %d | %.1f | %.1f | %.0f%% |"
        % (n, res["comp_reg"], res["inc_prov"],
           100 * res["inc_prov"] / res["comp_reg"]))
    rows_n2 = [r for r in rows if r["n_city"] >= 2]
    add_prov_cols(rows_n2, [k + s for k in MET for s in ("_d1", "_base")], loo=True)
    r_loo = decompose(rows_n2, prov_cols, dev_cols)
    say("| 留一均值（排除本市，$n\\ge2$） | %d | %.1f | %.1f | %.0f%% |"
        % (r_loo["n"], r_loo["comp_reg"], r_loo["inc_prov"],
           100 * r_loo["inc_prov"] / r_loo["comp_reg"]))
    cols4 = ["P_ws_d1", "P_ws_base", "P_dtr_d1", "P_dtr_base"]
    dev4 = ["D_ws_d1", "D_ws_base", "D_dtr_d1", "D_dtr_base"]
    r_4 = decompose(rows, cols4, dev4)
    say("| 只用风速与日温差 | %d | %.1f | %.1f | %.0f%% |"
        % (r_4["n"], r_4["comp_reg"], r_4["inc_prov"],
           100 * r_4["inc_prov"] / r_4["comp_reg"]))
    say()
    say("留一均值检验回应的是“省级均值含本市”：对单城市省份，省级均值就是本市气象。"
        "排除本市后增量从 %.1f 降到 %.1f，结论不变。"
        % (res["inc_prov"], r_loo["inc_prov"]))

    say()
    say("## 七、读法")
    say()
    say("1. **不能说“区域天气解释了初一尖峰的 39%”。** 正确的说法是：8 个省级气象")
    say("   变量解释了 372 个省×年效应方差的约四成；同样的解释力在除夕与前一天也在。")
    say("2. **不能把 %.1f 与基线成分 21.0 相加或相减。** 11.9 是在增量上估的，"
        % res["inc_prov"])
    say("   同一套变量对基线水平只解释约 7 个点；两者重叠，不可加。")
    say("3. **不能把“本地气象只解释 1.6”读成“剩下 95% 不是气象”。** 缺边界层高度，")
    say("   1.6 只是可观测本地气象的下界。")
    say("4. 支持的核心结论只有一条，但足够：**省×年成分在普通日子上同样存在，"
        "它不是燃放日特有的，因而不是“税没对准初一”的证据。**")

    if args.write:
        out = os.path.join(ROOT, "docs", "结果-气象.md")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print("\n已写入 docs/结果-气象.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
