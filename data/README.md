# data/

本目录存放空气质量数据。**除本文件与两个单日样例（见下）外，其余文件均不入库**（见上级 `.gitignore`）。

## 为什么不全入库

全量春节窗口数据约 180 个文件、10–30MB，且可用脚本在 30–60 分钟内重新生成，因此不纳入版本管理。需要数据时执行：

```bash
python3 -I scripts/download_aqi.py              # 全量：2015–2026 共 12 个春节窗口
python3 -I scripts/download_aqi.py --years 2025 # 只拉某一年
python3 -I scripts/download_aqi.py --test       # 只下 2 天，验证通路
```

输出：`data/aqi_cny_window.csv`（长表 `date, year, rel_day, hour, city, pollutant, value`）

## 入库的两个样例

- `raw_china_cities_20190204.csv` —— 2019 年除夕（农历己亥年）
- `raw_china_cities_20250128.csv` —— 2025 年除夕（农历乙巳年）

原始单日文件来自 <https://quotsoft.net/air/data/china_cities_YYYYMMDD.csv>
（该站数据取自中国环境监测总站"全国城市空气质量实时发布平台"）。

**格式**：UTF-8 编码；361 行 × 378 列；列 = `date,hour,type,<城市名>…`；行 = 24 小时 × 15 种污染物。
**不要用 GBK 转码**——文件本身就是 UTF-8，转码会把中文列名转坏。

## 三个必须注意的坑

1. **地区行署城市用的是地区名**：数据中为「**阿克苏地区**」，不是「阿克苏市」；喀什同理。
2. **南疆城市的 AQI / PM10 受沙尘污染，不能作结果变量**。阿克苏的 PM2.5/PM10 比值全天在 0.17–0.31（粗颗粒主导），其 AQI 曾被 PM10 拉高到 409 而 PM2.5 仅 131。对南疆各市**必须用 PM2.5**。详见上级 `README.md` §1.4。
3. **数据起始于 2014-05-13**，因此春节窗口从 2015 年开始，2014 年春节不可得。
