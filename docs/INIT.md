<!-- 变更记录: 20261126-1446 增加宿主机端口可选项说明 -->
# barebone 接入指南

本仓库是一个**项目模板**，用于创建「Vue 前端 + Python 后端（Django）+ Docker 部署」的真实项目。本文档说明：

1. 仓库结构与各文件的职责
2. 从模板创建新项目时的注意事项
3. 本地调试、本地容器部署、ECS 部署的区别与命令

---

## 1. 仓库结构

```
barebone/                            仓库根目录（Git 根目录；也是 Docker 构建上下文）
├── .env                             【本地私有】真实配置，compose 与本机直跑的后端都读它，不进 git
├── .env.example                     【团队共享】配置模板，键名齐全、值为 CHANGE_ME
├── .dockerignore                    【团队共享】镜像构建时排除的文件（.env、.git、node_modules 等）
├── .gitignore                       【团队共享】排除 .env、staticfiles/、缓存等
├── .pre-commit-config.yaml          【团队共享】提交门禁：分支保护、Ruff、前端检查、gitleaks
├── .vscode/                         【团队共享】extensions.json 与 settings.json（格式化与 lint 配置）
├── .claude/settings.json            【团队共享】Claude Code 权限：禁止读取 .env 与密钥文件
├── AGENTS.md                        【团队共享】给 AI 与开发者的项目约定（日志规范、时间戳、变更记录）
├── Dockerfile                       多阶段构建：Node 阶段编译前端，Python 阶段只放后端与前端产物
├── docker-compose.yml               本地编排：一个镜像三个角色 + postgres + minio + 一次性建桶容器
├── docker-entrypoint.sh             入口分发：第一个参数决定容器扮演 web / scheduler / migrate
│
├── backend/                         Python / Django 后端（Django 5.2 LTS）
│   ├── pyproject.toml               【团队共享】uv 项目声明（依赖）与 Ruff 规则（target py312）
│   ├── uv.lock                      依赖锁定文件，必须提交
│   ├── requirements.txt             由 uv.lock 导出，供 Dockerfile 的 pip 使用（不要手改）
│   ├── gunicorn.conf.py             【团队共享】gunicorn 配置，日志输出到 stdout
│   ├── logging_json.py              【团队共享】单行 JSON 日志格式化器
│   ├── manage.py                    Django 命令入口
│   ├── config/                      项目包（固定名 config，不用项目名）：settings.py（读取 ../.env）、urls.py、wsgi.py
│   └── apps/
│       ├── core/                    横切能力：trace_id 与客户端 IP、401/403 安全日志、audit_log、健康检查、SPA 兜底
│       └── accounts/                自定义用户模型 accounts.User（employee_number 为 SSO 识别字段，email 为辅助）
│
├── frontend/                        Vue 3 + TypeScript 前端
│   ├── package.json                 脚本：lint / type-check / format；依赖含 vue 与开发工具
│   ├── package-lock.json            npm 生成，必须提交（Dockerfile 的 npm ci 依赖它）
│   ├── eslint.config.js             ESLint 扁平配置：只检查 .vue
│   ├── .oxlintrc.json               Oxlint 规则：只检查 .js / .ts
│   ├── .oxlintignore                Oxlint 忽略：依赖、构建产物、.vue
│   ├── tsconfig.json                类型检查范围：src/**/*.ts 与 src/**/*.vue
│   ├── .prettierrc.json             Prettier 排版风格
│   ├── .prettierignore              Prettier 忽略：dist、node_modules、lock 文件
│   ├── vite.config.js               开发服务器（5173）、/api 代理到 8000、页面标题读取根目录 .env
│   ├── index.html                   入口页，标题占位符 %APP_DISPLAY_NAME% 由 vite.config.js 替换
│   └── src/                         main.ts、App.vue、api.ts（统一请求）、auth.ts（登录态）、router/、views/
│
└── docs/                            项目文档（本文件、各阶段总结）
```

**关于 `.env` 的唯一来源**：`.env` 只放在根目录一份。compose 默认从根目录读取它；本机直跑的后端通过 `../.env` 读取（`settings.py` 中用 `load_dotenv` 实现）。不要在 `backend/` 下复制一份。

---

## 2. 从模板创建新项目

### 2.1 复制模板并初始化 Git

```bash
# 1. 只从干净模板副本复制，不要从含有本地密钥、数据或个人配置的工作副本复制
#    同时排除模板自己的 .git 与依赖目录
rsync -a --exclude '.env' --exclude '.git' --exclude 'node_modules' --exclude '.venv' \
  /path/to/barebone/ /path/to/my-project/
cd /path/to/my-project
cp .env.example .env         # 之后按需填写 CHANGE_ME

# 2. 设置项目名：代码中不写项目名，只需修改以下位置
#    .env：APP_NAME（镜像名 <APP_NAME>:local）、APP_DISPLAY_NAME（后台标题）、POSTGRES_DB、S3_BUCKET
#    frontend/package.json 的 name 字段（npm 无法读取环境变量，需手动修改）
#    README.md 标题

# 3. 初始化 Git
git init
```

### 2.2 不能直接在 main 上做第一次提交

`.pre-commit-config.yaml` 中的 `no-commit-to-branch` 会拦截对 `main`、`master`、`dev` 的提交。**第一次提交也会被拦截**，因此先切到功能分支：

```bash
git checkout -b init
```

### 2.3 先装依赖、暂存文件，再安装并运行 pre-commit

前端钩子使用项目本地的 npm 脚本（`npm --prefix frontend run lint` 等），**必须先在 `frontend/` 下安装依赖**，否则第一次提交会失败：

```bash
cd frontend
npm install                 # 生成 package-lock.json，必须提交
cd ..

git add -A                  # pre-commit run --all-files 只检查 git 跟踪的文件，新仓库必须先 add
uv tool install pre-commit  # 首次安装 pre-commit 本身（只需一次）
pre-commit install          # 在 .git/hooks 注册钩子
pre-commit run --all-files  # 首次全量检查，确认基线通过
git commit -m "init"        # 已在 init 分支，不会被 no-commit-to-branch 拦截
```

`pre-commit install` 只注册钩子，不会检查已有文件；`run --all-files` 检查 Git 已跟踪文件在工作区中的内容。若钩子自动修复了文件，需重新 `git add` 再提交。

> 前端脚手架已建立（`src/` 存在），`npm run type-check`、`lint`、`format`、`build` 均可直接运行。

### 2.4 当前钩子一览

| 钩子 | 作用 | 触发范围 |
|---|---|---|
| `no-commit-to-branch` | 拦截直接提交到 main / master / dev | 所有提交 |
| `ruff-check` / `ruff-format` | Python 检查与格式化 | `backend/` 下的 Python 文件 |
| `frontend-lint` | Oxlint 检查并修复 JS/TS，ESLint 检查并修复 Vue | `frontend/` 下的 js / ts / vue |
| `frontend-format` | Prettier 检查（不修改） | `frontend/` 下的 js / ts / vue / css / scss / json |
| `frontend-type-check` | vue-tsc 类型检查 | `frontend/` 下的 ts / vue |
| `gitleaks` | 扫描提交内容中的密钥 | 所有提交 |

注意：`frontend-lint` 带 `--fix`，会直接修改文件。修改后需要重新 `git add` 再 `git commit`。

---

## 3. 配置：`.env` 与环境变量

| 变量 | 本机直跑（runserver） | compose 容器内 | 说明 |
|---|---|---|---|
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | 读取 `.env` | 读取 `.env` | 建库参数，也用于拼接 `DATABASE_URL` |
| `DATABASE_URL` | `localhost:5432` | **被 compose 覆盖**为 `postgres:5432` | 数据库连接串 |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | 读取 `.env` | 读取 `.env` | 对象存储 root 账号（开发阶段） |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | **被覆盖**为 `http://minio:9000` | S3 API 地址 |
| `S3_PUBLIC_ENDPOINT_URL` | `http://localhost:9000` | **可由 `.env` 覆盖**，默认 `http://localhost:9000` | 仅用于生成预签名 URL，必须与访问者的浏览器地址一致；跨设备测试时设为 `http://<本机局域网IP>:9000`（见 3.1、5.5） |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | 与 MinIO root 相同 | 由 compose 从 MinIO root 注入 | 应用访问 S3 的凭证。**ECS 上应留空，使用 IAM 角色** |
| `S3_BUCKET` / `S3_REGION` | 读取 `.env` | 读取 `.env` | 桶名与区域 |
| `DJANGO_SECRET_KEY` | 读取 `.env` | 读取 `.env` | 必须随机生成 |
| `DJANGO_DEBUG` | `0` 或 `1` | `0` | 生产必须为 0 |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | 按需 | 逗号分隔，不要有空格。跨设备测试时加入本机局域网 IP |
| `APP_NAME` / `APP_DISPLAY_NAME` | 读取 `.env` | 读取 `.env` | 项目短名（镜像名）与显示名（后台标题），默认 `app` |
| `DJANGO_HTTPS` | `0` | `0` | 可选。ECS + ALB 终止 TLS 时设为 `1`：启用 Secure Cookie 并信任 `X-Forwarded-Proto`。http 访问时必须为 `0`，否则无法登录 |
| `TRUSTED_PROXY_COUNT` | `0` | `0` | 可选。应用前的可信代理层数，用于从 `X-Forwarded-For` 取真实 IP。ECS + ALB 为 `1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `http://localhost:5173` | 空 | 可选。CSRF 可信来源（需带协议与端口）。模板默认包含 Vite 开发地址，因为 Vite 代理改写了 Host，浏览器的 Origin 仍是 5173。同源部署（容器、ALB）不需要，生产环境只填正式域名 |
| `DJANGO_SESSION_AGE_SECONDS` | `43200` | `43200` | 可选。会话有效期（秒），共享设备建议更短 |
| `DJANGO_TIME_ZONE` / `LOG_LEVEL` | `Asia/Shanghai` / `INFO` | 同左 | 可选。时区只影响页面显示，日志固定 UTC |
| `OIDC_ISSUER` | 模拟 IdP `http://localhost:8090/default` | 见 4.5 | 留空则关闭 SSO。其它端点通过 discovery 自动获取。**正式部署并使用 SSO 时必须由 Secrets Manager 注入**，否则 SSO 关闭（登录返回 503） |
| `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | 模拟 IdP 任意值 | 同左 | Okta 应用的凭证。ECS 上由 Secrets Manager 注入 |
| `OIDC_REDIRECT_URI` | `http://localhost:8000/api/auth/callback/` | 按访问地址 | 必须与 Okta 登记的 Sign-in redirect URI 完全一致 |
| `OIDC_POST_LOGOUT_REDIRECT_URI` | `http://localhost:8000/` | 按访问地址 | 登出后回到的地址，需登记为 Okta 的 Sign-out redirect URI |
| `OIDC_USER_KEY_CLAIM` 等 | 默认值 | 默认值 | 可选：识别 claim（`employeeNumber`）、`OIDC_SCOPES`、`OIDC_CREATE_USERS`、`OIDC_LOGOUT_FROM_IDP`、`OIDC_HTTP_TIMEOUT` |
| `POSTGRES_HOST_PORT` / `MINIO_HOST_PORT` / `MINIO_CONSOLE_HOST_PORT` / `MOCK_IDP_HOST_PORT` / `WEB_HOST_PORT` / `BACKEND_PORT` | 可选 | 可选 | 宿主机端口（默认 5432 / 9000 / 9001 / 8090 / 8000 / 8000）。同机有其它项目占用时修改，并同步 `DATABASE_URL`、`S3_*_ENDPOINT_URL`、`OIDC_*_URI` 中的端口；`BACKEND_PORT` 供 Vite 代理使用 |

**密码规则**：`POSTGRES_PASSWORD` 与 `MINIO_ROOT_PASSWORD` 只能包含 URL 安全字符（`A-Z a-z 0-9 - _`），因为会直接拼入 `DATABASE_URL`。生成方式：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

**覆盖规则**：compose 的 `environment` 优先于 `env_file`。因此 `.env` 里的本机地址（`localhost`）在容器里会被替换为容器网络地址（`postgres`、`minio`），两者可以共存于同一份 `.env`。

### 3.1 S3 客户端：内部与公开两个 endpoint

实现见 `backend/apps/core/storage.py`，业务代码只调用 `put_object`、`download_url`。

| 客户端 | endpoint | 用途 |
|---|---|---|
| `internal_client()` | `S3_ENDPOINT_URL`（compose 中为 `minio:9000`） | 上传、删除、读取对象 |
| `public_client()` | `S3_PUBLIC_ENDPOINT_URL`（为空时与内部相同） | 只生成预签名下载链接，不发起网络请求 |

**原因**：预签名 URL 的签名包含 host，而 host 取自客户端的 endpoint。应用容器只能访问 `minio:9000`，浏览器只能访问 `localhost:9000`，签名必须使用浏览器可达的 endpoint。

- 跨设备测试时，`S3_PUBLIC_ENDPOINT_URL` 必须设为测试设备能访问的局域网地址（见 5.5）。
- ECS 上两个 endpoint 都留空，使用 AWS 默认地址，凭证走 IAM 角色。
- 签名固定为 SigV4，地址固定为 path-style。`apps/core/tests/test_storage.py` 离线验证这两点。

---

## 4. 本地调试（跑法一：后端与前端分别跑在宿主机）

**适用场景**：日常写代码。改动即时生效，断点调试方便。

### 4.1 启动基础设施（postgres、minio、模拟 IdP）

```bash
docker compose up -d postgres minio minio-init mock-idp
```

`minio-init` 是一次性容器，建好桶后自动退出，属于正常现象。`mock-idp` 是本地模拟的 OIDC 身份提供方，用法见 4.5。

### 4.2 后端

```bash
cd backend
uv sync --python 3.12                                  # 首次或依赖变更后，创建 backend/.venv
uv run --python 3.12 python manage.py migrate          # 首次或模型变更后
uv run --python 3.12 python manage.py createsuperuser  # 首次：创建本地管理员（工号可留空）
uv run --python 3.12 python manage.py runserver        # 监听 127.0.0.1:8000
```

运行测试（使用内存 SQLite，不需要启动 PostgreSQL；命令行变量优先于 `.env`）：

```bash
DATABASE_URL=sqlite://:memory: uv run --python 3.12 python manage.py test
```

**增删依赖**：修改 `pyproject.toml` 的 `dependencies` 后执行 `uv lock`，再导出 `requirements.txt`（Dockerfile 使用）：

```bash
uv export --no-hashes --no-dev --no-emit-project --format requirements-txt -o requirements.txt
```

**接口约定**：

| 路径 | 用途 |
|---|---|
| `/api/health/` | 存活检查（不访问数据库），供 ALB 使用 |
| `/api/auth/login/?next=/path` | 跳转 IdP 登录，成功后回到 `next`（只接受本站相对路径） |
| `/api/auth/callback/` | IdP 回调，即 Okta 的 Sign-in redirect URI（路径固定） |
| `/api/auth/logout/` | POST（需 CSRF）。结束本地会话并跳转 IdP 登出；`Accept: application/json` 时返回 `{"redirect_url": ...}` |
| `/api/auth/me/` | 当前用户；匿名时返回 `authenticated: false`（200，不是 401），同时下发 `csrftoken` cookie |
| `/api/...` | 后端接口 |
| `/admin/` | Django 后台 |
| 其它路径 | 返回 `frontend/dist/index.html`，由 Vue Router 处理；未构建前端时返回 404 |

每个响应都带 `X-Request-ID` 头，与该请求所有日志中的 `trace_id` 一致。上游传入合法的 `X-Request-ID` 时沿用。

### 4.3 前端

```bash
cd frontend
npm install                  # 首次
npm run dev                  # Vite 开发服务器，默认 http://localhost:5173
```

`vite.config.js` 已把 `/api` 代理到 `http://localhost:8000`，浏览器只访问 5173，与后端同源，session cookie 才能生效。

> 使用 Vite 访问时，`.env` 中的 `OIDC_REDIRECT_URI` 与 `OIDC_POST_LOGOUT_REDIRECT_URI` 应改为 `http://localhost:5173/...`（见 4.5）。

### 4.4 注意

- 本机直跑时，预签名 URL 的地址是 `localhost:9000`，浏览器直接访问即可，**不需要改 hosts**。
- 本机直跑连接的是宿主机映射的 5432 与 9000 端口，compose 的 `web` 服务不需要启动。
- `frontend/dist` 存在时，WhiteNoise 以站点根路径直接提供其中文件（`WHITENOISE_ROOT`），因此 Vite 保持默认 `base: '/'`；带哈希的文件名长期缓存，`index.html` 由兜底视图返回并禁止缓存。WhiteNoise 只在启动时扫描该目录，本机重新 `npm run build` 后需重启后端。

### 4.5 SSO 本地调试（模拟 IdP）

`.env.example` 中的 `OIDC_*` 默认值已指向模拟 IdP。已有的 `.env` 需要从模板补上 `OIDC_*` 一节，否则 SSO 处于关闭状态（`/api/auth/login/` 返回 503）。

1. `docker compose up -d mock-idp`，后端按 4.2 启动。
2. 浏览器访问 `http://localhost:8000/api/auth/login/`，跳转到模拟 IdP 的登录页。
3. 用户名一栏填写**工号**（如 `10086`），它会作为 `employeeNumber` 返回；claims 一栏留空。登录后跳回站点，访问 `/api/auth/me/` 可看到当前用户。
4. 用户名填写 `no-employee-number` 可模拟 IdP 未返回 `employeeNumber` 的情况（WIS 生产环境曾遇到），应看到"登录失败"说明页。

**用户识别规则**：按 `employeeNumber` 查找 `User.employee_number`。找不到时自动创建（`OIDC_CREATE_USERS=1`，用户名即工号，无密码）；每次登录同步 email 与姓名。创建与修改都会记录 `AUDIT` 日志，email 与姓名只记为 `field_modified`。

**端到端测试**：对接正在运行的模拟 IdP，验证签名、nonce、PKCE、登出整条链路：

```bash
cd backend
DATABASE_URL=sqlite://:memory: uv run --python 3.12 python manage.py test apps.accounts.tests.test_sso_e2e
```

默认指向 `http://localhost:8090/default`。模拟 IdP 未运行时测试会跳过，不会失败；如需指向其它地址，可设置 `SSO_E2E_ISSUER`。

**注意**

- 模拟 IdP 任何工号都能登录，不做认证，因此只用于本机开发，**不适合跨设备访问**。compose 中它只绑定 `127.0.0.1`。运行模式二如需 SSO，见 5.2。
- 模拟 IdP 不校验 Client Secret 与 redirect_uri。
- 换成 Okta 后，必须用真实账号重新验证一次：Okta 是否返回 `employeeNumber`（preprod 与 prod 分别验证）、回调地址是否登记、MFA 策略是否符合预期。
- 前端（Vite，`localhost:5173`）建好后，`OIDC_REDIRECT_URI` 与 `OIDC_POST_LOGOUT_REDIRECT_URI` 应改为浏览器实际访问的地址（经 Vite 代理的 `http://localhost:5173/...`），Okta 中登记的地址也要一致。

---

## 5. 本地容器部署（跑法二：整套容器化）

**适用场景**：验证镜像能否正确运行，模拟生产环境。

### 5.1 准备

```bash
cp .env.example .env         # 填写全部 CHANGE_ME
```

### 5.2 启动

```bash
docker compose up --build    # 构建镜像并启动全部服务
```

启动顺序由 compose 保证：`postgres` 健康 → `migrate` 建表并退出 → `minio-init` 建桶并退出 → `web` 与 `scheduler` 启动。

**SSO 在本模式下默认不可用**：`web` 容器访问不到宿主机的 `localhost:8090`，登录会返回 502 与"暂时无法连接身份提供方"的提示，这是预期行为。本模式默认用于验证镜像、迁移、静态资源、路由与日志。

模拟 IdP 任何工号都能登录，只用于本机。运行模式二如需 SSO，建议使用真实 IdP。推荐 Keycloak（开发模式 `start-dev`）。

### 5.3 常用命令

| 目的 | 命令 |
|---|---|
| 只起基础设施 | `docker compose up -d postgres minio minio-init` |
| 代码或依赖变更后重新构建 | `docker compose up --build` |
| 查看日志（stdout） | `docker compose logs -f web` |
| 停止但保留数据 | `docker compose down` |
| 停止并清空数据卷 | `docker compose down -v`（**会删除数据库和附件**） |
| 手动执行迁移 | `docker compose run --rm migrate` |
| 清理残留的旧服务 | `docker compose up -d --remove-orphans` |

**易错点**：

- `docker compose up` **不会自动重新构建**。镜像已存在时直接复用，改了代码却没生效，就是这个原因，需要 `--build`。
- 改了 `POSTGRES_PASSWORD` 后重启仍然连不上：密码只在第一次建库时写入 `pgdata` 卷，之后修改 `.env` 不会生效。已有数据库应进入容器执行 `ALTER ROLE`，再同步 `.env` 与 `DATABASE_URL`：

  ```bash
  docker compose exec postgres psql -U <用户名> -d <数据库名> -c "ALTER ROLE <用户名> WITH PASSWORD '<新密码>';"
  ```

- **轮换 MinIO root 密码**：修改根目录 `.env` 中的 `MINIO_ROOT_PASSWORD` 和 `S3_SECRET_ACCESS_KEY`，将二者设为同一个新密码。宿主机直跑的后端使用 `S3_SECRET_ACCESS_KEY`；Compose 容器会从 `MINIO_ROOT_PASSWORD` 注入 S3 凭证。密码仍须只用 URL 安全字符（`A-Z a-z 0-9 - _`）。

  ```bash
  # 先在 .env 中更新 MINIO_ROOT_PASSWORD 和 S3_SECRET_ACCESS_KEY，再执行：
  docker compose up -d --force-recreate minio
  docker compose up --force-recreate minio-init
  docker compose up -d --force-recreate web scheduler
  ```

  重建会让 MinIO 短暂不可用，但会保留 `miniodata` 卷和已有对象。第二条命令以前台方式运行，成功退出后再执行第三条，让应用容器使用新凭证。宿主机直跑的后端也需重启以读取新 `S3_SECRET_ACCESS_KEY`。轮换前生成的预签名 URL 可能立即失效，需要重新生成。此流程按当前 Compose 凭证注入配置编写，尚未在实际 MinIO 容器上验证。

- `down -v` 会删除 `pgdata` 与 `miniodata`，**只在确实要清空开发数据时使用**，不要用来轮换密码。
- `docker compose` 的变量替换读取的是**项目根目录的 `.env`**，这也是 `.env` 必须放在根目录的原因。

### 5.4 端口一览

| 服务 | 宿主机绑定 | 用途 |
|---|---|---|
| web | `0.0.0.0:8000`（局域网可访问） | 网站与 API（前端产物与 Django 静态文件均由 WhiteNoise 提供） |
| postgres | `127.0.0.1:5432`（仅本机） | 本机直跑（runserver）连接数据库 |
| minio | `0.0.0.0:9000`（局域网可访问） | S3 API，浏览器上传与下载附件走这里；跨设备测试附件需要 |
| minio | `127.0.0.1:9001`（仅本机） | MinIO 控制台 |

### 5.5 跨设备测试

本地 Docker 方式默认按"可跨设备测试"准备：

- web（前端页面与 API）对局域网开放：`0.0.0.0:8000`。
- minio S3 API 对局域网开放：`0.0.0.0:9000`，附件上传下载需要。
- postgres 与 minio 控制台仅本机：`127.0.0.1`，其它设备无法直连数据库。

开发阶段（`runserver`、`npm run dev`）始终只在本机运行，地址保持 `localhost`。

**步骤**

1. 查出本机局域网 IP：
   - macOS：`ipconfig getifaddr en0`（无线网卡可能是 `en1`）
   - Linux：`hostname -I`
   - Windows：`ipconfig`，查看 IPv4 地址
2. 在根目录 `.env` 中修改：
   - 只测页面与接口：`DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,<局域网IP>`
   - 同时测附件上传下载：再加上 `S3_PUBLIC_ENDPOINT_URL=http://<局域网IP>:9000`
3. 应用新配置（环境变量变化会重建容器，不需要 `--build`）：

   ```bash
   docker compose up -d
   ```

4. 其它设备在浏览器中访问 `http://<局域网IP>:8000`。

**注意**

- 局域网 IP 变化后，`.env` 中的对应值需要同步更新。
- `DJANGO_ALLOWED_HOSTS` 不包含局域网 IP 时，其它设备访问会返回 400。
- `S3_PUBLIC_ENDPOINT_URL` 不改为局域网地址时，附件下载链接指向对方设备自己的 `localhost`，下载会失败。
- `S3_ENDPOINT_URL` 不需要改，compose 会将其覆盖为 `http://minio:9000`。
- 跨设备测试结束后，把 `.env` 改回 `localhost` 并执行 `docker compose up -d`，即可恢复本机模式。
- macOS 防火墙可能拦截入站连接，首次运行 Docker 时需要允许。
- 默认设置下，跨设备测试不包含 SSO 登录（模拟 IdP 不可用）。

---

## 6. ECS 部署：与本地的关键区别

**原则**：代码一行不改，只换环境变量的来源和基础设施的实现。

| 项目 | 本地容器（跑法二） | ECS |
|---|---|---|
| 数据库 | postgres 容器（有卷） | RDS |
| 对象存储 | minio 容器（有卷） | S3 |
| 配置来源 | `.env` 文件 → compose 注入 | Secrets Manager → Task 定义注入环境变量 |
| S3 凭证 | MinIO root 账号 | **留空，使用 Task 的 IAM 角色**（临时凭证，自动轮换） |
| `DATABASE_URL` | compose 拼接 | Secrets Manager 中直接保存完整连接串 |
| 建桶 | `minio-init` 容器 | 在 Terraform / 控制台中创建，不在应用里做 |
| 建表 | `migrate` 服务（一次性） | `migrate` Task 通过 RunTask 执行，在部署 web 之前完成 |
| 定时任务 | `scheduler` 服务，固定 1 个 | `scheduler` Service，**desired count 固定为 1** |
| Web 副本数 | 1 | 按负载调整，多副本前提是无状态（已满足） |
| 静态与 API 入口 | 容器内 gunicorn 直接对外 | ALB 反向代理到 web Service；静态文件仍由 WhiteNoise 提供 |
| 日志 | `docker compose logs` | stdout 自动收集到 CloudWatch Logs，应用代码不变 |

### 6.1 构建并推送镜像（模板命令，尚未验证）

```bash
# 变量：替换为你的账号与区域
export AWS_REGION=<region>
export AWS_ACCOUNT_ID=<account-id>
export ECR_REPO=<repo-name>
export IMAGE_TAG=$(TZ=Asia/Shanghai date +%Y%m%d-%H%M)   # 与变更记录一致的北京时间

# 登录 ECR
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin \
    "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

# 构建并推送（注意 Apple Silicon 需要指定平台）
docker build --platform linux/amd64 -t "$ECR_REPO:$IMAGE_TAG" .
docker tag "$ECR_REPO:$IMAGE_TAG" \
  "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:$IMAGE_TAG"
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:$IMAGE_TAG"
```

### 6.2 三类 Task 定义：同一个镜像，不同的 command

| Task | command | 运行方式 | 说明 |
|---|---|---|---|
| web | `["web"]` | ECS Service，可多副本，挂 ALB | 对外提供服务 |
| scheduler | `["scheduler"]` | ECS Service，**desired count = 1** | 定时任务，不能多副本 |
| migrate | `["migrate"]` | 一次性 RunTask | 每次发布前执行，成功后再更新 web |

迁移的典型顺序：`RunTask(migrate)` 成功 → 更新 web Service 与 scheduler Service。

> 具体的 ECS 资源（Cluster、Service、ALB、IAM 角色、Secrets）属于真实项目的基础设施代码，建议用 Terraform 或 CDK 管理，本模板不包含。

---

## 7. 日志

- 应用日志只输出到 stdout，**不写文件**。容器删除后文件会跟着丢失，多副本也无法汇总。
- 应用日志格式为单行 JSON，异常堆栈放在 `stack_trace` 字段中（见 `AGENTS.md`）。
- gunicorn 的 access log 与启动信息同样输出到 stdout，接受其现有格式（第三方日志不强制 JSON）。
- 日志级别与 `status` 的对应关系见 `AGENTS.md` 的"日志级别与 status 对应"。

---

## 8. 日常开发与提交行为

| 场景 | 系统自动行为 |
|---|---|
| 保存前端文件 | VS Code 调用 Prettier 格式化；Oxlint 检查 JS/TS，ESLint 检查 Vue |
| 保存 Python 文件 | VS Code 调用 Ruff 修复与整理 import |
| 直接在 main / master / dev 上提交 | `no-commit-to-branch` 拦截，要求切到功能分支 |
| 提交时有未修复的 lint 错误 | `frontend-lint` 中止提交并打印行号；修复后重新 `git add`、`git commit` |
| 提交时类型错误（如未定义变量） | `frontend-type-check` 中止提交 |
| 提交内容含疑似密钥 | `gitleaks` 中止提交 |
| 首次提交耗时较长 | 正常。pre-commit 首次运行时下载并缓存检查环境，之后通常在数秒内完成 |

---

## 9. 已知未完成事项

以下事项在模板阶段**尚未完成**，创建真实项目时需要处理：

- **定时任务（scheduler）**：`manage.py run_scheduler` 已提供空骨架（`apps/core/management/commands/run_scheduler.py`），不注册任何任务，只保持进程常驻、输出心跳日志并响应 SIGTERM 优雅退出，用于保证编排结构正确。是否需要定时任务、具体任务是什么，由真实项目决定；需要时在该命令中注册任务，部署时副本数必须保持为 1。
- **SSO 对接真实 Okta**：后端流程已实现并通过模拟 IdP 端到端验证，尚未对接真实 Okta。申请清单见 `docs/OIDC接入配置清单.md`；拿到 Client ID 后按 4.5 的注意事项验证。运行模式二如需 SSO，建议使用 Keycloak（开发模式 `start-dev`），尚未验证。
- **Django 后台登录方式**：`/admin/` 仍使用本地密码登录（供 `createsuperuser` 创建的管理员使用）。SSO 用户被设为 `is_staff` 后可以凭 SSO 会话进入后台。是否关闭后台密码登录，由具体项目决定。
- **前端单元测试**：模板没有前端单元测试，目前只做类型检查、lint 与构建验证。
- **`.env` 中的项目名**：`POSTGRES_DB`、`S3_BUCKET` 等需要按新项目命名。修改 `POSTGRES_DB` 不会重命名已存在的 `pgdata` 卷中的数据库。
- **镜像构建与 ECS 命令**：第 5 与第 6 节的命令尚未在真实项目上验证。
- **首次类型检查**：`src/` 建立后，首次运行 `npm run type-check`，确认 `tsconfig.json` 的 include 与入口文件匹配。
- **PostgreSQL 健康检查**：当前 `pg_isready` 使用容器内的 Unix socket，建议显式指定 TCP 探测，与 `migrate` 的连接方式一致。
- **scheduler 并发**：ECS 滚动发布时 `desiredCount=1` 仍可能短暂运行两个 scheduler。如任务要求互斥，需在任务执行层加锁。
- **迁移退出码**：发布流程应等待 migrate 任务退出且退出码为 0，再更新 web 与 scheduler 服务。

---

**相关文档**：各阶段的决策与变更记录见 `docs/` 下的总结文件；日志规范、时间戳规则与变更记录约定见 `AGENTS.md`。
