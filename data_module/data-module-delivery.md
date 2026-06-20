# 第三阶段交付物：A 股行情数据模块

版本：v0.1  
阶段：第三阶段 - 数据模块  
日期：2026-06-20  
目标：打通 A 股行情数据的导入、存储、查询和覆盖检查流程，为后续策略回测引擎提供稳定数据接口。

## 1. 阶段范围

本阶段聚焦数据模块 MVP，不接入实盘交易，不实现完整回测引擎。

已确认初版市场范围：

- 中国 A 股。
- 单标的历史行情。
- 日线、60 分钟、30 分钟、15 分钟。
- OHLCV 行情数据。
- 支持前复权、后复权、不复权字段预留。

本阶段实际打通：

- SQLite 行情数据库。
- A 股股票基础信息表。
- K 线行情表。
- 数据导入记录表。
- CSV 样例数据导入。
- 查询接口。
- 数据覆盖健康检查。

## 2. 交付文件

| 文件 | 说明 |
|---|---|
| `data_module/schema.sql` | SQLite 数据库表结构 |
| `data_module/market_data.py` | 数据模块命令行工具和核心接口 |
| `data_module/sample_data/a_share_daily_sample.csv` | A 股日线样例数据 |
| `data_module/sample_data/a_share_15m_sample.csv` | A 股 15 分钟线样例数据 |
| `data_module/market_data.sqlite` | 已初始化并导入样例数据的 SQLite 数据库 |
| `data_module/data-module-delivery.md` | 第三阶段交付说明 |

## 3. 数据模型

### 3.1 instruments 股票基础信息表

用于存储 A 股标的基础信息。

| 字段 | 类型 | 说明 |
|---|---|---|
| symbol | TEXT | 股票代码，如 `600519.SH` |
| name | TEXT | 股票名称 |
| market | TEXT | 固定为 `a_share` |
| exchange | TEXT | `SH` 或 `SZ` |
| asset_type | TEXT | 初版固定为 `stock` |
| listed_date | TEXT | 上市日期，预留 |
| status | TEXT | active / inactive |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

### 3.2 bars K 线行情表

用于存储不同频率的 OHLCV 数据。

| 字段 | 类型 | 说明 |
|---|---|---|
| symbol | TEXT | 股票代码 |
| frequency | TEXT | `1d`、`60m`、`30m`、`15m` |
| trade_time | TEXT | 交易日期或 K 线结束时间 |
| open | REAL | 开盘价 |
| high | REAL | 最高价 |
| low | REAL | 最低价 |
| close | REAL | 收盘价 |
| volume | REAL | 成交量 |
| amount | REAL | 成交额 |
| adj_factor | REAL | 复权因子 |
| source | TEXT | 数据来源 |

唯一约束：

```text
symbol + frequency + trade_time
```

这保证同一股票、同一频率、同一时间点不会重复插入。

### 3.3 data_loads 数据导入记录表

用于记录每次数据导入任务。

| 字段 | 类型 | 说明 |
|---|---|---|
| source | TEXT | 数据来源 |
| symbol | TEXT | 股票代码 |
| frequency | TEXT | 数据频率 |
| started_at | TEXT | 开始时间 |
| finished_at | TEXT | 完成时间 |
| row_count | INTEGER | 导入行数 |
| status | TEXT | running / completed / failed |
| error_message | TEXT | 失败原因 |

## 4. CSV 数据格式

CSV 必须包含以下字段：

```text
symbol,name,market,exchange,frequency,trade_time,open,high,low,close,volume,amount,adj_factor,source
```

示例：

```csv
600519.SH,贵州茅台,a_share,SH,1d,2024-01-02,1685.00,1698.80,1668.10,1682.50,3021450,5082100000,1.0,sample
```

## 5. 命令用法

以下命令使用 Codex 内置 Python 运行时验证通过。若本机已安装 Python，也可将命令中的 Python 路径替换为 `python`。

### 5.1 初始化数据库

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' data_module\market_data.py --db data_module\market_data.sqlite init
```

### 5.2 导入日线样例数据

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' data_module\market_data.py --db data_module\market_data.sqlite import-csv data_module\sample_data\a_share_daily_sample.csv
```

### 5.3 导入 15 分钟线样例数据

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' data_module\market_data.py --db data_module\market_data.sqlite import-csv data_module\sample_data\a_share_15m_sample.csv
```

### 5.4 查询行情

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' data_module\market_data.py --db data_module\market_data.sqlite query --symbol 600519.SH --frequency 1d --start 2024-01-02 --end 2024-01-08
```

### 5.5 查看数据覆盖

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' data_module\market_data.py --db data_module\market_data.sqlite health
```

## 6. 已实现校验

导入时会校验：

- 市场必须为 `a_share`。
- 频率必须为 `1d`、`60m`、`30m`、`15m` 之一。
- 股票代码必须以 `.SH` 或 `.SZ` 结尾。
- 交易所必须为 `SH` 或 `SZ`。
- 开高低收价格必须为正数。
- 最高价不能低于开盘、收盘、最低价。
- 最低价不能高于开盘、收盘、最高价。
- 成交量和成交额不能为负数。

## 7. 查询接口返回格式

查询结果返回 JSON 数组，示例：

```json
[
  {
    "symbol": "600519.SH",
    "frequency": "1d",
    "trade_time": "2024-01-02",
    "open": 1685.0,
    "high": 1698.8,
    "low": 1668.1,
    "close": 1682.5,
    "volume": 3021450.0,
    "amount": 5082100000.0,
    "adj_factor": 1.0,
    "source": "sample"
  }
]
```

后续回测引擎可以直接按 `symbol + frequency + start + end` 获取 K 线序列。

## 8. 当前样例数据覆盖

| 股票 | 频率 | 行数 |
|---|---:|---:|
| 600519.SH 贵州茅台 | 日线 | 5 |
| 000001.SZ 平安银行 | 日线 | 5 |
| 300750.SZ 宁德时代 | 日线 | 5 |
| 600519.SH 贵州茅台 | 15 分钟 | 5 |
| 000001.SZ 平安银行 | 15 分钟 | 5 |

## 9. 后续真实数据源接入方案

第三阶段已完成本地数据链路。真实数据源建议在下一轮迭代接入：

| 数据源 | 特点 | 适合阶段 |
|---|---|---|
| AkShare | 免费、易上手、适合原型 | MVP / 内测 |
| TuShare Pro | 数据较全，需要 token | MVP / 正式版 |
| Wind / 同花顺 iFinD | 专业、稳定、成本高 | 商业版 |
| 券商行情接口 | 接近实盘交易环境 | 模拟盘 / 实盘前 |

建议先接入 AkShare 或 TuShare Pro，并把外部数据统一转换为当前 CSV / Bar 结构后再入库，避免回测引擎依赖具体供应商。

## 10. 第三阶段结论

第三阶段已经完成数据模块 MVP：

1. A 股行情数据可以被导入。
2. 数据可以被结构化存储。
3. 数据可以按股票、频率和时间区间查询。
4. 数据覆盖情况可以被检查。
5. 后续回测引擎可以直接依赖本模块。

下一阶段建议进入“策略 DSL / 编辑器数据结构”或“回测引擎”开发。若严格按照原计划，第四阶段应完成策略规则 JSON 与编辑器逻辑；若想更快看到策略结果，也可以先做一个最小回测引擎。
