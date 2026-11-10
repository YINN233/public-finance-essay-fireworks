#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成气象数据的来源清单（可复现记录）。

为什么需要
----------
气象是从在线接口抓的，不是本地原始数据。接口会更新，坐标会改，抓取脚本
也会改。只记录“跑了哪个脚本”不够——要记录**当时拿到的是什么**。

本脚本不保存原始响应（体积大、且接口本身不提供逐位版本号），只记录：
- 抓取参数（接口、变量、时区、窗口、城市数）；
- 输出文件的行数、城市数、日期范围与 SHA-256；
- 坐标表的 SHA-256 与三处已更正的错配。

因此准确的说法是“**可重新估计**”，不是“逐位复现”。

用法
----
    python3 -I scripts/weather_manifest.py --write
"""
import argparse
import csv
import hashlib
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def summarize(path, date_col="date", city_col="city"):
    with open(path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    cities = {r[city_col] for r in rows}
    if date_col is None:
        lo = hi = "—"
    else:
        dates = [r[date_col] for r in rows]
        lo, hi = min(dates), max(dates)
    return {"rows": len(rows), "cities": len(cities), "lo": lo, "hi": hi,
            "sha": sha256(path)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    files = {
        "data/met_cityday.csv": "ERA5 日统计（风速、日温差、气温、气压、湿度）",
        "data/blh_cityday.csv": "边界层高度（仅 2025、2026）",
        "data/city_coords.csv": "城市经纬度（气象抓取输入）",
    }
    lines = ["# 气象数据清单", "",
             "由 `python3 -I scripts/weather_manifest.py --write` 生成。**不要手改。**", "",
             "## 一、抓取参数", "",
             "| 项目 | 值 |", "|---|---|",
             "| 接口 | Open-Meteo archive（ERA5）/ historical-forecast（BLH）|",
             "| 变量 | 10 m 风速、2 m 气温、日温差、地面气压、相对湿度；BLH 另行抓取 |",
             "| 时区 | `Asia/Shanghai`，接口直接返回本地日 |",
             "| 窗口 | 每个春节年份 rel_day −7 … +1（9 天）|",
             "| 城市数 | 306 |",
             "| 限流 | 按城市数计次，每分钟 600 次；`SLEEP = 4.5` 秒 |",
             "| 坐标修订 | 资阳、中山、大同三处错配已更正并重抓 |", "",
             "## 二、文件指纹", "",
             "| 文件 | 内容 | 行数 | 城市数 | 日期范围 | SHA-256 |",
             "|---|---|---|---|---|---|"]
    ok = True
    for rel, desc in files.items():
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            lines.append("| `%s` | %s | **缺失** | — | — | — |" % (rel, desc))
            ok = False
            continue
        s = summarize(path, date_col=None if rel.endswith("city_coords.csv") else "date")
        span = "—" if s["lo"] == s["hi"] == "—" else "%s 至 %s" % (s["lo"], s["hi"])
        lines.append("| `%s` | %s | %d | %d | %s | `%s` |"
                     % (rel, desc, s["rows"], s["cities"], span, s["sha"]))
    lines += ["",
              "## 三、限制", "",
              "· 原始响应未保存。接口更新后重新抓取，结果可能不同。",
              "· 因此本项目的准确表述是**可重新估计**，不是**逐位复现**。",
              "· 若要逐位复现，需在首次抓取时保存原始 JSON 与其 SHA-256。",
              "· BLH 只在 2025、2026 两个窗口可得；其余 10 个窗口用代理。"]
    text = "\n".join(lines) + "\n"
    if args.write:
        out = os.path.join(ROOT, "docs", "气象数据清单.md")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("已写入 docs/气象数据清单.md")
    else:
        print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
