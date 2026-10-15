#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把政策文本（policy/policy.csv）展开为「城市 × 日」的政策状态，并并入面板

policy.csv 是「一行 = 一次政策变动」。本脚本把它展开成每个城市每一天的
适用政策状态，再与 panel_cityday.csv 按 (city, date) 合并，输出分析用数据。

用法
----
  python3 -I merge_policy.py
  python3 -I merge_policy.py --policy policy/policy.csv --panel data/panel_cityday.csv

输出
----
  data/panel_with_policy.csv    面板 + 政策变量
  stdout                        覆盖率报告 + 政策类型 × 相对日 的均值表

新增变量
--------
  policy_type   1=无专门管制 / 2=限放 / 3=全面禁放 / 空=该城该日无政策记录
  ban           1 若 policy_type=3
  restrict      1 若 policy_type=2
  agency_cat    发文主体类别: eco/emergency/police/npc/gov/other（政策动机的代理）
  days_since_change  距上一次政策变动的天数（供事件研究用）
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import date

# 政策文件里的城市名 → 空气质量数据里的城市名（地区行署城市用地区名）
ALIAS = {
    "阿克苏": "阿克苏地区", "阿克苏市": "阿克苏地区",
    "喀什": "喀什地区", "喀什市": "喀什地区",
    "和田": "和田地区", "和田市": "和田地区",
    "塔城": "塔城地区", "阿勒泰": "阿勒泰地区",
}

AGENCY_KEYS = [("生态环境", "eco"), ("环保", "eco"), ("应急", "emergency"),
               ("公安", "police"), ("消防", "emergency"), ("人大", "npc"),
               ("政府", "gov")]

# tax_instrument 字段的取值含义（模块级：早先误写在 if 块内，无记录时会 NameError）
TAX_LABEL = {"0": "无（仅命令控制）", "1": "有地方价格型工具",
             "2": "国家消费税（背景）"}

# 省级政策展开表：policy.csv 里以省为单位的行（如"山西省"）会展开到该省全部地级市。
# 目前只放山西（2020-10-01 全省"五禁"、2025-12-16 废止）；需要时按同格式补充其他省。
PROVINCE_CITIES = {
    # 山西：2020-10-01 全省"五禁"；2025-12-16 废止（省政府废止 124 件规范性文件）
    "山西": ["太原", "大同", "阳泉", "长治", "晋城", "朔州", "晋中",
             "运城", "忻州", "临汾", "吕梁"],
    # 河南：2019-08 部署全域禁放（由各市政府出台规定）；2023-01 省政府发文要求各市
    # 按"限定时间、限定地点、限定品种"**自行决定**——所以各市响应不一致，这正是
    # 我们要的省内变异，因此 2023 年那次**不写成省级行**，只给实际放开的市场写行。
    "河南": ["郑州", "开封", "洛阳", "平顶山", "安阳", "鹤壁", "新乡", "焦作",
             "濮阳", "许昌", "漯河", "三门峡", "南阳", "商丘", "信阳", "周口",
             "驻马店", "济源"],
}


def norm_city(name, panel_cities):
    name = (name or "").strip()
    if name in panel_cities:
        return name
    if name in ALIAS and ALIAS[name] in panel_cities:
        return ALIAS[name]
    for cand in (name + "地区", name.rstrip("市")):
        if cand in panel_cities:
            return cand
    return None


def agency_cat(text):
    t = text or ""
    for key, cat in AGENCY_KEYS:
        if key in t:
            return cat
    return "other" if t.strip() else ""


def read_policy(path, panel_cities):
    """返回 city -> [(effective_date, row_dict)]（按日期升序），以及未匹配的城市名。"""
    tl = defaultdict(list)
    unmatched = set()
    with open(path, encoding="utf-8-sig") as fh:
        lines = [ln.rstrip("\n") for ln in fh if not ln.lstrip().startswith("#")]
    for ln, r in zip(lines, csv.DictReader(lines)):
        # 字段数校验：未加引号的逗号（多字段）或漏写逗号（少字段）都会让整行
        # 静默错位而不报错——例如把 URL 读成发文主体。必须显式拦下来。
        extra = r.get(None)
        miss = [k for k, v in r.items() if k is not None and v is None]
        if extra or miss:
            why = []
            if extra:
                why.append("多出 %d 个字段（疑似字段内含未加引号的逗号）" % len(extra))
            if miss:
                why.append("缺少字段 %s（疑似漏写逗号）" % "、".join(miss))
            print("   !! 字段数异常，该行会错位：%s" % "；".join(why), file=sys.stderr)
            print("      %s" % ln[:90], file=sys.stderr)
        raw = (r.get("city_name") or "").strip()
        if not raw:
            continue
        city = norm_city(raw, panel_cities)
        if city is None:
            # 省级政策：city_name 写成"山西省"这类，展开到该省全部地级市
            prov = (raw.replace("省", "").replace("（全省）", "")
                    .replace("(全省)", "").strip())
            members = [c for c in PROVINCE_CITIES.get(prov, []) if c in panel_cities]
            if members:
                try:
                    d_prov = date.fromisoformat((r.get("effective_date") or "").strip())
                except ValueError:
                    unmatched.add("%s(日期格式: %s)" % (raw, r.get("effective_date")))
                    continue
                for c in members:
                    tl[c].append((d_prov, dict(r, city_name=c)))
                continue
            unmatched.add(raw)
            continue
        ds = (r.get("effective_date") or "").strip()
        if not ds:
            unmatched.add("%s(无 effective_date)" % raw)
            continue
        try:
            d = date.fromisoformat(ds)
        except ValueError:
            unmatched.add("%s(日期格式: %s)" % (raw, ds))
            continue
        tl[city].append((d, r))
    for c in tl:
        tl[c].sort(key=lambda t: t[0])
    return tl, unmatched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="policy/policy.csv")
    ap.add_argument("--panel", default="data/panel_cityday.csv")
    ap.add_argument("--out", default="data/panel_with_policy.csv")
    args = ap.parse_args()
    # 默认参数是相对路径；从项目目录之外运行会解析到错误位置，甚至抛 FileNotFoundError
    # 而报错信息看不出是路径问题。统一以仓库根目录为基准；绝对路径不受影响。
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if not os.path.exists(args.policy):
        print("!! 找不到 %s" % args.policy, file=sys.stderr)
        return 1
    if not os.path.exists(args.panel):
        print("!! 找不到 %s。先运行 scripts/build_panel.py" % args.panel, file=sys.stderr)
        return 1

    rows = list(csv.DictReader(open(args.panel, encoding="utf-8-sig")))
    panel_cities = {r["city"] for r in rows}
    tl, unmatched = read_policy(args.policy, panel_cities)

    if unmatched:
        print("!! 以下政策记录的城市名在面板中找不到（或日期缺失），已跳过：", file=sys.stderr)
        for u in sorted(unmatched):
            print("     %s" % u, file=sys.stderr)
    print("政策时间线：%d 个城市" % len(tl))

    # 关键检查：若某城市的首条政策记录晚于样本起点，它更早的春节窗口会被当成
    # 「无记录」而剔除，导致该城市只以部分年份进入比较（等于悄悄地改变了样本）。
    if tl:
        sample_start = min(date.fromisoformat(r["date"]) for r in rows)
        late = {c: v[0][0] for c, v in tl.items() if v and v[0][0] > sample_start}
        if late:
            print("\n!! 以下城市的首条政策记录晚于样本起点（%s），其更早的春节窗口"
                  "没有政策记录、已从下方均值表中剔除：" % sample_start, file=sys.stderr)
            for c, d in sorted(late.items(), key=lambda kv: kv[1]):
                print("     %-14s 首条记录 %s" % (c, d), file=sys.stderr)
            print("   → 请补充更早的政策状态：当时若无专门管制，用 policy_type=1 补一行；"
                  "若当时已有规定，补上其生效日期。", file=sys.stderr)

    # 政策状态查找：返回该日适用的那次变动
    def status(city, d):
        best = None
        for eff, r in tl.get(city, []):
            if eff <= d:
                best = (eff, r)
            else:
                break
        return best

    cols = list(rows[0].keys()) + ["policy_type", "scope_level", "ban", "restrict",
                                   "agency_cat", "days_since_change",
                                   "tax_instrument"]
    n_matched = 0
    type_counts = defaultdict(set)          # policy_type -> 城市集合
    agency_counts = defaultdict(set)        # agency_cat -> 城市集合
    tax_counts = defaultdict(set)           # tax_instrument -> 城市集合
    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            try:
                d = date.fromisoformat(r["date"])
            except ValueError:
                continue
            st = status(r["city"], d)
            if st is None:
                r.update(policy_type="", scope_level="", ban="", restrict="",
                         agency_cat="", days_since_change="", tax_instrument="")
            else:
                eff, pol = st
                pt = (pol.get("policy_type") or "").strip()
                cat = agency_cat(pol.get("issuing_agency"))
                tax = (pol.get("tax_instrument") or "").strip()
                r.update(policy_type=pt,
                         scope_level=(pol.get("scope_level") or "").strip(),
                         ban=1 if pt == "3" else 0,
                         restrict=1 if pt == "2" else 0,
                         agency_cat=cat,
                         days_since_change=(d - eff).days,
                         tax_instrument=tax)
                n_matched += 1
                if pt:
                    type_counts[pt].add(r["city"])
                if cat:
                    agency_counts[cat].add(r["city"])
                if tax:
                    tax_counts[tax].add(r["city"])
            w.writerow(r)

    print("写入 %s（%d 行，其中 %d 行匹配到政策）" % (args.out, len(rows), n_matched))
    if not tl:
        print("\n!! 还没有任何政策记录，无法继续。请按 policy/README.md 填写 policy.csv")
        return 0

    print("\n=== 各政策类型的覆盖城市数 ===")
    label = {"1": "无专门管制", "2": "限放", "3": "全面禁放"}
    for k in ["3", "2", "1"]:
        n = len(type_counts.get(k, ()))
        flag = "   <<< 少于 20 城，暂不足以支撑分组比较" if k == "3" and n < 20 else ""
        print("  %s %-6s %3d 城%s" % (k, label[k], n, flag))
    ncov = len({c for s in type_counts.values() for c in s})
    print("  有政策记录的城市共 %d 个（面板共 %d 个）" % (ncov, len(panel_cities)))

    if agency_counts:
        print("\n=== 发文主体分布（政策动机的代理变量）===")
        for k, v in sorted(agency_counts.items(), key=lambda kv: -len(kv[1])):
            print("  %-10s %3d 城" % (k, len(v)))

    print("\n=== 价格型工具（tax_instrument）===")
    if tax_counts:
        for k, v in sorted(tax_counts.items(), key=lambda kv: -len(kv[1])):
            print("  %s %-22s %3d 城" % (k, TAX_LABEL.get(k, k), len(v)))
    else:
        print("  目前没有任何城市记录到价格型工具（或该字段尚未填写）。")
    print("  注：文章第二块机制的前提是「现实中几乎没有城市用价格工具管燃放」，")
    print("      这是一条需要用政策库证实的断言——查满全部地级市之前不要写进结论。")

    # 政策类型 × 相对日 的均值表（快速判断变异是否存在）
    print("\n=== 政策类型 × 相对日：日均 PM2.5 均值（μg/m³）===")
    agg = defaultdict(lambda: defaultdict(list))
    aggc = defaultdict(set)
    for r in rows:
        try:
            d = date.fromisoformat(r["date"])
        except ValueError:
            continue
        st = status(r["city"], d)
        if st is None or not (st[1].get("policy_type") or "").strip():
            continue
        if r["pm25"] == "":
            continue
        k = st[1]["policy_type"].strip()
        agg[k][int(r["rel_day"])].append(float(r["pm25"]))
        aggc[k].add(r["city"])
    hdr = [-7, -1, 0, 1, 2, 7]
    print("  %-10s" % "type" + "".join("%9s" % ("day%+d" % h) for h in hdr) + "%7s" % "n城")
    for k in ["3", "2", "1"]:
        if k not in agg:
            continue
        line = "  %-10s" % label[k]
        for h in hdr:
            v = agg[k].get(h, [])
            line += "%9s" % (("%.1f" % (sum(v) / len(v))) if v else "-")
        line += "%7d" % len(aggc[k])
        print(line)
    print("  注：n城为该组贡献观测的城市数。**每组少于 20 城时不要解读为因果**——"
          "单城或少数城市的差异可能来自城市规模、产业、气象或执行强度。")
    print("\n下一步：政策覆盖足够后，运行事件研究与 DiD（脚本待建）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
