#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取边界层高度（BLH），只用于**代理有效性检验**。

为什么只有两个窗口
------------------
BLH 在 Open-Meteo 的存档接口（ERA5）上返回全空值；historical-forecast 接口
提供 BLH，但只保留最近约两年。实测：2025-01、2026-02、2024-12 有值，
2024-02 全空。因此 12 个春节窗口里只有 **2025 与 2026** 能取到 BLH。

这两个窗口不够做主分析，但够回答一个关键问题：本文用风速与日温差作通风
代理，**这个代理到底有多像 BLH**？

输出
----
data/blh_cityday.csv：city, date, blh_mean, blh_night
  blh_mean   本地日 24 小时 BLH 均值（m）
  blh_night  本地 18:00—次日 05:00 的均值（m）——燃放集中在夜间，均值会稀释

用法
----
    python3 -u -I scripts/fetch_blh.py
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
API = "https://historical-forecast-api.open-meteo.com/v1/forecast"
CHUNK = 40
SLEEP = 4.5          # 同 fetch_era5：按城市数计次，每分钟不超过 600
NIGHT = {18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5}


def load_coords():
    with open(os.path.join(ROOT, "data", "city_coords.csv"), encoding="utf-8-sig") as fh:
        return [(r["city"], float(r["lat"]), float(r["lon"])) for r in csv.DictReader(fh)]


def windows():
    """每个春节年份的 rel_day −7 … +1 日期区间（与其他气象脚本一致）。"""
    wd = defaultdict(lambda: [None, None])
    with open(os.path.join(ROOT, "data", "panel_cityday.csv"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if not (-7 <= int(r["rel_day"]) <= 1):
                continue
            y, d = r["cny_year"], r["date"]
            lo, hi = wd[y]
            if lo is None or d < lo:
                lo = d
            if hi is None or d > hi:
                hi = d
            wd[y] = [lo, hi]
    return dict(wd)


def fetch(coords, start, end, tries=3):
    q = {"latitude": ",".join("%.4f" % c[1] for c in coords),
         "longitude": ",".join("%.4f" % c[2] for c in coords),
         "start_date": start, "end_date": end,
         "hourly": "boundary_layer_height", "timezone": "Asia/Shanghai"}
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q),
                                 headers={"User-Agent": "public-finance-essay/1.0"})
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as fh:
                return json.load(fh)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RuntimeError("HTTP 429，%s 秒后可重试" % e.headers.get("Retry-After")) from e
            last = e
            time.sleep(2 * (k + 1))
    raise last


def parse(payload, city):
    h = payload["hourly"]
    acc = defaultdict(lambda: {"all": [], "night": []})
    for t, v in zip(h["time"], h["boundary_layer_height"]):
        if v is None:
            continue
        day = t.split("T")[0]
        hour = int(t.split("T")[1][:2])
        acc[day]["all"].append(float(v))
        if hour in NIGHT:
            acc[day]["night"].append(float(v))
    out = []
    for day in sorted(acc):
        a, n = acc[day]["all"], acc[day]["night"]
        out.append({"city": city, "date": day,
                    "blh_mean": sum(a) / len(a) if a else None,
                    "blh_night": sum(n) / len(n) if n else None})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2025,2026", help="BLH 可得的年份")
    ap.add_argument("--out", default="data/blh_cityday.csv")
    args = ap.parse_args()

    coords = load_coords()
    wd = windows()
    years = [y.strip() for y in args.years.split(",") if y.strip()]
    rows, failed = [], []
    for y in years:
        if y not in wd:
            print("没有 %s 的窗口" % y, file=sys.stderr)
            continue
        start, end = wd[y]
        print("年份 %s：%s — %s，%d 城" % (y, start, end, len(coords)))
        for i in range(0, len(coords), CHUNK):
            chunk = coords[i:i + CHUNK]
            try:
                payload = fetch(chunk, start, end)
            except Exception as e:  # noqa: BLE001
                failed.append((y, i, str(e)))
                print("  失败（%s，%d—%d）：%s" % (y, i, i + len(chunk), e), file=sys.stderr)
                continue
            if isinstance(payload, dict):
                payload = [payload]
            for c, p in zip(chunk, payload):
                rows.extend(parse(p, c[0]))
            print("  %3d/%3d" % (min(i + CHUNK, len(coords)), len(coords)))
            time.sleep(SLEEP)

    if not rows:
        print("没有取到数据。", file=sys.stderr)
        return 1
    out = os.path.join(ROOT, args.out)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["city", "date", "blh_mean", "blh_night"])
        w.writeheader()
        w.writerows(rows)
    print("已写入 %s：%d 行，%d 城" % (args.out, len(rows), len({r["city"] for r in rows})))
    if failed:
        print("⚠️ %d 个请求失败" % len(failed), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
