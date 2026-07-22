# 实盘应用阶段四交付物：事件驱动模拟盘升级

版本：v0.2-stage-4  
阶段：实盘应用路线阶段四  
状态：已完成本地实现，仍禁止真实实盘  

## 1. 阶段目标

阶段四将模拟盘从简单结果生成升级为事件驱动模型，尽量贴近真实交易链路中的订单、成交、撤单和账户变化。

## 2. 新增文件

| 文件 | 说明 |
|---|---|
| `simulation_module/event_driven_paper_trader.py` | 事件驱动模拟盘引擎 |
| `simulation_module/configs/event_driven_demo.json` | A 股 + 港股混合模拟配置 |
| `simulation_module/event-driven-paper-stage-4-delivery.md` | 阶段四交付说明 |

## 3. 当前能力

- 订单提交事件。
- 市场规则校验。
- A 股与港股费用模型复用。
- 全成交。
- 部分成交。
- 部分成交后撤单。
- 账户资金和持仓快照。
- CSV 与 JSON 输出。

## 4. 输出文件

运行后输出：

| 文件 | 说明 |
|---|---|
| `simulation_report.json` | 完整模拟报告 |
| `orders.csv` | 模拟订单 |
| `fills.csv` | 模拟成交 |
| `events.csv` | 事件流水 |
| `account_snapshots.csv` | 账户快照 |

## 5. 验收命令

```powershell
python simulation_module\event_driven_paper_trader.py --config simulation_module\configs\event_driven_demo.json --output-dir simulation_module\output\stage4_event_driven_verify
```

## 6. 验收结果

| 场景 | 结果 |
|---|---|
| A 股 600519.SH 买入 100 股 | 全成交 |
| 港股 00700.HK 买入 200 股 | 成交 100 股，剩余 100 股撤单 |
| 账户快照 | 正常生成 |
| 事件流水 | 包含提交、成交、撤单 |

## 7. 下一阶段

下一阶段进入：

```text
阶段五：Broker Adapter 抽象
```

重点补充：

- 统一券商接口。
- 沙箱适配器迁移到统一接口。
- 只读适配器接口预留。
- 未来真实券商适配器禁止绕过网关。
