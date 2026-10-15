# 烟花爆竹管制研究 · 实施计划

> **给执行者**：本计划按任务逐条执行，步骤用 `- [ ]` 勾选。每个任务末尾都有**验收标准**，不通过不算完成。
> **配套文档**：`docs/spec-研究设计.md`（设计依据，执行前先读）。两者一起读。

**目标**：完成一篇公共财政学课程论文——论证"政府已有价格工具（消费税）却仍普遍叠加禁放"，并用全国面板的因果估计 + 约 20 城的执法数据支撑一个成本有效性对照。

**方法栈**：Python 3（数据采集与面板构建**只用标准库**；绘图用 numpy + matplotlib）；DCDH 估计用 Stata 的 `did_multiplegt` 或 R 的对应实现。全部数据与代码放在仓库 `essay-project/`。

**设计文档**：`docs/spec-研究设计.md`

---

## 全局约束（每个任务都隐含遵守）

1. 数据文件是 **UTF-8**，不得用 GBK 转码。
2. 结果变量的主口径是**正月初一（`rel_day = +1`）**，不是除夕。
3. **南疆各市必须用 PM2.5**，不得用 AQI 或 PM10（沙尘污染）。
4. 城市名以空气质量数据为准：地区行署城市用地区名（「阿克苏地区」）。
5. 估计用**平衡面板 308 城**，非平衡面板另作稳健性。
6. `policy.csv` 字段内若含逗号必须加引号；改完必须跑 `merge_policy.py` 看有无 `!!`。
7. 成本收益中的剂量反应与 VSL 参数**必须引用文献并标注出处**，不得自行设定。
8. 凡"待核实"的制度事实，未核到一手来源不得写入正文。

## 最可能出错的六处（每个任务的自检都要覆盖其中相关的项）

1. **政策切换年份记错**——这是处理变量的定义，错一年就污染整个事件研究。日期以文件原文的施行条款为准，不用网页发布日期。
2. **把"限放"当"较弱版本的禁放"**——春节恰是限放城市的**允许**燃放期，二者是不同制度，混淆会毁掉处理变量含义。
3. **出动人次口径混用**——"禁放专项"与"全市春节安保总量"不可比，混用会得出错误结论。
4. **查处案件数单独当执法投入**——它是"投入 × 违规规模"的乘积，必须与产出配对解读。
5. **选样偏差未披露**——按数据可得性选样会系统性偏向治理能力强的城市，必须用全国面板检验并明示。
6. **成本收益把转移支付算成社会成本**——罚款是转移支付；真实资源成本是警力、人力、设备。

---

## 文件结构

```
essay-project/
├── docs/
│   ├── spec-研究设计.md          设计（已有）
│   ├── plan-实施计划.md          本文件
│   └── 讨论提纲-与老师讨论稿.md    给老师的那份（已有）
├── policy/
│   ├── README.md                 采集手册（已有）
│   ├── policy.csv                政策库（已有，本计划扩展）
│   └── 切换城市名单.md            ← Task 1 产出
├── data/
│   ├── raw/                      原始单日文件（已有，不入库）
│   ├── panel_cityday.csv         城市×日面板（已有，不入库）
│   ├── panel_cityyear.csv        ← Task 4：折叠后的估计用面板
│   ├── sample_20cities.csv       ← Task 3：选样与代表性检验
│   ├── enforcement.csv           ← Task 5：执法数据
│   └── weather_era5.csv          ← Task 7：气象匹配
├── scripts/
│   ├── download_aqi.py/build_panel.py/check_coverage.py/merge_policy.py/make_figs.py  （已有）
│   ├── select_sample.py          ← Task 3
│   ├── collapse_panel.py         ← Task 4
│   ├── run_did.py                ← Task 4
│   ├── merge_enforcement.py      ← Task 5
│   ├── run_2x2.py                ← Task 6
│   └── cost_benefit.py           ← Task 8
└── figs/
```

---

## Task 1：锁定政策切换城市名单

**为什么第一**：它决定第一层有没有识别变异。若无城市改过政策，整个设计重来。

**Files**
- Create: `policy/切换城市名单.md`
- Modify: `policy/policy.csv`

**已有起点（本轮检索所得，须逐城核实）**
- 2023 年由禁改限：昆明、兰州、大连、杭州、珠海、西安、延川、白银、东营、滨州
- 天津、上海、重庆：中心城区禁放、郊区限放
- 广州：2023-03 市人大常委会审查认定花都、番禺、南沙全域禁放不符合比例原则，2024 春节恢复燃放
- 山西：2025-12-16 废止 124 件规范性文件（含 2020 年全省禁令）
- 陕西、四川：2025 年清理全面禁放文件
- 河南：郑州、洛阳、南阳、信阳、平顶山、新密调整禁燃令
- 仍全域禁放（对照）：北京、上海（外环内）、合肥、南阳、泸州

**Interfaces**
- Produces：`policy/policy.csv` 中新增若干行（每个切换城市至少两行：禁放行 + 改限放行）；`切换城市名单.md` 中的一张表（城市 / 省份 / 禁放生效年 / 改限放生效年 / 来源URL / 核实状态）

- [ ] **Step 1：逐城核实切换年份**

对名单中每城，检索并打开一手文件：
```
<市名> 烟花爆竹 燃放管理 规定 修订 废止 site:gov.cn
<市名> 全面禁止燃放烟花爆竹 通告 废止
```
记录两个日期：**禁放起始日**与**改限放生效日**。日期以文件施行条款为准。

- [ ] **Step 2：写入 policy.csv**

按 `policy/README.md` 的字段规范写行。每个切换城市至少两行。用顿号代替字段内的半角逗号。

- [ ] **Step 3：校验**

```bash
python3 -I scripts/merge_policy.py
```
Expected：无 `!!` 字段数异常；"各政策类型的覆盖城市数"中 `3 全面禁放` 不再是 1 城。

- [ ] **Step 4：统计并成文**

在 `切换城市名单.md` 开头写一句话结论，形如：
> 已核实有过全面禁放的城市 N 个，其中 M 个在 2023 年后改为限放；切换年份明确的有 M 个。

- [ ] **Step 5：提交**

```bash
git add policy/ && git commit -m "政策库：核实禁放/禁改限城市名单"
```

**验收标准**：`policy.csv` 中 `policy_type=3` 的城市 ≥ 10 个；其中发生 `3→2` 切换且两个日期都有一手来源的城市 ≥ 5 个；`merge_policy.py` 无告警。
**若验收不通过**：说明变异不足，回到 `docs/spec-研究设计.md` §7 风险表，改走"描述性政策评估"路线，不要硬做 DiD。

---

## Task 2：补齐第一批 20 城的政策文本

**Files**
- Modify: `policy/policy.csv`

**Interfaces**
- Consumes：Task 1 的名单与格式
- Produces：20 城的完整政策时间线；`policy.csv` 新增两个结构化字段 `penalty_detention`（0/1，是否可行政拘留）与 `penalty_amount`（罚款上限，元）

- [ ] **Step 1：按手册填 20 城**

照 `policy/README.md` 第八节的七步操作示范。每人认领 4 城。

- [ ] **Step 2：结构化罚则**

从 `penalty` 自由文本中提取两项：是否可拘留、罚款上限。填不进 `penalty_amount` 的（如"批评教育"）记 0。

- [ ] **Step 3：校验并统计**

```bash
python3 -I scripts/merge_policy.py
```
Expected：20 城均有政策记录；`verified=Y` 的城市数 ≥ 10。

- [ ] **Step 4：提交**

```bash
git add policy/ && git commit -m "政策库：补齐第一批 20 城政策文本与罚则结构化"
```

**验收标准**：20 城每城至少一行、其中至少 10 城 `verified=Y`；`penalty_detention` 与 `penalty_amount` 无空值（无此项填 0）。

---

## Task 3：选样与代表性检验

**Files**
- Create: `scripts/select_sample.py`, `data/sample_20cities.csv`

**Interfaces**
- Consumes：`data/panel_cityday.csv`、`data/coverage_city_year.csv`
- Produces：`data/sample_20cities.csv`（列：city, province, in_sample, 切换年, pop_proxy, baseline_pm25, spike_ratio, spike_increment, z_baseline, z_spike_ratio, z_increment, 备注）

- [ ] **Step 1：写脚本，先定输出格式**

脚本读入候选 20 城名单（写在脚本顶部的常量里），从面板算每城的基线 PM2.5、初一倍数、绝对增量，再算这三个量在 308 城平衡面板中的 z 值。

- [ ] **Step 2：跑并检查**

```bash
python3 -I scripts/select_sample.py
```
Expected：输出 `data/sample_20cities.csv`，每城四个统计量均有值；同时打印入选城市与全国均值/中位数的对照。

- [ ] **Step 3：写代表性判断**

在输出末尾打印一段结论，形如："入选城市在**基线 PM2.5** 上平均高于/低于全国中位数 X%，在**尖峰倍数**上……"，供论文的数据部分直接引用。

- [ ] **Step 4：提交**

```bash
git add scripts/select_sample.py && git commit -m "选样：20 城代表性检验"
```

**验收标准**：脚本可重复运行且输出稳定；能写出一句明确的"这批城市在哪些维度不具代表性"的结论。
**注意**：这是**选样偏差的披露**，不是消除。不要为了让样本"看起来有代表性"而反复换城市——那正是偏差本身。

---

## Task 4：第一层估计

**Files**
- Create: `scripts/collapse_panel.py`, `scripts/run_did.py`, `data/panel_cityyear.csv`

**Interfaces**
- Consumes：`data/panel_cityday.csv`、`data/panel_with_policy.csv`（由 `merge_policy.py` 生成）
- Produces：`data/panel_cityyear.csv`（列：city, cny_year, policy_type, ban, restrict, penalty_detention, agency_cat, pm25_d1, pm25_win, pm25_base, spike_ratio, spike_increment）；`run_did.py` 输出三个估计量并列的结果表

- [ ] **Step 1：写折叠脚本**

`collapse_panel.py`：把城市 × 日折叠为城市 × 春节年份。结果变量四个——初一日均（`pm25_d1`）、窗口日均（`pm25_win`）、基线日均（`pm25_base`，除夕前 7 日至前 2 日）、以及由前两者派生的倍数与增量。

- [ ] **Step 2：跑并校验行数**

```bash
python3 -I scripts/collapse_panel.py
```
Expected：行数 = 城市数 × 年份数；平衡面板下应为 **308 × 12 = 3,696**。若不符，检查是否有城市在某年被剔除。

- [ ] **Step 3：写估计脚本**

`run_did.py`：主结果用 de Chaisemartin & D'Haultfœuille（2020）的估计量（Stata `did_multiplegt` 或 R 实现，由脚本调起并读取结果）；附录报告 TWFE 与 Callaway–Sant'Anna。三者并列成一张表，并输出三者差异的来源说明（处理逆转 + 效应异质性）。

- [ ] **Step 4：跑并做已知值检查**

```bash
python3 -I scripts/run_did.py
```
Expected：DCDH 系数与置信区间输出；**且用 `pm25_d1` 与 `pm25_win` 两个结果变量各跑一次，符号方向应一致**。若不一致，说明结果对结果变量的选择敏感，必须报告。

- [ ] **Step 5：提交**

```bash
git add scripts/collapse_panel.py scripts/run_did.py && git commit -m "估计：折叠面板与第一层 DCDH"
```

**验收标准**：折叠行数为 308×12；三个估计量结果并列；两个结果变量方向一致（或不一致时已如实报告）。
**注意**：若切换城市不足 20 个，DCDH 的置信区间会极宽——**如实报告宽度，不要为了让结果显著而改口径**。

---

## Task 5：执法数据采集

**Files**
- Create: `data/enforcement.csv`, `scripts/merge_enforcement.py`

**Interfaces**
- Produces：`data/enforcement.csv`（列：city, year, cases, personnel_special, personnel_total, budget, source_url, caliber_note）

- [ ] **Step 1：按优先级采集三类数据**

对 Task 2 的 20 城，逐年检索：
```
<市名> 公安局 春节 安保 通报 出动警力 人次
<市名> 春节 烟花爆竹 查处 案件 起
<市名> 禁放工作经费 绩效评价 决算
```
- `cases`：查处案件数（**主口径**，一致性最好）
- `personnel_special`：明确标注"禁放专项"的出动人次
- `personnel_total`：全市春节安保总量（**单列，不混入**）
- `budget`：禁放工作经费（能查到才填）

- [ ] **Step 2：逐行填写口径备注**

`caliber_note` 必须写明该数字的口径来源。凡推测或换算得到的数字，标记为 `估计`。

- [ ] **Step 3：跑合并脚本，检查覆盖率**

```bash
python3 -I scripts/merge_enforcement.py
```
Expected：打印每城的三类数据覆盖年份数；**每城至少两类有值**。

- [ ] **Step 4：提交**

```bash
git add data/enforcement.csv scripts/merge_enforcement.py && git commit -m "执法数据：20 城三类口径"
```

**验收标准**：20 城中每城至少两类数据有值；`personnel_special` 与 `personnel_total` 未混用；每个数字都有 `source_url` 或标为 `估计`。

---

## Task 6：2×2 诊断

**Files**
- Create: `scripts/run_2x2.py`

**Interfaces**
- Consumes：`data/panel_cityyear.csv`（Task 4）、`data/enforcement.csv`（Task 5）

- [ ] **Step 1：定义两个维度**

- 横轴"尖峰是否被压住"：该城政策切换**后**的尖峰倍数相对切换**前**是否下降（下降幅度 ≥ 10% 算"压住"，阈值写进脚本常量，便于改）
- 纵轴"查处案件数高低"：该城该年在样本内的中位数以上 / 以下

- [ ] **Step 2：跑并输出格子分布**

```bash
python3 -I scripts/run_2x2.py
```
Expected：输出 2×2 的格子计数表 + 每格的城市列表。

- [ ] **Step 3：写解读**

对每格按 `docs/spec-研究设计.md` §5.3 的含义给出解读；**B 格（案件多但没压住）必须给出第三变量的分辨思路**（如违规规模、人口流出强度）。

- [ ] **Step 4：提交**

**验收标准**：四个格子都有城市落入（若某格为空，如实说明）；B 格有明确的进一步分辨方案。

---

## Task 7：ERA5 气象匹配

**Files**
- Create: `data/weather_era5.csv`

**Interfaces**
- Produces：`data/weather_era5.csv`（列：city, date, blh, wind10, temp2, rh, precip）

- [ ] **Step 1：注册并下载**

Copernicus CDS（<https://cds.climate.copernicus.eu/>）注册后下载 20 城所在格点的逐日：边界层高度、10 米风速、2 米温度、相对湿度、降水。

- [ ] **Step 2：匹配到城-日并检查覆盖率**

```bash
python3 -c "import csv;rows=list(csv.DictReader(open('data/weather_era5.csv',encoding='utf-8-sig')));print(len(rows))"
```
Expected：覆盖率（有气象值的城-日占比）≥ 90%。

- [ ] **Step 3：重做扩散条件检验**

用边界层高度与风速**替代**此前用的"基线 PM2.5"代理，重跑 §异质性检验，报告新的相关系数。这一步是为了修掉 spec §5.6 里承认的那个粗糙代理。

- [ ] **Step 4：提交**

**验收标准**：覆盖率 ≥ 90%；给出用气象变量的新 r 值，并与此前用基线浓度的 r = −0.21 / +0.24 并列对比。

---

## Task 8：成本收益

**Files**
- Create: `scripts/cost_benefit.py`

- [ ] **Step 1：建参数表**

每个参数一行：名称、取值、来源文献、页码或 DOI。**至少包含**：PM2.5 的剂量反应关系、统计生命价值（VSL）、暴露窗口的定义。剂量反应与 VSL 均须引用文献，不得自设。

- [ ] **Step 2：写计算脚本**

收益 = 污染减少量 × 剂量反应 × VSL；成本 = 三类执法数据（财政经费优先，其余作区间）。**罚款不计入社会成本**（转移支付）；警力、人力、设备计入。

- [ ] **Step 3：跑并输出情景表**

```bash
python3 -I scripts/cost_benefit.py
```
Expected：输出低/中/高三档情景下的成本收益比；每档标明参数来源与不确定来源。

- [ ] **Step 4：写缺口说明**

明确写出：工时统计系统性缺失（有一手证据：2011 年检察日报报道北京禁放投入约 286 万人次管控力量，同时写明"工时统计数字缺失"），因此本文给出的是**下界**。

- [ ] **Step 5：提交**

**验收标准**：参数表每个参数都有文献出处；三档情景均有结果；缺口说明有据可查。

---

## Task 9：交付

- [ ] **Step 1**：PPT 第一版（≤20 页，第一层结果 + 机制证据为主）
- [ ] **Step 2**：PPT 第二版（按老师意见修改）
- [ ] **Step 3**：论文正文（≤30 页，双倍行距、12 号字、边距 ≥1 英寸）
- [ ] **Step 4**：摘要（<300 词）
- [ ] **Step 5**：标题页贡献说明（列在摘要之前）
- [ ] **Step 6**：核对参考文献卷期页码与数据代码提交

**验收标准**：逐条对照 `docs/讨论提纲-与老师讨论稿.md` 与课程大纲的交付要求。

---

## 自检记录

- **spec 覆盖**：spec §3.2（待采数据）→ Task 5；§4（样本设计）→ Task 1/2/3；§5（变量与识别）→ Task 4/6；§6（成本收益）→ Task 8；§7 风险表中"扩散条件代理粗糙"→ Task 7。spec §9 九项待办与本计划 Task 1–9 一一对应，无遗漏。
- **占位符扫描**：无 TBD/TODO；每个任务均有具体命令与验收标准。
- **一致性检查**：`pm25_d1`/`pm25_win`/`pm25_base`/`spike_ratio`/`spike_increment` 五个变量名在 Task 4 定义、Task 6 使用，拼写一致；`personnel_special` 与 `personnel_total` 在 Task 5 定义并明确禁止混用。
- **Review Focus**：文首"最可能出错的六处"逐条落到了任务——1→Task 1，2→Task 1/2，3/4→Task 5，5→Task 3，6→Task 8。
