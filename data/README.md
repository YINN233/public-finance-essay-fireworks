# data/

本目录存放数据。**除本文件与 `samples/` 下的两个单日样例，其余文件均不入库**（见上级 `.gitignore`）。

```
data/
├── README.md                  本文件
├── samples/                   入库：两个单日原始样例，供了解文件格式
├── raw/                       不入库：全量原始单日文件（180 个，约 73 MB），由脚本生成
├── panel_cityday.csv          不入库：城市 × 日 面板（63,515 行）
├── panel_hourly_focus.csv     不入库：聚焦城市逐小时长表
├── panel_with_policy.csv      不入库：面板并入政策变量后的分析数据
└── coverage_city_year.csv     不入库：城市 × 年份 在场矩阵（覆盖率诊断产物）
```

四类产物全部可由脚本重新生成（下载约 20 分钟，其余各在数十秒内）：

```bash
python3 -u scripts/download_aqi.py     # → data/raw/
python3 -I scripts/build_panel.py      # → panel_cityday.csv、panel_hourly_focus.csv
python3 -I scripts/check_coverage.py   # → coverage_city_year.csv
python3 -I scripts/merge_policy.py     # → panel_with_policy.csv（需先填 policy/policy.csv）
```

## 入库的两个样例

- `data/samples/china_cities_20190204.csv`（2019 年除夕）
- `data/samples/china_cities_20250128.csv`（2025 年除夕）

原始文件取自 <https://quotsoft.net/air/data/china_cities_YYYYMMDD.csv>；该站数据来自
中国环境监测总站"全国城市空气质量实时发布平台"。

**格式**：UTF-8；361 行 × 378 列；列 = `date,hour,type,<城市名>…`；行 = 24 小时 × 15 种污染物
（AQI、PM2.5、PM10、SO₂、NO₂、O₃、CO 及各自的 24 小时滚动均值）。

**不要用 GBK 转码**——文件本身就是 UTF-8，转码会把中文列名变成乱码。

## 三个必须注意的坑

1. **地区行署城市用的是地区名**。数据中为「**阿克苏地区**」，不是「阿克苏市」；喀什同理。
2. **南疆城市的 AQI 与 PM10 受沙尘污染，不能作结果变量**。实测阿克苏的 PM2.5/PM10 比值全天在 0.17–0.31（粗颗粒主导），其 AQI 曾被 PM10 拉高至 409 而 PM2.5 仅 131。对南疆各市**必须用 PM2.5**。
3. **数据起始于 2014-05-13**，因此春节窗口从 2015 年开始，2014 年春节不可得。
