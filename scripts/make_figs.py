#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成论文配图（英文标注；本机无 CJK 字体，中文会变方框）

每张图论证一个观点：

Fig 1  春节窗口的事件研究剖面
       (a) PM2.5 日均值随相对日的变化，分「早期 2015–2019」「近期 2022–2026」
           → 尖峰陡峭且位置精确地落在正月初一（rel_day = +1）；水平值整体
             下降是全国治污趋势，故识别只能来自城市间差异
       (b) 四污染物指数化剖面（rel_day = -7 记为 100）
           → 机制/安慰剂：PM2.5 与 SO2 在初一尖峰，NO2 反向下降（假期停产停驶），
             O3 平坦 ⇒ 尖峰不是交通或气象造成的

Fig 2  除夕午后至初一清晨的逐小时 PM2.5（五城）
       (a) 绝对水平；(b) 按各城自身除夕午后基线归一化
           → 尖峰在跨零点前后爆发，形态各城一致、幅度差异极大
           注意：本图基线是「小时值」，故倍数远大于 Fig 3 的「日均值」口径

Fig 3  城市层面的异质性（308 个平衡面板城市）
       (a) 尖峰倍数 vs 基线浓度；(b) 绝对增量 vs 基线浓度
           → 两关系都很弱（|r| ≈ 0.21–0.24），说明「扩散条件梯度」不足以解释
             城市间差异；变异极大（增量 −11 至 +191 μg/m³），留待政策变量解释

用法
----
  python3 -I make_figs.py            # 出图 + 视觉自检 + 导出
  python3 -I make_figs.py --qa-only  # 只渲染自检，不导出
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 出图使用 SciPilot 技能（期刊样式、视觉自检、灰度预览）。该技能是**本机安装**的，
# 别人克隆本仓库时不一定有，因此做成可选：找不到就退回内置的 matplotlib 样式。
# 需要时可用环境变量指定路径：export SCIPILOT_SKILL=/path/to/scipilot-figure-skill/scripts
SKILL = os.environ.get(
    "SCIPILOT_SKILL",
    os.path.expanduser("~/.claude/skills/scipilot-figure-skill/scripts"))
if os.path.isdir(SKILL) and SKILL not in sys.path:
    sys.path.insert(0, SKILL)
try:
    from setup_style import setup_style
    from export_figure import export_figure
    from visual_qa import render_preview, audit_layout, print_report
    from layout_tools import add_panel_labels
    HAS_SKILL = True
except ImportError:
    HAS_SKILL = False

    def setup_style(journal="general", lang="en", **kw):
        """内置回退：只设置一组可读的字号与 DPI。"""
        plt.rcParams.update({
            "savefig.dpi": 300, "figure.dpi": 300, "font.size": 8,
            "axes.labelsize": 8, "axes.titlesize": 8.5,
            "xtick.labelsize": 7, "ytick.labelsize": 7,
            "legend.fontsize": 6.2, "axes.unicode_minus": False,
        })
        return {"journal": journal, "lang": lang, "fallback": True}

    def export_figure(fig, basename, formats=("pdf", "png"), dpi=300,
                      size_inches=None, grayscale_preview=False, **kw):
        for ext in formats:
            fig.savefig("%s.%s" % (basename, ext), dpi=dpi, bbox_inches="tight")
            print("  [内置回退] 写入 %s.%s" % (basename, ext))

    def render_preview(fig, out_png):
        fig.savefig(out_png, dpi=110, bbox_inches="tight")

    def audit_layout(fig, **kw):
        # 返回非空，使调用方不会误报"自检通过"
        return [("info", "未安装 SciPilot 自检工具，跳过布局检查")]

    def print_report(issues):
        return "  （未安装 SciPilot 自检工具，跳过布局检查——不表示检查通过）"

    def add_panel_labels(fig, style="nature", **kw):
        print("  [内置回退] 未安装 SciPilot，跳过子图编号 (a)/(b)")

REL = list(range(-7, 8))
FOCUS5 = ["武汉", "丹东", "贵阳", "阿克苏地区", "乌鲁木齐"]
CITY_EN = {"武汉": "Wuhan", "丹东": "Dandong", "贵阳": "Guiyang",
           "阿克苏地区": "Aksu", "乌鲁木齐": "Urumqi", "上海": "Shanghai",
           "北京": "Beijing", "拉萨": "Lhasa", "广州": "Guangzhou"}

# 只标注分布在两端、彼此远离的 5 个城市；中间的阿克苏与贵阳留作无标签点
# （其数值见 data/panel_cityday.csv 汇总表，避免在密集散点上堆文字）
LABELED = {"武汉", "丹东", "上海", "乌鲁木齐", "拉萨"}
LBL_OFFSET = {"丹东": (-20, 7), "上海": (7, -11), "武汉": (9, 7),
              "乌鲁木齐": (6, 9), "拉萨": (7, 6)}


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return np.nan


def load(data_dir):
    bal = {r["city"] for r in csv.DictReader(
        open(os.path.join(data_dir, "coverage_city_year.csv"), encoding="utf-8-sig"))
        if r["in_balanced"] == "Y"}
    rows = list(csv.DictReader(
        open(os.path.join(data_dir, "panel_cityday.csv"), encoding="utf-8-sig")))
    return bal, rows


def series(rows, bal, col, subset=lambda y: True, rels=REL):
    buckets = defaultdict(list)
    for r in rows:
        if r["city"] not in bal or not subset(int(r["cny_year"])):
            continue
        v = fnum(r[col])
        if not np.isnan(v):
            buckets[int(r["rel_day"])].append(v)
    xs, ms, ses, ns = [], [], [], []
    for rel in rels:
        a = np.array(buckets.get(rel, []))
        if a.size == 0:
            continue
        xs.append(rel)
        ms.append(a.mean())
        ses.append(a.std(ddof=1) / np.sqrt(a.size) if a.size > 1 else 0.0)
        ns.append(a.size)
    return np.array(xs), np.array(ms), np.array(ses), ns


def fig1(rows, bal):
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9))
    ax = axes[0]
    eras = [((2015, 2019), "#0072B2", "o", "-", "2015-2019"),
            ((2022, 2026), "#D55E00", "s", "--", "2022-2026")]
    ymax = 0
    for (y0, y1), color, mk, ls, lab in eras:
        x, m, se, ns = series(rows, bal, "pm25", lambda y: y0 <= y <= y1)
        ax.fill_between(x, m - se, m + se, color=color, alpha=0.18, lw=0)
        ax.plot(x, m, color=color, marker=mk, ls=ls, ms=4, lw=1.5, label=lab)
        # 直接在线端标注，避免图例遮挡峰值（此前图例压住了 2015–2019 的峰）
        ax.annotate(f"{lab}\n(n={ns[0]}/pt)", (x[-1] + 0.25, m[-1]), color=color,
                    fontsize=6.2, va="center", ha="left", annotation_clip=False)
        ymax = max(ymax, float((m + se).max()))
    ax.axvline(1, color="0.55", lw=0.8, ls=":")
    ax.set_xlim(-7.8, 13.2)
    ax.set_ylim(0, ymax * 1.17)
    ax.annotate("New Year's\nDay 1", (1.0, ax.get_ylim()[1] * 0.995), fontsize=6,
                color="0.35", ha="center", va="top")
    ax.set_xlabel("Days relative to Lunar New Year's Eve")
    ax.set_ylabel(r"Daily mean PM$_{2.5}$ ($\mu$g m$^{-3}$)")
    ax.set_title("(a) PM$_{2.5}$ level by era", fontsize=8.5)

    ax = axes[1]
    specs = [("pm25", "#D55E00", "-", "o", r"PM$_{2.5}$"),
             ("so2", "#CC79A7", "--", "^", r"SO$_2$"),
             ("no2", "#0072B2", "-.", "s", r"NO$_2$"),
             ("o3_max", "#009E73", ":", "D", r"O$_3$ max")]
    for col, color, ls, mk, lab in specs:
        x, m, se, ns = series(rows, bal, col)
        idx = m / m[0] * 100.0
        ax.fill_between(x, idx - se / m[0] * 100, idx + se / m[0] * 100,
                        color=color, alpha=0.15, lw=0)
        ax.plot(x, idx, color=color, marker=mk, ls=ls, ms=3.5, lw=1.5, label=lab)
    ax.axhline(100, color="0.75", lw=0.7)
    ax.axvline(1, color="0.55", lw=0.8, ls=":")
    ax.set_xlabel("Days relative to Lunar New Year's Eve")
    ax.set_ylabel("Index (day -7 = 100)")
    ax.set_title("(b) Pollutant profile, indexed", fontsize=8.5)
    ax.legend(fontsize=6.2, frameon=False, ncol=2, loc="lower left")
    add_panel_labels(fig, style="nature")
    return fig


def fig2(data_dir):
    raw = defaultdict(lambda: defaultdict(list))
    with open(os.path.join(data_dir, "panel_hourly_focus.csv"),
              encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["city"] not in FOCUS5 or r["pollutant"] != "PM2.5":
                continue
            rd, h = int(r["rel_day"]), int(r["hour"])
            if rd == 0 and 12 <= h <= 23:
                x = h - 24
            elif rd == 1 and 0 <= h <= 6:
                x = h
            else:
                continue
            v = fnum(r["value"])
            if not np.isnan(v):
                raw[r["city"]][x].append(v)

    xs = list(range(-12, 7))
    colors = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00"]
    marks = ["o", "s", "^", "D", "v"]
    lstyles = ["-", "--", "-.", ":", (0, (3, 1, 1, 1))]

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.0))
    for ax, norm in zip(axes, [False, True]):
        for city, c, mk, ls in zip(FOCUS5, colors, marks, lstyles):
            base = None
            if norm:
                b = [np.mean(raw[city][k]) for k in (-12, -11, -10) if raw[city].get(k)]
                base = float(np.mean(b)) if b else None
            xs_, ms, ses = [], [], []
            for x in xs:
                a = raw[city].get(x)
                if not a:
                    continue
                m = float(np.mean(a))
                if norm:
                    if not base:
                        continue
                    m = m / base * 100.0
                xs_.append(x)
                ms.append(m)
                ses.append(float(np.std(a, ddof=1) / np.sqrt(len(a))) if len(a) > 1 else 0.0)
            if not xs_:
                continue
            xs_, ms, ses = np.array(xs_), np.array(ms), np.array(ses)
            ax.fill_between(xs_, ms - ses, ms + ses, color=c, alpha=0.15, lw=0)
            ax.plot(xs_, ms, color=c, marker=mk, ls=ls, ms=3.2, lw=1.5,
                    label=CITY_EN[city])
        ax.axvline(0, color="0.35", lw=0.9, ls=":")
        ax.set_xlabel("Hours from midnight")          # 短标签，避免与相邻子图撞车
        ax.set_xticks([-12, -8, -4, 0, 4])
    axes[0].set_ylabel(r"PM$_{2.5}$ ($\mu$g m$^{-3}$)")
    axes[0].set_title("(a) Absolute level", fontsize=8.5)
    axes[1].set_ylabel("Index (hour 12:00-14:00 = 100)")
    axes[1].set_title("(b) Normalised to own afternoon baseline", fontsize=8.5)
    axes[1].legend(fontsize=6.0, frameon=False, ncol=2, loc="upper left")
    # 窗口说明放图注，不放在图内（放图内会与两子图的 x 轴标签叠压）
    add_panel_labels(fig, style="nature")
    return fig


def fig3(rows, bal):
    peak, base = defaultdict(list), defaultdict(list)
    for r in rows:
        c = r["city"]
        if c not in bal:
            continue
        v = fnum(r["pm25"])
        if np.isnan(v):
            continue
        rel = int(r["rel_day"])
        if rel == 1:
            peak[c].append(v)
        elif -7 <= rel <= -2:
            base[c].append(v)
    names, xs, ratio, delta = [], [], [], []
    for c in peak:
        if c not in base or not peak[c] or not base[c]:
            continue
        b = float(np.mean(base[c]))
        p = float(np.mean(peak[c]))
        if b <= 0:
            continue
        names.append(c)
        xs.append(b)
        ratio.append(p / b)
        delta.append(p - b)
    xs, ratio, delta = np.array(xs), np.array(ratio), np.array(delta)
    hi = [i for i, c in enumerate(names) if c in LABELED]

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.0))
    for ax, ys, ylab, title in [
            (axes[0], ratio, "Spike ratio (Day 1 / baseline)", "(a) Relative spike"),
            (axes[1], delta, r"Increment ($\mu$g m$^{-3}$)", "(b) Absolute increment")]:
        ax.scatter(xs, ys, s=13, facecolor="none", edgecolor="#0072B2",
                   linewidths=0.7, alpha=0.75)
        for i in hi:
            ax.scatter([xs[i]], [ys[i]], s=30, color="#D55E00", zorder=3)
            dx, dy = LBL_OFFSET.get(names[i], (3, 2))
            ax.annotate(CITY_EN[names[i]], (xs[i], ys[i]), fontsize=5.8,
                        xytext=(dx, dy), textcoords="offset points",
                        color="#D55E00")
        if len(xs) > 2:
            z = np.polyfit(xs, ys, 1)
            xr = np.linspace(xs.min(), xs.max(), 50)
            ax.plot(xr, np.polyval(z, xr), color="0.35", lw=1.0, ls="--")
            r = np.corrcoef(xs, ys)[0, 1]
            ax.text(0.97, 0.95, f"r = {r:+.2f}\nn = {len(xs)}", transform=ax.transAxes,
                    fontsize=6.5, ha="right", va="top",
                    bbox=dict(fc="white", ec="none", alpha=0.75, pad=1.5))
        ax.set_xlabel(r"Baseline PM$_{2.5}$, days -7 to -2 ($\mu$g m$^{-3}$)")
        ax.set_ylabel(ylab)
        ax.set_title(title, fontsize=8.5)
    axes[1].axhline(0, color="0.7", lw=0.7)
    add_panel_labels(fig, style="nature")
    return fig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--outdir", default="figs")
    ap.add_argument("--qa-only", action="store_true")
    args = ap.parse_args()

    style = setup_style(journal="general", lang="en")
    print("样式:", style)
    os.makedirs(args.outdir, exist_ok=True)
    bal, rows = load(args.data_dir)
    print("平衡面板 %d 城，面板 %d 行" % (len(bal), len(rows)))

    figs = [("fig1_event_study", fig1(rows, bal)),
            ("fig2_hourly", fig2(args.data_dir)),
            ("fig3_heterogeneity", fig3(rows, bal))]

    for name, fig in figs:
        render_preview(fig, os.path.join(args.outdir, "_preview_%s.png" % name))
        issues = audit_layout(fig)
        print("\n--- %s 自检 ---" % name)
        print(print_report(issues) if issues else "  程序自检通过")
        if not args.qa_only:
            export_figure(fig, basename=os.path.join(args.outdir, name),
                          formats=["pdf", "png"], dpi=300,
                          size_inches=tuple(fig.get_size_inches()),
                          grayscale_preview=True)
        plt.close(fig)
    print("\n完成。预览图: %s/_preview_*.png" % args.outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
