# OAuth/OIDC 接入配置清单

> 依据：SSO-doc 中 WIS 的 OIDC 接入记录（2025-08 至 2025-10）。
> Okta 的界面名称和选项以实际租户版本为准，提交前需与 Okta 管理员核对。
> 本文不包含任何 Client Secret 或其他凭据。

## 一、申请入口（按顺序）

| 步骤 | 入口 | 说明 |
|---|---|---|
| 1. 启动 onboarding | ServiceNow 目录项：`https://logitech.service-now.com/sp?id=sc_cat_item&sys_id=3ef09c0587a69a502a58ece80cbb357f` | WIS 在 2025-08-01 通过此目录项启动流程。 |
| 2. 提交应用信息 | ServiceNow 表单 `u_okta_application`（从步骤 1 进入） | 不要直接复用 WIS 的记录链接（其中 sys_id 指向具体记录）。 |
| 3. 建立工单 | JIRA：`https://jira.logitech.com`，建立 SSO 接入工单 | WIS 使用的是 ITSM-428810。Okta 团队要求必须有工单号。 |
| 4. 隐私与供应商评估 | OneTrust ID、Vendor assessment ID | 文档中只有 WIS 的编号（#3998、VA-00980），申请入口需向隐私或供应商管理团队确认。 |
| 5. 业务负责人审批 | 确认应用 owner 与访问审批问题 | WIS 的 owner 为 Roger Zheng，审批问题为"请说明申请访问的原因"。 |

历史对接人（2025 年，需确认是否仍在岗）：Giridharan Dakshinamurthy（Okta 配置）、Dhanush Sha（协调、JIRA）、Yu Tang（测试）。

## 二、提交给 Okta 团队的信息

### 应用基本信息
- [ ] 应用名称（如 `Warehouse Intelligence System`）
- [ ] 应用图标（logo 文件）
- [ ] 应用简介、使用目的、使用团队
- [ ] 业务负责人（姓名、工号、邮箱）
- [ ] 用户开通与停用流程（如：JIRA 工单 + 主管 + owner 审批）
- [ ] 复核周期（如 6 个月）

### 环境信息（dev 与 prod 分开列）
本模板的路径是固定的，只需把 `<域名>` 换成实际域名：

| 项目 | 填写值 | 说明 |
|---|---|---|
| 应用域名（CNAME） | `<dev 域名>`、`<prod 域名>` | 如 `wis-dev.xxx` 与 `wis.xxx` |
| Sign-in redirect URI | `https://<域名>/api/auth/callback/` | 需完全一致，包括末尾斜杠。PC 与 PDA 访问同一个 Web 应用时共用此地址 |
| Sign-out redirect URI | `https://<域名>/` | 登出 IdP 后回到的地址 |
| Initiate login URI（Okta 门户点击图标时打开） | `https://<域名>/api/auth/login/` | 用于让应用出现在 Okta Dashboard |

- [ ] 以上各项 dev 与 prod 各一份
- [ ] 若有独立的 PDA 程序（不是同一个 Web 应用），其回调地址单独列出

### OIDC 参数
- [ ] 应用类型：**Web application**（confidential client，后端持有 Client Secret）。不要选 SPA
- [ ] Grant type：Authorization Code（应用同时使用 PKCE S256）
- [ ] Scope：`openid profile email`

### 身份字段（claims）
- [ ] 唯一标识使用 **`employeeNumber`**（应用按工号识别用户；`sub` 在 preprod 与 prod 中不同，不能使用）
- [ ] 要求 Okta 在授权服务器中配置 `employeeNumber` 自定义 claim，在 id_token 或 userinfo 中返回均可，并确认 **preprod 与 prod 均已配置**。WIS 的 prod 曾漏配此项
- [ ] `email`、`given_name`、`family_name` 作为辅助信息（标准 `email`、`profile` scope 即可提供）

### 访问控制
- [ ] 用户名单（Okta 不会自动分配，需管理员逐一指派）
- [ ] 访问审批问题（Okta Access Request 中的问题）
- [ ] 审批人

### 安全与网络
- [ ] 是否需要为应用启用网络区域（Trusted IP），涉及的 PC 与 PDA 网段
- [ ] MFA 策略：共享 PDA 是否豁免，或改用其它因素
- [ ] 密钥交付方式：不通过邮件发送 Client Secret，使用密钥管理系统

## 三、拿到 Okta 信息后填写的配置（应用侧）

后端已实现（见 `docs/INIT.md` 4.5），只需把 Okta 交付的值填入环境变量。本地写在 `.env`，ECS 上放入 Secrets Manager：

| Okta 交付的信息 | 环境变量 | 说明 |
|---|---|---|
| Issuer（OIDC Metadata 地址去掉 `/.well-known/openid-configuration`） | `OIDC_ISSUER` | 如 `https://<公司>.okta.com`。其它端点通过 discovery 自动获取 |
| Client ID | `OIDC_CLIENT_ID` | |
| Client Secret | `OIDC_CLIENT_SECRET` | 不要通过邮件传递，不要提交到 git |
| 登记的 Sign-in redirect URI | `OIDC_REDIRECT_URI` | 与 Okta 中登记的值逐字相同 |
| 登记的 Sign-out redirect URI | `OIDC_POST_LOGOUT_REDIRECT_URI` | |
| — | `DJANGO_HTTPS=1`、`TRUSTED_PROXY_COUNT=1` | 部署在 ALB 后面（HTTPS）时设置 |
| — | `DJANGO_SESSION_AGE_SECONDS` | 共享设备（PDA）建议缩短 |

## 四、上线前测试清单

本地可先用模拟 IdP 验证应用自身（`docker compose up -d mock-idp`），以下各项需在真实 Okta 上逐一确认：

1. [ ] 访问 `<OIDC_ISSUER>/.well-known/openid-configuration`，确认 `issuer` 与 `OIDC_ISSUER` 逐字一致（不一致时应用会报"SSO 配置错误"）
2. [ ] dev 环境完整走一遍：登录、回调、`/api/auth/me/` 返回工号、退出
3. [ ] preprod 与 prod 分别确认能识别 `employeeNumber`；缺失时应用会显示"身份提供方未返回 employeeNumber"，日志 reason 为 `sso:missing_claim:employeeNumber`
4. [ ] 用未分配应用的账号测试，确认被拒绝（应用显示"没有本应用的访问权限"，日志 reason 为 `sso:idp_error:access_denied`）
5. [ ] PC 与 PDA 各测试一次，检查是否触发意外 MFA
6. [ ] 换班场景：点击退出后再次登录，确认需要重新输入账号（Okta 会话已结束）
7. [ ] 从 Okta Dashboard 点击应用图标，确认能直接进入应用
