# 阶段 2 交付物：后端 API MVP

版本：V2.1 Stage 2  
日期：2026-06-21  
状态：已实现同步 FastAPI API MVP。

## 1. 阶段目标

把现有静态 MVP 的核心能力包装成后端 API，为后续在线应用提供真实服务入口。

已完成：

- 模板列表 API。
- 单个模板详情 API。
- 策略校验 API。
- 回测运行 API。
- 回测报告查询 API。
- 安全状态 API。
- 后端测试用例。

## 2. 已实现 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 服务健康检查 |
| GET | `/api/v1/system` | 系统信息 |
| GET | `/api/v1/security/status` | 安全状态，实盘仍阻断 |
| GET | `/api/v1/templates` | 获取模板库索引 |
| GET | `/api/v1/templates/{template_id}` | 获取模板详情和策略 JSON |
| POST | `/api/v1/strategies/validate` | 校验策略 JSON |
| POST | `/api/v1/backtests` | 同步运行回测 |
| GET | `/api/v1/backtests/{backtest_id}` | 获取回测报告 |
| GET | `/api/v1/backtests/{backtest_id}/report` | 获取回测报告 |

## 3. 回测运行请求

```json
{
  "strategy": {
    "schema_version": "1.0",
    "strategy_id": "template_price_breakout",
    "market": "a_share"
  }
}
```

实际请求需要传入完整策略 JSON。前端可以先通过：

```text
GET /api/v1/templates/tpl_price_breakout
```

拿到模板策略，再提交到：

```text
POST /api/v1/backtests
```

## 4. 回测输出位置

阶段 2 暂时使用文件作为运行时存储：

```text
web_app/backend/runtime/backtests/{backtest_id}/
  report.json
  trades.csv
  equity_curve.csv
  strategy.json
```

阶段 3 会把这些运行结果迁移到数据库。

## 5. 启动后端

安装依赖：

```powershell
cd web_app/backend
python -m pip install -e .[dev]
```

启动：

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

打开：

```text
http://localhost:8000/docs
```

## 6. 测试

```powershell
cd web_app/backend
python -m pytest
```

## 7. 当前限制

- 回测 API 目前是同步执行。
- 尚未接 PostgreSQL。
- 尚未有用户系统。
- 尚未做任务队列。
- 仍使用已有 MVP 文件模块作为业务逻辑来源。

## 8. 下一阶段

阶段 3：数据库设计与迁移。

建议迁移表：

- templates
- strategies
- backtest_runs
- trades
- equity_curve
- audit_logs
