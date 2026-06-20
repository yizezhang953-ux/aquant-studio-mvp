# 第六阶段交付物：A 股策略模板库

版本：v0.1  
阶段：第六阶段 - 策略模板库  
日期：2026-06-20  
前置依赖：

- 第三阶段：A 股行情数据模块。
- 第四阶段：策略 DSL。
- 第五阶段：回测引擎 MVP。

目标：提供一组可直接用于创建策略、校验和回测的 A 股策略模板，降低用户从零搭建策略的门槛。

## 1. 阶段范围

本阶段完成模板库 MVP。

已完成：

- 模板索引。
- 5 个 A 股策略模板。
- 模板管理脚本。
- 从模板生成策略 JSON。
- 批量校验模板。
- 批量运行模板回测。
- 输出每个模板的回测报告。

暂不包含：

- 图形化模板市场。
- 用户上传模板。
- 模板评分与收藏。
- 参数优化。
- 多标的模板。
- 实盘模板。

## 2. 交付文件

| 文件 | 说明 |
|---|---|
| `template_module/templates/index.json` | 模板库索引 |
| `template_module/templates/double_ma_trend.json` | 双均线趋势模板 |
| `template_module/templates/rsi_reversal.json` | RSI 波段反转模板 |
| `template_module/templates/price_breakout.json` | 价格突破模板 |
| `template_module/templates/volume_breakout.json` | 成交量突破模板 |
| `template_module/templates/return_momentum.json` | 收益率动量模板 |
| `template_module/template_manager.py` | 模板管理工具 |
| `template_module/generated_strategies/tpl_price_breakout_600519_SH_1d.json` | 从模板生成的策略实例 |
| `template_module/output/` | 批量回测输出目录 |
| `template_module/template-library-delivery.md` | 第六阶段交付说明 |

## 3. 模板列表

| 模板 ID | 名称 | 类型 | 风险等级 | 默认标的 | 默认频率 |
|---|---|---|---|---|---|
| `tpl_double_ma_trend` | 双均线趋势策略 | 趋势 | 中 | `600519.SH` | `1d` |
| `tpl_rsi_reversal` | RSI 波段反转策略 | 均值回归 | 中 | `000001.SZ` | `1d` |
| `tpl_price_breakout` | 价格突破策略 | 突破 | 中 | `600519.SH` | `1d` |
| `tpl_volume_breakout` | 成交量突破策略 | 突破 | 高 | `000001.SZ` | `15m` |
| `tpl_return_momentum` | 收益率动量策略 | 动量 | 中 | `300750.SZ` | `1d` |

## 4. 模板结构

每个模板本质上都是一个符合第四阶段 DSL 的策略 JSON：

```json
{
  "schema_version": "1.0",
  "strategy_id": "template_price_breakout",
  "name": "价格突破策略",
  "market": "a_share",
  "universe": {
    "type": "single",
    "symbols": ["600519.SH"]
  },
  "data": {},
  "entry": {},
  "exit": {},
  "position": {},
  "execution": {},
  "risk": {},
  "metadata": {
    "template_id": "tpl_price_breakout"
  }
}
```

这样前端可以直接读取模板 JSON，并把它填入策略编辑器。

## 5. 模板管理工具

工具文件：

```text
template_module/template_manager.py
```

### 5.1 查看模板列表

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' template_module\template_manager.py list
```

### 5.2 从模板创建策略

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' template_module\template_manager.py create tpl_price_breakout --symbol 600519.SH --frequency 1d --output-dir template_module\generated_strategies
```

已生成：

```text
template_module\generated_strategies\tpl_price_breakout_600519_SH_1d.json
```

### 5.3 批量校验模板

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' template_module\template_manager.py validate-all --db data_module\market_data.sqlite
```

校验内容：

- 策略 DSL 是否有效。
- A 股市场边界是否满足。
- 股票代码格式是否正确。
- 指标和操作符是否在白名单内。
- 仓位与风控参数是否合理。
- 行情数据是否覆盖模板区间。

### 5.4 批量回测模板

```powershell
& 'C:\Users\huawei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' template_module\template_manager.py backtest-all --db data_module\market_data.sqlite --output-dir template_module\output
```

输出目录：

```text
template_module\output\
```

每个模板会生成：

- `report.json`
- `trades.csv`
- `equity_curve.csv`

## 6. 验证结果

批量校验结果：

| 模板 | 校验结果 | 数据覆盖 |
|---|---|---|
| 双均线趋势策略 | 通过 | 5 根日线 |
| RSI 波段反转策略 | 通过 | 5 根日线 |
| 价格突破策略 | 通过 | 5 根日线 |
| 成交量突破策略 | 通过 | 5 根 15 分钟线 |
| 收益率动量策略 | 通过 | 5 根日线 |

批量回测结果：

| 模板 | 交易次数 | 总收益率 | 说明 |
|---|---:|---:|---|
| 双均线趋势策略 | 0 | 0.0000% | 样例数据少于 MA20 窗口 |
| RSI 波段反转策略 | 0 | 0.0000% | 样例数据少于 RSI14 窗口 |
| 价格突破策略 | 1 | -0.2785% | 完整买入卖出闭环 |
| 成交量突破策略 | 0 | -0.0160% | 有未平仓持仓，权益按收盘价盯市 |
| 收益率动量策略 | 0 | 0.0000% | 未触发完整交易 |

注意：当前样例行情数据很短，回测结果只用于验证系统链路，不代表真实策略表现。

## 7. 与前端原型的衔接

第二阶段原型中的“从模板创建”按钮后续可接入：

1. 读取 `template_module/templates/index.json`。
2. 在模板库页面展示模板卡片。
3. 用户选择模板。
4. 系统读取模板 JSON。
5. 将模板 JSON 填入策略编辑器。
6. 用户修改股票代码、频率、参数、仓位和风控。
7. 保存为用户自己的策略。

模板卡片建议展示：

- 模板名称。
- 策略类型。
- 风险等级。
- 默认频率。
- 核心规则摘要。
- 使用模板按钮。

## 8. 后续扩展

下一步可扩展：

- 模板参数说明，例如 MA 快线周期、慢线周期。
- 模板默认适用场景。
- 模板风险提示。
- 模板历史回测摘要。
- 用户自定义模板。
- 模板版本管理。
- 模板收藏和复制次数统计。

## 9. 第六阶段结论

第六阶段已经完成 A 股策略模板库 MVP。现在产品可以做到：

1. 用户不必从零开始写策略。
2. 模板可以直接进入策略编辑器。
3. 模板可以被统一校验。
4. 模板可以批量回测。
5. 模板库已经和前三个核心模块形成闭环：行情数据、策略 DSL、回测引擎。

下一阶段建议进入“回测报告可视化”，把第五阶段和第六阶段产生的 `report.json`、`trades.csv`、`equity_curve.csv` 展示到 Web 页面中。
