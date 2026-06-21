# AQuant Studio 项目总览

版本：MVP v0.1  
状态：可演示，禁止实盘  
市场范围：中国 A 股  

## 项目定位

AQuant Studio 是一个 A 股量化策略设计与研究平台 MVP。它允许用户基于模板或策略 DSL 定义交易规则，使用样例 A 股行情数据进行回测、可视化分析、参数优化和模拟盘验证。

当前项目不连接真实券商，不进行真实资金交易。

## 阶段索引

| 阶段 | 名称 | 核心文件 |
|---|---|---|
| 1 | 需求定义 | `quant-model-platform-prd.md` |
| 2 | 原型设计 | `prototype/index.html` |
| 3 | 数据模块 | `data_module/data-module-delivery.md` |
| 4 | 策略 DSL | `strategy_module/strategy-dsl-delivery.md` |
| 5 | 回测引擎 | `backtest_module/backtest-engine-delivery.md` |
| 6 | 策略模板库 | `template_module/template-library-delivery.md` |
| 7 | 可视化分析 | `visualization_module/visualization-delivery.md` |
| 8 | 参数优化 | `optimization_module/optimization-delivery.md` |
| 9 | 模拟盘 | `simulation_module/paper-trading-delivery.md` |
| 10 | 交易网关 | `trading_gateway_module/trading-gateway-delivery.md` |
| 11 | 安全合规 | `security_compliance_module/security-compliance-delivery.md` |
| 12 | MVP 发布 | `release_module/release-delivery.md` |

## 演示入口

打开：

```text
release_module/index.html
```

## V2 在线应用工程

阶段 1 已新增真正 Web App 工程骨架：

```text
web_app/
```

其中 `web_app/backend` 是 FastAPI 后端结构，`web_app/frontend` 是 React/Vite 前端结构。

## 关键结果

- 策略模板：5 个。
- 参数优化候选：36 个。
- 模拟盘订单：2 个。
- 安全合规状态：`blocked_for_live_trading`。

## 安全说明

本项目仅用于研究、学习、演示和沙箱验证。回测和模拟盘结果不代表未来收益。本项目不构成投资建议。
