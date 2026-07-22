# 实盘应用阶段六交付物：账户只读接入骨架

版本：v0.2-stage-6  
阶段：实盘应用路线阶段六  
状态：已完成本地实现，未连接真实券商  

## 1. 阶段目标

阶段六建立真实账户只读接入的安全骨架。当前实现使用本地快照模拟券商只读返回，未来接真实券商时必须保持默认禁止下单。

## 2. 新增文件

| 文件 | 说明 |
|---|---|
| `broker_adapter_module/read_only_broker_adapter.py` | 只读券商适配器 |
| `broker_adapter_module/account_sync.py` | 账户快照同步命令 |
| `broker_adapter_module/configs/read_only_broker_snapshot.json` | 只读账户快照样例 |
| `broker_adapter_module/read-only-account-stage-6-delivery.md` | 阶段六交付说明 |

## 3. 当前能力

- 查询账户资金。
- 查询持仓数量。
- 查询持仓详情。
- 查询委托。
- 查询成交。
- 导出标准化账户快照。
- 明确拒绝下单。
- 撤单接口为只读 no-op。

## 4. 验收命令

同步只读账户：

```powershell
python broker_adapter_module\account_sync.py --snapshot broker_adapter_module\configs\read_only_broker_snapshot.json --output broker_adapter_module\output\stage6_read_only_account_snapshot.json
```

验证只读下单拒绝：

```powershell
python -c "from pathlib import Path; from broker_adapter_module.read_only_broker_adapter import ReadOnlyBrokerAdapter; from types import SimpleNamespace; a=ReadOnlyBrokerAdapter(Path('broker_adapter_module/configs/read_only_broker_snapshot.json')); ack, fill=a.submit_order(SimpleNamespace(gateway_order_id='GW-TEST')); print(ack.status, ack.message, fill)"
```

## 5. 验收结果

| 场景 | 结果 |
|---|---|
| 账户同步 | 通过 |
| 持仓标准化 | 通过 |
| 只读适配器下单 | 拒绝 |

## 6. 下一阶段

下一阶段进入：

```text
阶段七：影子交易
```

重点补充：

- 策略理论订单。
- 真实账户只读快照对比。
- 不下单的交易可行性报告。
- 风控预检查报告。
