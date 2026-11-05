#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检验风速与日温差是不是边界层高度的好代理。

背景
----
主分析用 10 m 风速与日温差作通风代理，因为 BLH 在 12 个窗口里只有 2025、
2026 两个能取到（见 fetch_blh.py）。这两个窗口不够做主分析，但够回答：
**代理与 BLH 有多像？**

三问
----
1. 城市-日层面：BLH 与风速、日温差的相关。
2. 省×年层面：模型实际用的是省均值，所以要看**省均值之间**的相关。
3. 解释力：在 2025—2026 子样本上，BLH 单独、8 个代理变量、两者相加，
   各自解释多少方差。

用法
----
    python3 -I scripts/blh_validation.py --write
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
import run_did as R  # noqa: E402

MET = ["ws", "dtr", "ps", "rh"]


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pearson(x, y):
    n = len(x)
    mx, my = st.mean(x), st.mean(y)
    sx = sum((v - mx) ** 2 for v in x) ** 0.5
    sy = sum((v - my) ** 2 for v in y) ** 0.5
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (sx * sy)


def load():
    met = {}
    with open(os.path.join(ROOT, "data", "met_cityday.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            met[(r["city"], r["date"])] = {k: fnum(r.get(k)) for k in MET}
    blh = {}
    with open(os.path.join(ROOT, "data", "blh_cityday.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            blh[(r["city"], r["date"])] = {"blh_mean": fnum(r["blh_mean"]),
                                           "blh_night": fnum(r["blh_night"])}
    prov = {}
    lines = [l for l in open(os.path.join(ROOT, "data", "city_province.csv"),
                             encoding="utf-8-sig") if not l.startswith("#")]
    for r in csv.DictReader(io.StringIO("".join(lines))):
        prov[r["city"]] = r["province"]

    daily = defaultdict(dict)
    with open(os.path.join(ROOT, "data", "panel_cityday.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            rel = fnum(r.get("rel_day"))
            if rel is not None:
                daily[(r["city"], r["cny_year"])][int(rel)] = r

    rows = []
    with open(os.path.join(ROOT, "data", "panel_cityyear.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["cny_year"] not in ("2025", "2026"):
                continue
            base = fnum(r.get("pm25_base"))
            key = (r["city"], r["cny_year"])
            today = daily.get(key, {}).get(1)
            base_rows = [daily.get(key, {}).get(d) for d in range(-7, -1)]
            if base is None or today is None or any(b is None for b in base_rows):
                continue
            m1 = met.get((r["city"], today["date"]))
            mb = [met.get((r["city"], b["date"])) for b in base_rows]
            b1 = blh.get((r["city"], today["date"]))
            bb = [blh.get((r["city"], b["date"])) for b in base_rows]
            if not m1 or not b1 or any(x is None for x in mb + bb):
                continue
            row = {"city": r["city"], "year": r["cny_year"],
                   "prov": prov.get(r["city"], "_缺"),
                   "y": fnum(today["pm25"]) - base}
            row["prov_year"] = row["prov"] + "|" + row["year"]
            ok = True
            for k in MET:
                v1, vb = m1.get(k), [x.get(k) for x in mb]
                if v1 is None or any(v is None for v in vb):
                    ok = False
                    break
                row[k + "_d1"] = v1
                row[k + "_base"] = st.mean(vb)
            for k in ("blh_mean", "blh_night"):
                if b1.get(k) is None or any(x.get(k) is None for x in bb):
                    ok = False
                    break
                row[k + "_d1"] = b1[k]
                row[k + "_base"] = st.mean(x[k] for x in bb)
            if ok:
                rows.append(row)
    for r in rows:
        r["ws_d1"] /= 3.6
        r["ws_base"] /= 3.6
    return rows


def ols(y, X):
    k, n = len(X), len(y)
    A = [[sum(X[i][t] * X[j][t] for t in range(n)) for j in range(k)]
         + [sum(X[i][t] * y[t] for t in range(n))] for i in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(A[r][c]))
        if abs(A[p][c]) < 1e-12:
            raise ValueError("设计矩阵奇异")
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


def r2(rows, fe, cols):
    y = [r["y"] for r in rows]
    tot = sum((v - st.mean(y)) ** 2 for v in y)
    yd = R.demean(y, fe)
    if not cols:
        return 1 - sum(v * v for v in yd) / tot
    X = [R.demean([r[c] for r in rows], fe) for c in cols]
    beta, resid = ols(yd, X)
    return 1 - sum(v * v for v in resid) / tot, beta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows = load()
    if not rows:
        print("没有样本。先运行 scripts/fetch_blh.py。", file=sys.stderr)
        return 1
    lines = []

    def say(s=""):
        print(s)
        lines.append(s)

    say("# 风速与日温差是 BLH 的好代理吗？")
    say()
    say("由 `python3 -I scripts/blh_validation.py --write` 生成。**不要手改。**")
    say()
    say("BLH 只在 2025、2026 两个窗口可得；样本 **%d** 个城市-年。" % len(rows))

    # 城市-日层面
    say()
    say("## 一、城市-日层面")
    say()
    say("| 对照 | Pearson $r$ |")
    say("|---|---|")
    for b in ("blh_mean", "blh_night"):
        for w in ("ws_d1", "dtr_d1"):
            say("| %s 与 %s | %.3f |"
                % (b, w, pearson([r[b + "_d1"] for r in rows], [r[w] for r in rows])))
    say()
    say("样本是 %d 个城市-日，但只有 2 年，城市间差异主导相关；下表把省均值单列。" % len(rows))

    # 省×年层面
    grp = defaultdict(list)
    for r in rows:
        grp[r["prov_year"]].append(r)
    py = []
    for g, rs in grp.items():
        py.append({k: st.mean(x[k] for x in rs) for k in
                   ("blh_mean_d1", "blh_night_d1", "ws_d1", "dtr_d1")})
    say()
    say("## 二、省 × 年层面（模型实际使用的口径）")
    say()
    say("$N=%d$ 个省 × 年单元。" % len(py))
    say()
    say("| 对照 | Pearson $r$ |")
    say("|---|---|")
    for b in ("blh_mean_d1", "blh_night_d1"):
        for w in ("ws_d1", "dtr_d1"):
            say("| %s 与 %s | %.3f |"
                % (b, w, pearson([x[b] for x in py], [x[w] for x in py])))

    # 解释力
    city = [r["city"] for r in rows]
    year = [r["year"] for r in rows]
    base = r2(rows, [city, year], [])
    met8 = ["%s_%s" % (k, t) for k in MET for t in ("d1", "base")]
    blh2 = ["blh_night_d1", "blh_night_base"]
    both = met8 + blh2
    say()
    say("## 三、解释力（城市 + 年份 FE，$N=%d$）" % len(rows))
    say()
    say("| 变量集 | 累计 R² | 增量（百分点） |")
    say("|---|---|---|")
    say("| 无 | %.1f%% | — |" % (100 * base))
    for name, cols in [("8 个代理变量", met8), ("BLH（夜间，当日 + 基线）", blh2),
                       ("8 个代理 + BLH", both)]:
        v = r2(rows, [city, year], cols)[0]
        say("| %s | %.1f%% | %.1f |" % (name, 100 * v, 100 * (v - base)))
    say()
    say("注：2 年样本上 8 个回归元的自由度代价约 %.1f 个百分点（$8/304$ 乘残差），"
        % (100 * 8 / 304 * (1 - base)))
    say("所以“8 个代理”的增量有一部分是拟合噪声；BLH 只用了 2 个回归元，可比性更好。")

    say()
    say("## 四、读法")
    say()
    say("· 若 BLH 与风速、日温差的省×年相关很强，代理就是合格的。")
    say("· 若 BLH 单独解释的方差与 8 个代理相当，说明代理抓住了主要信息。")
    say("· 若 BLH 在 8 个代理之上还能加很多，说明代理漏掉了重要维度——")
    say("  正文必须把这写成明确限制，而不是一句“代理不是 BLH 本身”。")

    if args.write:
        out = os.path.join(ROOT, "docs", "结果-BLH校验.md")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print("\n已写入 docs/结果-BLH校验.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
