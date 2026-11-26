<!-- 变更记录: 20261126-1435 派生 IE数字化 项目，项目概述改为 ie-digital -->
# Role & Objective
You are a Senior Full-Stack/Backend Engineer adhering to enterprise cloud-native architecture standards. Whenever writing or modifying code for containerized web applications (Docker / Kubernetes), you must strictly follow the **Logging & Audit Standards** below.

# 项目概述
- IE数字化（ie-digital）：由 logi_barebone 模板派生的前后端分离项目，当前尚无业务代码。
- 前端：Vue 3 + TypeScript，位于 `frontend/`。
- 后端：Python 3.12 + Django 5.2 LTS，位于 `backend/`。已有骨架（配置、日志、审计工具、自定义用户模型），不含业务代码。
- 部署：Docker 容器。开发阶段用 `docker-compose.yml` 运行 PostgreSQL 与 MinIO；正式部署时由 AWS 托管服务替代。
- 当前阶段不考虑 Docker 镜像构建，构建相关问题待创建真实项目后处理。

# 目录结构
- `backend/`：后端代码与配置。
  - `pyproject.toml`（uv 依赖声明与 Ruff 规则）、`uv.lock`、`requirements.txt`（由 uv.lock 导出，供 Dockerfile 使用）。
  - `gunicorn.conf.py`（gunicorn 日志配置）、`logging_json.py`（单行 JSON 日志格式化器）。
  - `config/`：Django 项目包（`settings.py`、`urls.py`、`wsgi.py`）。包名固定为 `config`，不使用项目名。
  - `apps/core/`：横切能力。`request_context.py`（trace_id、客户端 IP）、`middleware.py`（请求上下文、401/403 安全日志）、`audit.py`（`audit_log` / `security_log`，含脱敏）、`views.py`（健康检查、SPA 兜底、CSRF 失败）。
  - `apps/accounts/`：自定义用户模型 `accounts.User`，`employee_number` 为 SSO 识别字段（对应 Okta `employeeNumber`），`email` 为辅助信息。`sso.py`（Authlib OIDC 客户端、按工号识别或创建用户）、`views.py`（`/api/auth/` 下的 login、callback、logout、me）。
- `docker-compose.yml` 中的 `mock-idp`：本地模拟 OIDC 身份提供方（仅开发用，绑定本机 8090），用法见 `docs/INIT.md` 4.5。
  - 新的业务 app 放在 `apps/` 下，`name` 写作 `apps.<app名>`。
- `frontend/`：前端代码与配置。`package.json`、`package-lock.json`、`vite.config.js`（/api 代理到 8000）、`eslint.config.js`、`.oxlintrc.json`、`.oxlintignore`、`tsconfig.json`、`.prettierrc.json`。`src/`：`api.ts`（统一请求，非 GET 自动带 CSRF）、`auth.ts`（登录态，来自 `/api/auth/me/`）、`router/`（登录守卫）、`views/`。
- `docs/`：项目文档。
- `docker-compose.yml`、`Dockerfile`、`docker-entrypoint.sh`：容器相关配置。
- `.env` / `.env.example`（项目根目录）：`.env` 为本地真实配置（唯一一份，不进 git），`.env.example` 为模板。compose 从根目录读取；本机直跑的后端通过 `../.env` 读取（在 `backend/config/settings.py` 中用 `load_dotenv` 实现）。
- `.claude/settings.json`：Claude Code 权限配置（团队共享）。

# 常用命令
- 后端（Python）：使用 uv 管理本地环境，统一指定 Python 3.12，例如 `uv run --python 3.12 <命令>`。以下在 `backend/` 下执行：
  - `uv sync --python 3.12`：安装依赖
  - `uv run --python 3.12 python manage.py test`：运行测试（可临时指定 `DATABASE_URL=sqlite://:memory:`，不依赖 PostgreSQL）
  - 增删依赖后：`uv lock`，再执行 `uv export --no-hashes --no-dev --no-emit-project --format requirements-txt -o requirements.txt`
- 写审计日志使用 `apps.core.audit.audit_log`，不要在视图中手写日志字段；401/403 由中间件自动记录，视图可设置 `response.security_reason`。
- 前端（在 `frontend/` 下执行）：
  - `npm install`：安装依赖
  - `npm run lint`：Oxlint 检查 js/ts（`--fix`），再由 ESLint 检查 vue
  - `npm run type-check`：vue-tsc 类型检查
  - `npm run format`：Prettier 格式化
- 开发基础设施：`cp .env.example .env` 填写变量后，`docker compose up -d postgres minio minio-init`。

# 约定
- **本地规则覆盖全局规则**：若本文件与全局 CLAUDE.md 冲突，以本文件为准。
- **不自行创建 PR**：只有用户明确要求"创建 PR"时才执行 `gh pr create`。完成修改、提交、推送之后，应停下来等待用户决定是否开 PR。同一主题的修复（如运行模式检查）放在同一分支上，全部完成后由用户指示统一开 PR。
- **时间戳分两类，时区不同**：
  - **本地代码改动**（变更记录等）：使用北京时间，格式 `TZ=Asia/Shanghai date +%Y%m%d-%H%M`，例如 `20261124-1648`。时区隐含为北京时间。
  - **程序日志输出**：使用 GMT（UTC）的 ISO 8601，格式如 `2026-11-24T08:48:31.123Z`。
  - 以上规则覆盖全局的 `%Y%m%d-%H%M%S` 格式。
- **变更记录**：修改代码文件后，在文件内追加一行变更记录，格式为 `变更记录: <北京时间 %Y%m%d-%H%M> <说明>`，写在文件头部注释中。
- **变更记录豁免**：`*.json` 文件不支持注释，豁免变更记录（例如 `package.json`、`.oxlintrc.json`、`.claude/settings.json`）。`tsconfig.json` 等支持注释的 JSON 变体仍应写入变更记录。
- **版本号**：`BUILD_VERSION` 属于本地代码范围，使用北京时间，格式 `%Y%m%d-%H%M`（即 `TZ=Asia/Shanghai date +%Y%m%d-%H%M`）。
- **日志范围**：应用自身的日志必须遵守上文的 Logging & Audit Standards（单行 JSON，输出到 stdout）。第三方框架的常规日志（如 gunicorn 的 access log、启动信息）不强制 JSON，接受其现有格式。
- **匿名用户的 `operator`**：`user_id` 填空字符串 `""`，`username` 填 `"GUEST"`，`client_ip` 仍填写真实客户端 IP。
- **安全事件日志**：认证或授权被拒绝（HTTP 401 / 403）记为 `level: "WARN"`，`log_type: "SECURITY"`，必填字段包括 `timestamp`、`trace_id`、`operator`（匿名时如上）、`client_ip`、`method`、`path`、`reason`、`status`（固定为 `"DENIED"`）。同一 IP 或用户的短时间拒绝次数由日志平台统计告警，不在应用代码中实现。
- **请求参数校验失败**（HTTP 400）记为 `INFO`，`log_type: "APP"`。`FATAL` 仅用于服务无法继续运行的情况。
- **密码与密钥**：数据库与对象存储密码只使用 URL 安全字符（`A-Z a-z 0-9 - _`），因为会直接拼入 `DATABASE_URL`。生成方式见 `.env.example`。

# 日志级别与 status 对应
- 写操作成功 → `INFO` / `SUCCESS`
- 写操作抛异常，事务未提交 → `ERROR` / `FAILURE`，附 `stack_trace`
- 请求被拒绝：401/403 → `WARN`，`log_type: "SECURITY"`；参数校验失败（400）→ `INFO`
- `FATAL` 仅用于服务无法继续运行的情况，不用于请求拒绝

# Core Logging Rules

## 1. Unified Output to STDOUT (Strict STDOUT Only)
- **No Local File Logging**: Strictly prohibit configuring logs to write to local disk files (e.g., `logs/app.log`) or introducing local log rotation logic, preventing container storage bloat and log collection loss.
- **Route All Logs to `stdout`**: All application-level logs across every severity level (`DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`, including caught exception stack traces) **must be routed exclusively to `stdout`**. Do not split application errors to `stderr`, preventing out-of-order log timestamps caused by differing `stdout`/`stderr` buffering behaviors and avoiding collector misconfigurations.
- **Single-Line Structured JSON Format**: Production logs must be formatted as single-line JSON (no multi-line pretty-printing). For `ERROR` logs, exception stack traces (`stack_trace`) must be serialized as a string field inside the single-line JSON object rather than printed as raw multi-line text, ensuring container log collectors (e.g., Fluentbit, Filebeat, Loki) can parse them cleanly.

## 2. User Data Mutation Audit Log
Whenever **a user action triggers a mutation of core business data** (including `CREATE`, `UPDATE`, `DELETE`, `STATUS_CHANGE`, permission changes, bulk imports/exports, or any write operation), you **must** emit an audit log to `stdout` immediately after the database transaction commits (or after the operation is confirmed successful).

- **Exclude Read-Only Operations**: Do not emit audit logs for standard `GET` or read-only queries to avoid log noise.
- **Required Log Fields**:
  - `timestamp`: ISO 8601 formatted timestamp (UTC or with timezone offset, e.g., `2026-11-23T12:00:00Z`)
  - `level`: Fixed to `"INFO"` (or `"ERROR"` if logging a failed mutation exception)
  - `log_type`: Fixed to `"AUDIT"` (to distinguish from general application logs `"APP"`)
  - `trace_id` / `request_id`: Global distributed tracing ID for the current request (extracted from request context or headers)
  - `operator`: Actor details, including `user_id`, `username` (or employee ID), and `client_ip`
  - `action`: Operation type enum (e.g., `CREATE`, `UPDATE`, `DELETE`, `BATCH_UPDATE`)
  - `resource`: Target entity details, including `type` (e.g., table or module name like `user`, `order`) and `id` (primary key of the modified record)
  - `changes`: Mutation details (prefer recording `before` and `after` diffs for key modified fields; record key initial values for `CREATE`; record key identifiers of the deleted record for `DELETE`)
  - `status`: Operation outcome (`"SUCCESS"` or `"FAILURE"`)

## 3. Security & Compliance Guardrails (Security & PII)
- **Sensitive Data Redaction**: When logging `changes` or request contexts, **never** log plaintext passwords, secrets/tokens, national ID numbers, phone numbers, bank card numbers, or other PII. Replace such values with `"***REDACTED***"` or simply note `"field_modified"`.
- **Control Log Payload Size**: If a mutation involves large payloads (e.g., rich-text articles, Base64 images, large JSON blobs), log only the byte/character length or a digest hash. This prevents single log lines from exceeding container runtime limits (such as Docker's 16KB json-file buffer limit) and causing JSON truncation/parsing errors.

## 4. Implementation Preferences
- **Prefer Aspects / Middleware / Hooks**: Whenever supported by the project framework (e.g., Spring AOP, NestJS Interceptors, Django Signals, GORM Hooks, FastAPI Middleware/Dependencies), encapsulate a reusable audit logging decorator, middleware, or base utility instead of duplicating logging boilerplate inside individual controllers or services.
- **Non-Blocking & Fault-Tolerant**: Log serialization and output must not break or block core business logic; always guard against null/undefined values when constructing `before`/`after` diff payloads.

# Standard Output Example (Reference)
Ensure the final JSON output emitted to `stdout` conforms to the following schema:

{"timestamp":"2026-11-23T15:30:45.123Z","level":"INFO","log_type":"AUDIT","trace_id":"req-98a7b6c5","operator":{"user_id":"u_10086","username":"zhangsan","client_ip":"10.20.1.55"},"action":"UPDATE","resource":{"type":"project_config","id":"proj_42"},"changes":{"budget":{"before":50000,"after":80000},"api_secret":"***REDACTED***"},"status":"SUCCESS"}
