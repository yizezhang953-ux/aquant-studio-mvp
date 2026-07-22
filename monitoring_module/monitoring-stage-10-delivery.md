# 实盘应用阶段十交付物：监控与告警

版本：v0.2-stage-10  
阶段：实盘应用路线阶段十  
状态：已完成本地实现  

## 1. 阶段目标

阶段十提供一个轻量监控汇总器，读取交易网关、影子交易、限额自动化和只读账户同步结果，输出健康状态和告警列表。

## 2. 新增文件

| 文件 | 说明 |
|---|---|
| `monitoring_module/monitor.py` | 监控汇总器 |
| `monitoring_module/configs/monitoring_config.json` | 监控输入配置 |
| `monitoring_module/monitoring-stage-10-delivery.md` | 阶段十交付说明 |

## 3. 当前能力

- 检查网关最新订单状态。
- 检查影子交易不可行订单。
- 检查限额自动化候选订单。
- 检查只读账户同步模式。
- 检测 live submission 异常开启。
- 输出 `ok / warning / critical` 状态。

## 4. 验收命令

```powershell
python monitoring_module\monitor.py --config monitoring_module\configs\monitoring_config.json --output monitoring_module\output\stage10_monitor_report.json
```

## 5. 验收结果

| 场景 | 结果 |
|---|---|
| 读取阶段五网关输出 | 通过 |
| 读取阶段七影子报告 | 通过 |
| 读取阶段九候选订单 | 通过 |
| 读取阶段六只读账户 | 通过 |

## 6. 下一阶段

下一阶段进入：

```text
阶段十一：审计与合规
```

重点补充：

- 关键产物清单。
- 文件哈希。
- 策略/订单/审批/风控可追溯。
- 最终实盘检查基础材料。
