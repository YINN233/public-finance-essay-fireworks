#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quotsoft.net/air 全国城市空气质量数据：春节窗口原始文件下载与归档

设计原则：下载昂贵、变换便宜。
本脚本只负责把原始单日文件抓到本地并归档；城市筛选、面板构建由 build_panel.py
从本地文件完成，无需再次联网。（旧年份文件单文件约 20 秒，全量约 30 分钟。）

数据源主页 : https://quotsoft.net/air/
单日文件   : https://quotsoft.net/air/data/china_cities_YYYYMMDD.csv
             （数据取自中国环境监测总站"全国城市空气质量实时发布平台"）
文件格式   : UTF-8；361 行 × 约 378 列；列 = date,hour,type,<城市名>...
             行 = 24 小时 × 15 种污染物（AQI/PM2.5/PM10/SO2/NO2/O3/CO 及各自 _24h）
起始时间   : 2014-05-13 —— 春节窗口从 2015 年开始（2014 年春节不可得）
命名陷阱   : 地区行署城市在数据中名为「阿克苏地区」「喀什地区」，不是「阿克苏市」
编码警告   : 文件本身是 UTF-8，不要用 GBK 转码

用法
----
  python3 -u download_aqi.py                # 全量：12 个春节窗口 × 15 天 = 180 文件
  python3 -u download_aqi.py --years 2025   # 只拉指定年份
  python3 -u download_aqi.py --window 7 7   # 除夕前后天数（默认 7 7）
  python3 -u download_aqi.py --force        # 忽略本地已有文件，强制重下

输出
----
  data/raw/china_cities_YYYYMMDD.csv   原始单日文件（本地已存在且完整则跳过）
"""

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = "https://quotsoft.net/air/data/china_cities_{d}.csv"
UA = {"User-Agent": "Mozilla/5.0 (academic course project)"}

# 农历正月初一（春节）的公历日期；除夕 = 前一天
CNY_DAY1 = {
    2015: (2, 19), 2016: (2, 8),  2017: (1, 28), 2018: (2, 16),
    2019: (2, 5),  2020: (1, 25), 2021: (2, 12), 2022: (2, 1),
    2023: (1, 22), 2024: (2, 10), 2025: (1, 29), 2026: (2, 17),
}

MIN_VALID_BYTES = 50_000  # 小于此大小视为残缺，需重新下载


def cny_eve(year):
    """返回该年除夕（春节前一天）的日期。"""
    m, d = CNY_DAY1[year]
    return date(year, m, d) - timedelta(days=1)


def download(day, retries=3):
    """下载单日文件，返回解码后的文本；失败返回 None。"""
    url = BASE.format(d=day.strftime("%Y%m%d"))
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == retries - 1:
                print("      !! 失败: %s" % exc, file=sys.stderr)
                return None
            time.sleep(4 * (attempt + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=sorted(CNY_DAY1))
    ap.add_argument("--window", nargs=2, type=int, default=[7, 7],
                    metavar=("BEFORE", "AFTER"), help="除夕前后天数，默认 7 7")
    ap.add_argument("--raw-dir", default="data/raw")
    ap.add_argument("--force", action="store_true", help="忽略本地已有文件")
    ap.add_argument("--sleep", type=float, default=1.5, help="每次请求间隔秒数")
    args = ap.parse_args()
    # 默认参数是相对路径；从项目目录之外运行会解析到错误位置，甚至抛 FileNotFoundError
    # 而报错信息看不出是路径问题。统一以仓库根目录为基准；绝对路径不受影响。
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    before, after = args.window
    days = []
    for y in args.years:
        if y not in CNY_DAY1:
            print("!! 未收录年份 %d，跳过（如需扩展请更新 CNY_DAY1）" % y, file=sys.stderr)
            continue
        eve = cny_eve(y)
        for off in range(-before, after + 1):
            days.append((eve + timedelta(days=off), y, off))
    days.sort()

    os.makedirs(args.raw_dir, exist_ok=True)
    total = len(days)
    print("计划处理 %d 个文件（%d 个春节窗口 × %d 天）"
          % (total, len(args.years), before + after + 1))
    print("归档目录: %s" % args.raw_dir)
    print("-" * 72)

    ok = skipped = failed = 0
    t_start = time.time()
    for n, (day, year, off) in enumerate(days, 1):
        name = "china_cities_%s.csv" % day.strftime("%Y%m%d")
        path = os.path.join(args.raw_dir, name)
        tag = "%3d/%3d %s (rel %+d)" % (n, total, day, off)

        if not args.force and os.path.exists(path) and os.path.getsize(path) >= MIN_VALID_BYTES:
            skipped += 1
            print("[%s] 已有，跳过 (%d KB)" % (tag, os.path.getsize(path) // 1024))
            continue

        sys.stdout.write("[%s] 下载中 ... " % tag)
        sys.stdout.flush()
        t0 = time.time()
        text = download(day)
        if text is None:
            failed += 1
            print("失败")
            continue
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        ok += 1
        elapsed = time.time() - t0
        eta = (time.time() - t_start) / max(ok + skipped, 1) * (total - n)
        print("%d KB  %.1fs  (累计成功 %d，预计剩余 %.0f 分)"
              % (len(text) // 1024, elapsed, ok, eta / 60))

        if n < total:
            time.sleep(args.sleep)

    print("-" * 72)
    print("完成：成功 %d，跳过 %d，失败 %d，总计 %d，耗时 %.1f 分钟"
          % (ok, skipped, failed, total, (time.time() - t_start) / 60))
    if failed:
        print("!! 有 %d 个文件失败，重新运行本脚本即可补下（已有文件会自动跳过）" % failed,
              file=sys.stderr)
    print("\n下一步：python3 -I scripts/build_panel.py")


if __name__ == "__main__":
    sys.exit(main())
