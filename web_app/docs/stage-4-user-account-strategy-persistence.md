# 阶段 4 交付物：用户账户与策略持久化

版本：V2.1 Stage 4  
日期：2026-06-21  
状态：已完成用户账户、登录会话、用户策略保存、编辑、删除和版本记录。

## 1. 阶段目标

让 AQuant Studio 从“系统演示 API”进入“用户可保存自己策略”的状态。用户可以注册账户、登录、保存从模板派生或自主编辑的策略，并在后续继续修改和管理。

## 2. 已交付内容

- 用户模型：`users`
- 登录会话模型：`user_sessions`
- 用户策略归属：`user_strategies.owner_id`
- 策略版本模型：`strategy_versions`
- 认证服务：`app/services/auth_service.py`
- 策略持久化服务：`app/services/strategy_repository.py`
- 认证 API：`/api/v1/auth/*`
- 策略管理 API：`/api/v1/strategies`
- 数据库轻量迁移：已有 SQLite 会自动补充新字段
- 测试用例：注册、登录、保存策略、编辑策略、版本查询、删除策略

## 3. 新增 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/register` | 注册用户并返回 token |
| POST | `/api/v1/auth/login` | 登录并返回 token |
| GET | `/api/v1/auth/me` | 获取当前登录用户 |
| POST | `/api/v1/auth/logout` | 注销当前用户会话 |
| GET | `/api/v1/strategies` | 查询当前用户策略列表 |
| POST | `/api/v1/strategies` | 保存一个新策略 |
| GET | `/api/v1/strategies/{strategy_id}` | 查询单个策略 |
| PUT | `/api/v1/strategies/{strategy_id}` | 更新策略名称、状态或策略 JSON |
| DELETE | `/api/v1/strategies/{strategy_id}` | 删除策略 |
| GET | `/api/v1/strategies/{strategy_id}/versions` | 查询策略版本记录 |

## 4. 使用方式

注册：

```json
POST /api/v1/auth/register
{
  "email": "demo@example.com",
  "password": "strong-password-123",
  "display_name": "Demo User"
}
```

保存策略时需要带上登录返回的 token：

```text
Authorization: Bearer <access_token>
```

保存策略：

```json
POST /api/v1/strategies
{
  "name": "My breakout strategy",
  "source_template_id": "tpl_price_breakout",
  "strategy": {
    "schema_version": "1.0",
    "strategy_id": "template_price_breakout",
    "market": "a_share"
  }
}
```

实际调用时 `strategy` 需要传入完整策略 JSON。前端可以先通过：

```text
GET /api/v1/templates/tpl_price_breakout
```

获取模板策略，再提交保存。

## 5. 安全边界

当前阶段实现的是本地可用的账户与会话系统：

- 密码使用 PBKDF2-SHA256 加盐哈希保存。
- token 存储在数据库 `user_sessions` 中。
- 策略接口必须携带 Bearer token。
- 每个用户只能访问自己的策略。
- 实盘交易仍然保持禁用状态。

正式线上部署前建议升级：

- 使用 HTTPS。
- 使用成熟认证方案，如 JWT 加刷新 token，或第三方 OAuth。
- 增加登录频率限制和审计告警。
- 增加邮箱验证和找回密码流程。

## 6. 验收标准

- 用户可注册并登录。
- 未登录用户不能访问策略管理接口。
- 登录用户可以保存、编辑、查看、删除自己的策略。
- 策略每次修改 JSON 时生成版本记录。
- 已有 SQLite 数据库可自动补充新增字段。
- 自动化测试通过。

## 7. 下一阶段建议

阶段 5 建议连接前端：把注册、登录、模板复制、策略列表、策略编辑器和策略版本历史做成真实可点击的界面。
