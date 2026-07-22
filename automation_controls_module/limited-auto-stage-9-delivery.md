# 实盘应用阶段九交付物：小资金限额自动化守门器

版本：v0.2-stage-9  
阶段：实盘应用路线阶段九  
状态：已完成本地实现，不开启真实自动下单  

## 1. 阶段目标

阶段九在人工确认订单之后增加限额自动化守门器。通过守门器的订单只会成为自动化候选，仍然不会绕过交易网关、风控和券商适配器。

## 2. 新增文件

| 文件 | 说明 |
|---|---|
| `automation_controls_module/limited_auto_guard.py` | 限额自动化守门器 |
| `automation_controls_module/configs/limited_auto_policy.json` | 限额自动化策略 |
| `automation_controls_module/limited-auto-stage-9-delivery.md` | 阶段九交付说明 |

## 3. 当前能力

- 全局 kill switch。
- 标的白名单。
- 来源白名单。
- 必须人工审批。
- 单笔金额上限。
- 单日订单数量上限。
- 单日订单金额上限。
- 输出候选订单和拒绝订单。

## 4. 验收命令

```powershell
python automation_controls_module\limited_auto_guard.py --orders manual_confirmation_module\output\stage8_manual_confirmation_result.json --policy automation_controls_module\configs\limited_auto_policy.json --output automation_controls_module\output\stage9_limited_auto_candidates.json
```

## 5. 验收结果

| 场景 | 结果 |
|---|---|
| 港股 approved order | 通过，成为候选 |
| 是否真实提交 | 否 |
| 是否绕过网关 | 否 |

## 6. 下一阶段

下一阶段进入：

```text
阶段十：监控与告警
```

重点补充：

- 读取网关/模拟/影子交易输出。
- 检测拒单、失败、熔断、亏损和异常。
- 输出监控报告。
- 为前端监控面板预留数据结构。
