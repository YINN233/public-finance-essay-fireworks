#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从本地归档的原始单日文件构建分析面板（不联网）

输入 : data/raw/china_cities_YYYYMMDD.csv（由 download_aqi.py 生成）
输出 :
  data/panel_cityday.csv        城市 × 日 面板（全城）—— DiD 主用
  data/panel_hourly_focus.csv   聚焦城市 × 日 × 小时 × 污染物 —— 画除夕小时曲线用
  stdout                        覆盖率报告 + 聚焦城市的除夕对照

用法
----
  python3 -I build_panel.py
  python3 -I build_panel.py --focus 武汉 丹东 贵阳 阿克苏地区 乌鲁木齐
  python3 -I build_panel.py --min-hours 18

说明
----
* rel_day = 相对除夕的天数（除夕 = 0，前一 = -1）；cny_year = 该窗口所属的春节年份。
  注意：不要用日历年份 year 分组，用 cny_year。
* 日均值要求当日有效小时数 >= --min-hours（默认 18），否则该城该日不入面板。
* O3 取日内最大值而非均值（臭氧日变化强，均值会掩盖燃放时段的影响）。
* 同时输出 PM2.5/PM10 比值：南疆城市该比值低（粗颗粒/沙尘主导），
  该比值在燃放时段上升，可用于区分沙尘与燃放两种来源。详见 README §1.4。
"""

import argparse
import csv
import glob
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta

CNY_DAY1 = {
    2015: (2, 19), 2016: (2, 8),  2017: (1, 28), 2018: (2, 16),
    2019: (2, 5),  2020: (1, 25), 2021: (2, 12), 2022: (2, 1),
    2023: (1, 22), 2024: (2, 10), 2025: (1, 29), 2026: (2, 17),
}

MEAN_VARS = ["PM2.5", "PM10", "AQI", "SO2", "NO2", "CO"]
MAX_VARS = ["O3_8h", "O3"]
ALL_VARS = MEAN_VARS + MAX_VARS

DEFAULT_FOCUS = ["武汉", "丹东", "贵阳", "阿克苏地区", "乌鲁木齐",
                 "北京", "上海", "广州", "哈尔滨", "拉萨"]

MAX_WINDOW = 15  # 判定窗口的最大绝对天数（默认下载窗口为 ±7）


def cny_eve_map():
    """春节年份 -> 除夕日期（春节前一天）。"""
    return {y: date(y, m, d) - timedelta(days=1) for y, (m, d) in CNY_DAY1.items()}


def rel_and_cny_year(day, eves):
    """返回 (rel_day, cny_year)；rel_day 为相对除夕的天数，找不到返回 (None, None)。"""
    best, best_abs = (None, None), None
    for y, eve in eves.items():
        delta = (day - eve).days
        if abs(delta) <= MAX_WINDOW and (best_abs is None or abs(delta) < best_abs):
            best, best_abs = (delta, y), abs(delta)
    return best


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_file(path):
    """返回 (day, (header, {(pollutant, hour): row}))；失败返回 (None, None)。"""
    m = re.search(r"(\d{8})", os.path.basename(path))
    if not m:
        return None, None
    s = m.group(1)
    day = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 2:
        return None, None
    table = {}
    for r in rows[1:]:
        if len(r) < 3 or r[2] not in ALL_VARS:
            continue
        table[(r[2], r[1])] = r
    return day, (rows[0], table)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default="data/raw")
    ap.add_argument("--out-cityday", default="data/panel_cityday.csv")
    ap.add_argument("--out-hourly", default="data/panel_hourly_focus.csv")
    ap.add_argument("--focus", nargs="*", default=DEFAULT_FOCUS)
    ap.add_argument("--min-hours", type=int, default=18)
    args = ap.parse_args()
    # 默认参数是相对路径；从项目目录之外运行会解析到错误位置，甚至抛 FileNotFoundError
    # 而报错信息看不出是路径问题。统一以仓库根目录为基准；绝对路径不受影响。
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    files = sorted(glob.glob(os.path.join(args.raw_dir, "*china_cities_*.csv")))
    if not files:
        print("!! %s 下没有文件。先运行: python3 -u scripts/download_aqi.py" % args.raw_dir,
              file=sys.stderr)
        return 1

    eves = cny_eve_map()
    print("发现 %d 个原始文件，开始构建面板 ..." % len(files))

    # city -> day -> pollutant -> [hourly values]
    store = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    focus_hourly = []
    city_names, days_seen, unparsed = set(), set(), []
    focus_set = set(args.focus)

    for path in files:
        day, parsed = parse_file(path)
        if day is None:
            unparsed.append(os.path.basename(path))
            continue
        header, table = parsed
        idx = {name: i for i, name in enumerate(header)}
        cities = [c for c in header[3:] if c]
        city_names.update(cities)
        days_seen.add(day)
        rel, cny_year = rel_and_cny_year(day, eves)

        for city in cities:
            ci = idx[city]
            for var in ALL_VARS:
                col = []
                for hour in range(24):
                    row = table.get((var, str(hour)))
                    if row is not None and ci < len(row):
                        v = fnum(row[ci])
                        if v is not None:
                            col.append(v)
                if col:
                    store[city][day][var] = col
                if city in focus_set:
                    for hour in range(24):
                        row = table.get((var, str(hour)))
                        if row is None or ci >= len(row):
                            continue
                        focus_hourly.append({
                            "date": day.isoformat(), "cny_year": cny_year,
                            "rel_day": rel, "hour": hour, "city": city,
                            "pollutant": var, "value": row[ci],
                        })

    print("城市 %d 个，日期 %d 天" % (len(city_names), len(days_seen)))
    if unparsed:
        print("!! %d 个文件无法解析: %s" % (len(unparsed), unparsed[:3]))

    # ---------- 城市 × 日 面板 ----------
    os.makedirs(os.path.dirname(args.out_cityday) or ".", exist_ok=True)
    cols = ["date", "cny_year", "rel_day", "city", "n_hours",
            "pm25", "pm10", "ratio_pm25_pm10", "aqi", "so2", "no2", "co", "o3_max"]
    n_rows, n_dropped = 0, 0
    with open(args.out_cityday, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for city in sorted(store):
            for day in sorted(store[city]):
                d = store[city][day]
                pm25 = [v for v in d.get("PM2.5", []) if v is not None]
                if len(pm25) < args.min_hours:
                    n_dropped += 1
                    continue
                rel, cny_year = rel_and_cny_year(day, eves)

                def mean(var):
                    c = [v for v in d.get(var, []) if v is not None]
                    return round(sum(c) / len(c), 1) if len(c) >= args.min_hours else ""

                m25 = sum(pm25) / len(pm25)
                pm10 = [v for v in d.get("PM10", []) if v is not None]
                m10 = sum(pm10) / len(pm10) if pm10 else None
                o3 = [v for v in (d.get("O3_8h") or d.get("O3") or []) if v is not None]

                w.writerow([day.isoformat(), cny_year, rel, city, len(pm25),
                            round(m25, 1), round(m10, 1) if m10 else "",
                            round(m25 / m10, 3) if m10 else "",
                            mean("AQI"), mean("SO2"), mean("NO2"), mean("CO"),
                            round(max(o3), 1) if o3 else ""])
                n_rows += 1
    print("写入 %s（%d 行；因有效小时不足丢弃 %d 个城-日）"
          % (args.out_cityday, n_rows, n_dropped))

    # ---------- 聚焦城市逐小时 ----------
    if focus_hourly:
        os.makedirs(os.path.dirname(args.out_hourly) or ".", exist_ok=True)
        fcols = ["date", "cny_year", "rel_day", "hour", "city", "pollutant", "value"]
        with open(args.out_hourly, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=fcols)
            w.writeheader()
            w.writerows(focus_hourly)
        print("写入 %s（%d 行）" % (args.out_hourly, len(focus_hourly)))

    # ---------- 聚焦城市：除夕当日（rel_day = 0）对照 ----------
    # 注意：尖峰在正月初一（rel_day = +1），不在除夕（0）——见 README §1.5
    print("\n=== 聚焦城市 · 正月初一（rel_day=+1），跨年份均值 ===")
    print("%-12s %5s %8s %8s %8s %8s" % ("城市", "年份数", "PM2.5", "PM10", "比值", "NO2"))
    for city in args.focus:
        if city not in store:
            print("%-12s   (数据中无此城市)" % city)
            continue
        rows = []
        for day, d in store[city].items():
            rel, _ = rel_and_cny_year(day, eves)
            if rel != 1:          # 初一为尖峰日；改回 0 会取到被稀释的除夕日均
                continue
            pm = [v for v in d.get("PM2.5", []) if v is not None]
            if len(pm) < args.min_hours:
                continue
            pm10 = [v for v in d.get("PM10", []) if v is not None]
            no2 = [v for v in d.get("NO2", []) if v is not None]
            rows.append((sum(pm) / len(pm),
                         sum(pm10) / len(pm10) if pm10 else None,
                         sum(no2) / len(no2) if no2 else None))
        if not rows:
            print("%-12s   (无除夕数据)" % city)
            continue
        def col_avg(i):
            c = [r[i] for r in rows if r[i] is not None]
            return sum(c) / len(c) if c else 0.0
        p, p10, no2 = col_avg(0), col_avg(1), col_avg(2)
        print("%-12s %5d %8.1f %8.1f %8.2f %8.1f"
              % (city, len(rows), p, p10, (p / p10) if p10 else 0, no2))

    print("\n完成。下一步：用 panel_cityday.csv 跑事件研究/DiD。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
