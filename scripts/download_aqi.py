#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quotsoft.net/air 全国城市空气质量数据：春节窗口下载与整理

数据源主页 : https://quotsoft.net/air/
单日文件   : https://quotsoft.net/air/data/china_cities_YYYYMMDD.csv
             （数据来自中国环境监测总站"全国城市空气质量实时发布平台"）
文件格式   : UTF-8；361 行 × 约 378 列；列 = date,hour,type,<城市名>...
             行 = 24 小时 × 15 种污染物（AQI/PM2.5/PM10/SO2/NO2/O3/CO 及各自 _24h）
起始时间   : 2014-05-13 —— 因此春节窗口从 2015 年开始（2014 年春节不可得）
命名陷阱   : 地区行署城市在数据中名为「阿克苏地区」「喀什地区」，不是「阿克苏市」

用法
----
  python3 -I download_aqi.py --test                  # 只下 2 天，验证通路（约 30 秒）
  python3 -I download_aqi.py --years 2015 2016       # 指定年份
  python3 -I download_aqi.py                         # 全部 12 个窗口（约 180 文件，30-60 分钟）
  python3 -I download_aqi.py --window 7 7            # 除夕前 7 天、后 7 天

输出
----
  data/aqi_cny_window.csv   长表: date, year, rel_day, hour, city, pollutant, value
                            rel_day = 相对除夕的天数（除夕=0，前为负）

注意：本脚本会限速（每次请求间隔 1.5 秒）并自动重试 3 次；旧年份文件（2019 以前）单文件可能耗时约 20 秒。
"""

import argparse
import csv
import io
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "https://quotsoft.net/air/data/china_cities_{d}.csv"
UA = {"User-Agent": "Mozilla/5.0 (academic course project; contact via course TA)"}

# 农历正月初一（春节）的公历日期；除夕 = 前一天
CNY_DAY1 = {
    2015: (2, 19), 2016: (2, 8),  2017: (1, 28), 2018: (2, 16),
    2019: (2, 5),  2020: (1, 25), 2021: (2, 12), 2022: (2, 1),
    2023: (1, 22), 2024: (2, 10), 2025: (1, 29), 2026: (2, 17),
}

POLLUTANTS = ["AQI", "PM2.5", "PM10", "SO2", "NO2", "O3", "CO"]

DEFAULT_CITIES = ["武汉", "丹东", "贵阳", "阿克苏地区", "乌鲁木齐", "北京", "上海", "广州"]


def cny_eve(year):
    """返回该年除夕（春节前一天）的 date。"""
    m, d = CNY_DAY1[year]
    return date(year, m, d) - timedelta(days=1)


def fetch(day, retries=3):
    url = BASE.format(d=day.strftime("%Y%m%d"))
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == retries - 1:
                print("    !! 失败 %s: %s" % (day, exc), file=sys.stderr)
                return None
            time.sleep(4 * (attempt + 1))
    return None


def parse(text, day, cities):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], []
    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    keep = [c for c in cities if c in idx]
    missing = [c for c in cities if c not in idx]
    out = []
    for row in rows[1:]:
        if len(row) < 3 or row[2] not in POLLUTANTS:
            continue
        hour = row[1]
        for city in keep:
            i = idx[city]
            out.append({
                "date": day.isoformat(),
                "hour": hour,
                "city": city,
                "pollutant": row[2],
                "value": row[i] if i < len(row) else "",
            })
    return out, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=sorted(CNY_DAY1))
    ap.add_argument("--cities", nargs="*", default=DEFAULT_CITIES)
    ap.add_argument("--window", nargs=2, type=int, default=[7, 7],
                    metavar=("BEFORE", "AFTER"), help="除夕前后天数，默认 7 7")
    ap.add_argument("--out", default="data/aqi_cny_window.csv")
    ap.add_argument("--test", action="store_true", help="只下 2 天并打印，不写文件")
    args = ap.parse_args()

    before, after = args.window
    days = []
    for y in args.years:
        if y not in CNY_DAY1:
            print("!! 未收录年份 %d，跳过" % y, file=sys.stderr)
            continue
        eve = cny_eve(y)
        for off in range(-before, after + 1):
            days.append((eve + timedelta(days=off), y, off))
    days.sort()

    if args.test:
        days = days[:2]

    print("计划下载 %d 个文件（%d 个春节窗口 × %d 天）"
          % (len(days), len(args.years), before + after + 1))
    print("目标城市: %s" % "、".join(args.cities))

    records = []
    all_missing = set()
    for n, (day, year, off) in enumerate(days, 1):
        sys.stdout.write("[%3d/%3d] %s (rel_day=%+d) ... " % (n, len(days), day, off))
        sys.stdout.flush()
        text = fetch(day)
        if text is None:
            print("跳过")
            continue
        rows, missing = parse(text, day, args.cities)
        all_missing.update(missing)
        for r in rows:
            r["year"] = year
            r["rel_day"] = off
        records.extend(rows)
        print("%d 条" % len(rows))
        time.sleep(1.5)

    if all_missing:
        print("\n!! 以下城市在数据中不存在，请检查名称: %s" % "、".join(sorted(all_missing)),
              file=sys.stderr)

    if not records:
        print("没有抓到数据。", file=sys.stderr)
        return 1

    if args.test:
        print("\n=== 抽样（前 12 条）===")
        for r in records[:12]:
            print(r)
        return 0

    cols = ["date", "year", "rel_day", "hour", "city", "pollutant", "value"]
    outdir = os.path.dirname(args.out)
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        writer.writerows(records)
    print("\n写入 %s（%d 条记录）" % (args.out, len(records)))
    print("下一步：用 pandas/R 按 city × rel_day × hour 透视，即可画除夕小时曲线。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
