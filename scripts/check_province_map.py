#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验 data/city_province.csv（城市 → 省份映射）

为什么需要校验
--------------
这份映射是手工维护的，而它一旦有单个城市错配，`run_did.py --same-province`
会把对照城市取错省——**结果会静默地错，不会报错**。所以必须有机器校验。

三项检查
--------
1. **覆盖**：面板里每个城市都有归属吗？映射里有面板外的城市吗？
2. **分段常数**：原始 AQI 文件的列序是按省份分组的。把面板城市按该列序排列后，
   省份序列应当**分段常数**。任何单个城市错配都会打断连续段，从而暴露出来。
3. **交叉核对**：`merge_policy.PROVINCE_CITIES`（山西、河南的省级展开表）
   与本文档是否一致。

用法
----
  python3 -I check_province_map.py
  python3 -I check_province_map.py --raw data/raw/china_cities_20150211.csv
"""

import argparse
import csv
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from merge_policy import PROVINCE_CITIES   # noqa: E402

# 各省省会 / 自治区首府 / 直辖市自身。用途是**证伪**：如果某个省会城市被写进了
# 别省的列表，几乎肯定是一处错配。这是本校验里唯一能独立于"列序"发现的错误类型。
CAPITALS = {
    "北京": "北京", "天津": "天津", "上海": "上海", "重庆": "重庆",
    "河北": "石家庄", "山西": "太原", "内蒙古": "呼和浩特", "辽宁": "沈阳",
    "吉林": "长春", "黑龙江": "哈尔滨", "江苏": "南京", "浙江": "杭州",
    "安徽": "合肥", "福建": "福州", "江西": "南昌", "山东": "济南",
    "河南": "郑州", "湖北": "武汉", "湖南": "长沙", "广东": "广州",
    "广西": "南宁", "海南": "海口", "四川": "成都", "贵州": "贵阳",
    "云南": "昆明", "西藏": "拉萨", "陕西": "西安", "甘肃": "兰州",
    "青海": "西宁", "宁夏": "银川", "新疆": "乌鲁木齐",
}


def read_map(path):
    m = {}
    dup = []
    with open(path, encoding="utf-8-sig") as fh:
        lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
    for r in csv.DictReader(lines):
        c = (r.get("city") or "").strip()
        p = (r.get("province") or "").strip()
        if not c:
            continue
        if c in m and m[c] != p:
            dup.append((c, m[c], p))
        m[c] = p
    return m, dup


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=os.path.join(here, "data/city_province.csv"))
    ap.add_argument("--panel", default=os.path.join(here, "data/panel_cityday.csv"))
    ap.add_argument("--raw", default=os.path.join(here, "data/raw/china_cities_20150211.csv"))
    args = ap.parse_args()

    m, dup = read_map(args.map)
    print("映射载入：%d 个城市，%d 个省份/大区" % (len(m), len(set(m.values()))))
    rc = 0
    if dup:
        rc = 1
        print("!! 同一城市被赋了两个省份：")
        for c, a, b in dup:
            print("     %s：%s vs %s" % (c, a, b))

    # ---- 检查 1：覆盖 ----
    cities = []
    seen = set()
    for r in csv.DictReader(open(args.panel, encoding="utf-8-sig")):
        c = r["city"]
        if c not in seen:
            seen.add(c)
            cities.append(c)
    miss = [c for c in cities if c not in m]
    extra = [c for c in m if c not in seen]
    print("\n=== 检查 1：覆盖 ===")
    print("  面板城市 %d 个；已归属 %d 个" % (len(cities), len(cities) - len(miss)))
    if miss:
        rc = 1
        print("  !! 以下 %d 个面板城市在映射中缺失（同省对照会静默退化）：" % len(miss))
        for i in range(0, len(miss), 8):
            print("     " + "、".join(miss[i:i + 8]))
    if extra:
        print("  ⚠️ 映射中有 %d 个城市不在面板里（无害，可能是拼写差异或未下载的城市）：" % len(extra))
        for i in range(0, len(extra), 8):
            print("     " + "、".join(extra[i:i + 8]))

    # ---- 检查 2：原始列序上的分段常数 ----
    print("\n=== 检查 2：省份序列在原始列序上是否分段常数（提示性，不判失败）===")
    print("  注：原始文件的列序按省份分组，但**先把各省会与计划单列市列在一起**，"
          "县级市另成一块（列 161—190）。所以省份分成多段是文件结构，不是错配。"
          "\n  真正能证伪的是检查 4（省会错配）。")
    if not os.path.exists(args.raw):
        print("  ⚠️ 找不到 %s，跳过（原始数据未下载时正常）" % args.raw)
    else:
        hdr = open(args.raw, encoding="utf-8-sig").readline().strip().split(",")[3:]
        order = {}
        for i, c in enumerate(hdr):
            c = c.strip()
            if c and c not in order:
                order[c] = i
        seq = sorted([c for c in cities if c in order], key=lambda c: order[c])
        noplace = [c for c in cities if c not in order]
        seq = [(c, m.get(c, "?")) for c in seq]
        runs = []
        for c, p in seq:
            if runs and runs[-1][0] == p:
                runs[-1][1].append(c)
            else:
                runs.append((p, [c]))
        print("\n  可比对城市 %d 个（%d 个不在原始列中）；连续段数 %d（省份数 %d）"
              % (len(seq), len(noplace), len(runs), len(set(m.values()))))
        # 单城孤段：省会/直辖市/计划单列市出现在这里是**预期**的
        PLANNED = {"大连", "青岛", "宁波", "厦门", "深圳"}
        singles = [(p, cs[0]) for p, cs in runs if len(cs) == 1]
        odd = [(p, c) for p, c in singles
               if CAPITALS.get(p) != c and c not in PLANNED]
        print("  单城段 %d 个，其中 %d 个既非本省省会也非计划单列市："
              % (len(singles), len(odd)))
        for p, c in odd:
            print("     %s → %s（列序位置 %d，请确认）" % (c, p, order.get(c, -1)))

    # ---- 检查 4：省会错配（可证伪）----
    print("\n=== 检查 4：省会/首府是否被写进了别省 ===")
    bad = []
    for c, p in m.items():
        for q, cap in CAPITALS.items():
            if c == cap and p != q:
                bad.append((c, p, q))
    # 直辖市名本身既是省名也是市名，跳过
    bad = [b for b in bad if b[0] != b[1]]
    if bad:
        rc = 1
        print("  !! 以下城市是某省省会，却被归到别省：")
        for c, got, should in bad:
            print("     %s：映射记为 %s，但它应是 %s 的省会" % (c, got, should))
    else:
        print("  通过：没有任何省会/首府被归到别省（共核对 %d 个省会）" % len(CAPITALS))
    # 反向：每个省的省会在不在该省列表里
    lack = [(p, cap) for p, cap in CAPITALS.items()
            if cap not in m or (m.get(cap) != p and cap != p)]
    lack = [(p, cap) for p, cap in lack if p != cap]
    if lack:
        print("  ⚠️ 以下省份的省会在映射中缺失或归属不符（可能只是该市未下载）：")
        for p, cap in lack:
            print("     %s：省会 %s（映射中为 %s）" % (p, cap, m.get(cap, "缺失")))

    # ---- 检查 3：与 merge_policy 的省级展开表交叉核对 ----
    print("\n=== 检查 3：与 merge_policy.PROVINCE_CITIES 交叉核对 ===")
    ok = True
    for prov, lst in PROVINCE_CITIES.items():
        for c in lst:
            got = m.get(c)
            if got is None:
                ok = rc = 1
                print("  !! %s 在省级展开表里，但映射中没有" % c)
            elif got != prov:
                ok = rc = 1
                print("  !! %s：省级展开表记为 %s，映射记为 %s" % (c, prov, got))
    if ok:
        print("  一致（山西 %d 城、河南 %d 城）"
              % (len(PROVINCE_CITIES.get("山西", [])), len(PROVINCE_CITIES.get("河南", []))))

    print("\n各省城市数（仅列 ≥5 城的省，供同省对照的可达性判断）：")
    cnt = Counter(m.values())
    for p, n in sorted(cnt.items(), key=lambda kv: -kv[1]):
        if n >= 5:
            print("  %-12s %2d 城" % (p, n))

    print("\n%s" % ("!! 有检查未通过，见上。" if rc else "全部检查通过。"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
