#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取春节窗口的气象数据（ERA5，经 Open-Meteo 存档接口，免注册）。

为什么用这个接口
----------------
边界层高度（BLH）是判断"静稳天气"的关键变量，CDS 的 ERA5 需要注册与排队；
Open-Meteo 的 archive 接口直接提供 ERA5 的逐日统计量，无需密钥，适合课程
项目的一次性抓取。**它不是原始 ERA5 网格，而是按点位插值后的产品**——这一点
必须写进论文的数据说明。

为什么用 daily 而不是 hourly
----------------------------
同样 40 城 × 15 天，hourly 请求约 35 秒，daily 约 2 秒（实测，2026-11-03）。
逐小时数据在本地聚合与接口的逐日统计结果逐值一致（已对北京 2025-01 核对），
所以没有理由付 20 倍的传输代价。

输出
----
data/met_cityday.csv：city, date, ws, temp, dtr, ps, rh
  均为**本地日（Asia/Shanghai）**的日内统计：
    ws    10 m 风速日均值（km/h，分析时换算为 m/s）
    temp  2 m 气温日均值（°C）
    dtr   当日最高与最低气温之差（°C，作边界层发展的粗代理）
    ps    地面气压日均值（hPa）
    rh    相对湿度日均值（%）

时区由接口的 `timezone=Asia/Shanghai` 直接给出，脚本**不做 UTC 偏移运算**。
早先版本手工加 8 小时并用 `d > 28` 做月末回退，会把 1 月 29/30 日错记成
2 月/3 月 1 日——2017、2025 两个春节窗口正好覆盖这两天，故改为由接口给本地时间。

用法
----
    python3 -u -I scripts/fetch_era5.py                     # 全部年份（约 4 分钟）
    python3 -I scripts/fetch_era5.py --year 2024
    python3 -I scripts/fetch_era5.py --city 中山,资阳,大同 --append   # 修补坐标错误
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
API = "https://archive-api.open-meteo.com/v1/archive"
DAILY = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
         "wind_speed_10m_mean", "surface_pressure_mean", "relative_humidity_2m_mean"]
CHUNK = 40          # 每个请求的城市数：40 城约 2 秒，100 城会掉到 50 秒
# 限流有两条：每分钟 600 次、每小时 5000 次，且**按城市数计次**（40 城 = 40 次）。
# 所以间隔必须 ≥ 40×60/600 = 4 秒；取 4.5 秒，等于每分钟约 530 次。
SLEEP = 4.5


FIELDS = ["city", "date", "ws", "temp", "dtr", "ps", "rh"]


def dedupe(path):
    """按 (city, date) 去重，保留后写入的行。修补与断点续抓会留下重复。"""
    with open(path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    seen, keep = set(), []
    for r in reversed(rows):
        k = (r["city"], r["date"])
        if k in seen:
            continue
        seen.add(k)
        keep.append(r)
    keep.reverse()
    if len(keep) != len(rows):
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(keep)
        print("去重：%d → %d 行" % (len(rows), len(keep)))


def load_coords():
    path = os.path.join(ROOT, "data", "city_coords.csv")
    out = []
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            out.append((r["city"], float(r["lat"]), float(r["lon"])))
    return out


def windows():
    """每个春节年份**实际要用到**的日期区间：rel_day −7 … +1。

    分析只用到初一（+1）与节前基线（−7…−2），所以不抓 +2…+7。接口按
    “地点 × 天数”计费，砍掉 6 天等于把配额消耗降四成。
    """
    path = os.path.join(ROOT, "data", "panel_cityday.csv")
    wd = defaultdict(lambda: [None, None])
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            rel = int(r["rel_day"])
            if not (-7 <= rel <= 1):
                continue
            y, d = r["cny_year"], r["date"]
            lo, hi = wd[y]
            if lo is None or d < lo:
                lo = d
            if hi is None or d > hi:
                hi = d
            wd[y] = [lo, hi]
    return dict(wd)


class RateLimited(Exception):
    def __init__(self, retry_after):
        self.retry_after = retry_after
        super().__init__("HTTP 429，%s 秒后可重试" % retry_after)


def fetch(coords, start, end, tries=4):
    """超时可重试；429 说明**小时配额已耗尽**，重试只会更糟，立刻上抛。"""
    q = {
        "latitude": ",".join("%.4f" % c[1] for c in coords),
        "longitude": ",".join("%.4f" % c[2] for c in coords),
        "start_date": start,
        "end_date": end,
        "daily": ",".join(DAILY),
        "timezone": "Asia/Shanghai",
    }
    url = API + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "public-finance-essay/1.0"})
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as fh:
                return json.load(fh)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimited(e.headers.get("Retry-After", "?")) from e
            last = e
            time.sleep(2 * (k + 1))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (k + 1))
    raise last


def parse_daily(payload, city):
    d = payload["daily"]
    out = []
    for i, day in enumerate(d["time"]):
        tmax, tmin = d["temperature_2m_max"][i], d["temperature_2m_min"][i]
        out.append({
            "city": city,
            "date": day,
            "ws": d["wind_speed_10m_mean"][i],
            "temp": d["temperature_2m_mean"][i],
            "dtr": (tmax - tmin) if tmax is not None and tmin is not None else None,
            "ps": d["surface_pressure_mean"][i],
            "rh": d["relative_humidity_2m_mean"][i],
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", default="", help="只抓某一年，默认全部")
    ap.add_argument("--city", default="", help="只抓某几个城市，逗号分隔（用于修补坐标错误）")
    ap.add_argument("--append", action="store_true", help="追加到已有输出，不覆盖")
    ap.add_argument("--resume", action="store_true", help="跳过输出里已完整的年份")
    ap.add_argument("--out", default="data/met_cityday.csv")
    args = ap.parse_args()

    coords = load_coords()
    if args.city:
        want = {c.strip() for c in args.city.split(",") if c.strip()}
        coords = [c for c in coords if c[0] in want]
    wd = windows()
    years = [args.year] if args.year else sorted(wd)
    out = os.path.join(ROOT, args.out)
    mode = "a" if args.append and os.path.exists(out) else "w"
    if args.resume and os.path.exists(out):
        with open(out, encoding="utf-8-sig") as fh:
            have = {r["date"][:4] for r in csv.DictReader(fh)}
        years = [y for y in years if y not in have]
        print("已完成 %d 年，本次补 %d 年：%s"
              % (len(have), len(years), ",".join(years)))
        mode = "a"
    # 追加时不能用 utf-8-sig：它会在追加位置再写一个 BOM
    fh = open(out, mode, encoding="utf-8", newline="")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    if mode == "w":
        w.writeheader()
    failed, n_written, rate_limited, done_years = [], 0, None, 0
    try:
        for y in years:
            start, end = wd[y]
            print("年份 %s：%s — %s，%d 城" % (y, start, end, len(coords)))
            rows = []
            for i in range(0, len(coords), CHUNK):
                chunk = coords[i:i + CHUNK]
                try:
                    payload = fetch(chunk, start, end)
                except RateLimited as e:
                    rate_limited = e
                    break
                except Exception as e:  # noqa: BLE001
                    failed.append((y, i, str(e)))
                    print("  请求失败（%s 年，%d—%d）：%s" % (y, i, i + len(chunk), e),
                          file=sys.stderr)
                    continue
                if isinstance(payload, dict):
                    payload = [payload]
                for c, p in zip(chunk, payload):
                    rows.extend(parse_daily(p, c[0]))
                print("  %3d/%3d" % (min(i + CHUNK, len(coords)), len(coords)))
                time.sleep(SLEEP)
            # 触发配额时整年丢弃，避免留下半年的残缺数据；重跑该年即可
            if rate_limited:
                break
            # 按年落盘：中途中断也不丢已经完整拿到的年份
            w.writerows(rows)
            fh.flush()
            n_written += len(rows)
            done_years += 1
    finally:
        fh.close()

    # 去重必须在**写完之后**：先去掉旧行会把刚追加的行也当成旧的
    if mode == "a":
        dedupe(out)
    print("已写入 %s：%d 行" % (args.out, n_written))
    if rate_limited:
        print("⚠️ 触发小时配额，%s 秒后可重试；已完整拿到 %d/%d 年。"
              % (rate_limited.retry_after, done_years, len(years)), file=sys.stderr)
        return 3
    if failed:
        print("⚠️ %d 个请求最终失败：%s" % (len(failed), failed), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
