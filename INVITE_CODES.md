> **注意**
>
> - 本文档中出现的所有邀请码均为占位示例，并非真实可用的码。实际的邀请码由服务
>   启动时随机生成，请勿将真实邀请码提交到代码仓库。
> - `dev-unlimited` / `test-unlimited` / `demo-user` 这三个固定码硬编码在源码里，
>   属于公开已知值。它们**默认不再创建**，仅在设置 `SEED_DEV_INVITE_CODES=true`
>   时用于本地开发。生产环境请保持关闭。
> - 出于同样的原因，启动日志默认只打印邀请码**数量**，不再打印码本身。

# Invite Codes 说明

## 启动日志

API 服务启动时会自动打印所有可用的 invite codes：

```
================================================================================
AVAILABLE INVITE CODES:

  Permanent (unlimited use):
    • dev-unlimited
    • test-unlimited
    • demo-user

  Regular (single use, expires in 30 days):
    • aBcD1234
    • eFgH5678
    • iJkL9012
    ...
================================================================================
```

## Invite Code 类型

### 1. 永久 Codes (Permanent)

| Code | 用途 | 最大使用次数 | 过期时间 |
|------|------|-------------|---------|
| `dev-unlimited` | 开发环境无限使用 | 999,999 | 永不过期 |
| `test-unlimited` | 测试环境无限使用 | 999,999 | 永不过期 |
| `demo-user` | 演示账户 | 999,999 | 永不过期 |

**特点**:
- 无过期时间 (`expires_at = NULL`)
- 接近无限使用次数 (`max_uses = 999999`)
- 自动创建，首次启动时生成
- 适合开发、测试、演示使用

### 2. 普通 Codes (Regular)

**特点**:
- 单次使用 (`max_uses = 1`)
- 30 天后过期
- 自动维护 10 个可用 codes
- 使用后自动补充新 codes

**生成规则**:
- 使用 `secrets.token_urlsafe(6)` 生成
- 示例: `aBcD1234`, `eFgH5678`, `iJkL9012`

## 自动管理机制

### 启动时自动检查

1. **创建永久 codes**: 如果 `dev-unlimited`, `test-unlimited`, `demo-user` 不存在，自动创建
2. **维护普通 codes 数量**: 确保始终有 10 个可用的普通 codes
3. **打印所有可用 codes**: 分类显示永久和普通 codes

### 使用后自动补充

当普通 codes 被使用后，下次启动时会自动补充到 10 个。

## 使用场景

### 开发环境
使用 `dev-unlimited` - 本地开发时无限注册测试账户

### 测试环境
使用 `test-unlimited` - CI/CD 自动化测试时注册账户

### 演示环境
使用 `demo-user` - 给客户、投资人演示时注册账户

### 生产环境
使用普通 codes - 真实用户注册，单次使用后失效

## 数据库查询

### 查看所有可用 codes
```sql
SELECT code, max_uses, used_count, expires_at
FROM invite_codes
WHERE used_count < max_uses
  AND (expires_at IS NULL OR expires_at > NOW())
ORDER BY expires_at NULLS FIRST;
```

### 查看永久 codes
```sql
SELECT code, max_uses, used_count
FROM invite_codes
WHERE expires_at IS NULL;
```

### 查看使用统计
```sql
SELECT
  CASE WHEN expires_at IS NULL THEN 'Permanent' ELSE 'Regular' END as type,
  COUNT(*) as total_codes,
  SUM(used_count) as total_uses,
  SUM(max_uses - used_count) as remaining_uses
FROM invite_codes
GROUP BY CASE WHEN expires_at IS NULL THEN 'Permanent' ELSE 'Regular' END;
```

## 手动管理

### 创建新的永久 code
```sql
INSERT INTO invite_codes (id, code, max_uses, expires_at, created_at)
VALUES (
  gen_random_uuid()::text,
  'custom-permanent',
  999999,
  NULL,
  NOW()
);
```

### 创建新的单次 code
```sql
INSERT INTO invite_codes (id, code, max_uses, expires_at, created_at)
VALUES (
  gen_random_uuid()::text,
  'custom-single',
  1,
  NOW() + INTERVAL '30 days',
  NOW()
);
```

### 禁用某个 code
```sql
UPDATE invite_codes
SET used_count = max_uses
WHERE code = 'code-to-disable';
```

## API 使用

### 验证 invite code
```bash
POST /api/auth/invites/validate
{
  "code": "dev-unlimited"
}
```

### 查看可用 codes (需要管理员权限)
```bash
GET /api/auth/invites
```

## 安全建议

1. **生产环境**: 不要使用永久 codes，仅使用单次普通 codes
2. **开发环境**: 可以使用 `dev-unlimited` 方便开发
3. **测试环境**: 使用 `test-unlimited` 用于自动化测试
4. **定期清理**: 定期清理过期的 codes 以保持数据库整洁

```sql
DELETE FROM invite_codes
WHERE expires_at IS NOT NULL
  AND expires_at < NOW()
  AND used_count >= max_uses;
```
