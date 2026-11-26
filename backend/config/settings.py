# 变更记录: 20261126-0841 新增：Django 骨架配置。全部配置来自环境变量；本机直跑时由 ../.env 补充；日志为 stdout 单行 JSON
# 变更记录: 20261126-0902 新增 SSO（OIDC）配置项：issuer 走 discovery，回调地址显式配置，employeeNumber 为识别 claim
# 变更记录: 20261126-1345 新增 S3 配置项（内部与公开 endpoint、凭证、桶、区域），供 apps/core/storage.py 使用
"""项目配置。

原则：代码不含任何项目名或环境差异，差异全部来自环境变量。
- 本机直跑（runserver）：load_dotenv 读取仓库根目录的 .env。
- 容器内：镜像不含 .env，load_dotenv 找不到文件时静默跳过，配置来自 compose 或 ECS 注入的环境变量。
- 已存在的环境变量优先于 .env（load_dotenv 默认不覆盖），因此 compose 的覆盖值和命令行临时变量都会生效。
"""

import os
import re
import sys
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
REPO_DIR = BASE_DIR.parent  # 仓库根目录（容器内为 /app）

load_dotenv(REPO_DIR / ".env")


def env_str(name, default=None, *, required=False):
    value = os.environ.get(name, "")
    if value:
        return value
    if required:
        raise ImproperlyConfigured(f"缺少必需的环境变量 {name}，请参考 .env.example")
    return default


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    value = os.environ.get(name)
    return int(value) if value else default


def env_list(name, default=""):
    return [
        item.strip()
        for item in os.environ.get(name, default).split(",")
        if item.strip()
    ]


# --- 应用标识（派生项目只改 .env，不改代码）---
APP_NAME = env_str("APP_NAME", "app")
APP_DISPLAY_NAME = env_str("APP_DISPLAY_NAME", APP_NAME)

# --- 基础安全 ---
SECRET_KEY = env_str("DJANGO_SECRET_KEY", required=True)
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
# 跨域提交表单的可信来源，例如 https://app.example.com；同源部署通常不需要
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# 是否经由 HTTPS 访问（ECS 上 ALB 终止 TLS 时设为 1）。
# 本地容器部署走 http，若开启 Secure Cookie，浏览器不会回传 cookie，导致无法登录，因此默认关闭。
HTTPS = env_bool("DJANGO_HTTPS", False)
if HTTPS:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # ALB 通过 X-Forwarded-Proto 告知原始协议；只有在应用前面确实有代理时才能信任该请求头
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# 应用前面的可信代理层数，用于从 X-Forwarded-For 中取真实客户端 IP。
# 本地直连为 0（使用 REMOTE_ADDR）；ECS + ALB 为 1。设置过大会让客户端可以伪造 IP。
TRUSTED_PROXY_COUNT = env_int("TRUSTED_PROXY_COUNT", 0)

# Session：SameSite 必须为 Lax（默认值）。SSO 回调是从 IdP 跨站跳回的顶层请求，Strict 会丢失 session。
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env_int("DJANGO_SESSION_AGE_SECONDS", 12 * 60 * 60)

# --- SSO（OIDC 授权码流程 + PKCE，后端持有 Client Secret）---
# OIDC_ISSUER 为空时 SSO 关闭，/api/auth/login/ 返回 503；其它端点地址通过 discovery 自动获取。
OIDC_ISSUER = env_str("OIDC_ISSUER", "")
OIDC_CLIENT_ID = env_str("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = env_str("OIDC_CLIENT_SECRET", "")
# 回调地址显式配置，不由请求拼接：经过 ALB 时自动拼接容易出现 http/https 或 host 不一致，
# Okta 会以 redirect_uri 不匹配拒绝（400）。必须与 Okta 应用中登记的 Sign-in redirect URI 完全一致。
OIDC_REDIRECT_URI = env_str("OIDC_REDIRECT_URI", "")
OIDC_SCOPES = env_str("OIDC_SCOPES", "openid profile email")
# 识别用户的 claim，对应 User.employee_number。Okta 需在授权服务器中配置该自定义 claim（prod 与 preprod 都要）。
OIDC_USER_KEY_CLAIM = env_str("OIDC_USER_KEY_CLAIM", "employeeNumber")
# 首次登录时自动创建用户（是否允许访问由 Okta 的应用分配控制）；设为 0 时只允许已预先开通的用户登录。
OIDC_CREATE_USERS = env_bool("OIDC_CREATE_USERS", True)
# 登出后回到的地址。若同时登出 IdP，该地址必须登记为 Okta 的 Sign-out redirect URI。为空时回到站点根路径。
OIDC_POST_LOGOUT_REDIRECT_URI = env_str("OIDC_POST_LOGOUT_REDIRECT_URI", "")
# 登出时是否同时结束 IdP 会话。共享设备（如 PDA）必须为 1，否则下一个人会直接以上一个人的身份登录。
OIDC_LOGOUT_FROM_IDP = env_bool("OIDC_LOGOUT_FROM_IDP", True)
# 访问 IdP（discovery、token、userinfo、jwks）的超时，秒
OIDC_HTTP_TIMEOUT = env_int("OIDC_HTTP_TIMEOUT", 10)

# --- 对象存储（S3 / MinIO）：详见 apps/core/storage.py ---
# 应用内部读写对象的 endpoint；为空时使用 AWS 默认地址（ECS）
S3_ENDPOINT_URL = env_str("S3_ENDPOINT_URL", "")
# 只用于生成预签名 URL 的 endpoint，必须是浏览器可达的地址；为空时与 S3_ENDPOINT_URL 相同
S3_PUBLIC_ENDPOINT_URL = env_str("S3_PUBLIC_ENDPOINT_URL", "")
S3_BUCKET = env_str("S3_BUCKET", "")
S3_REGION = env_str("S3_REGION", "us-east-1")
# 为空时使用 boto3 默认凭证链（ECS 上为 Task 的 IAM 角色）
S3_ACCESS_KEY_ID = env_str("S3_ACCESS_KEY_ID", "")
S3_SECRET_ACCESS_KEY = env_str("S3_SECRET_ACCESS_KEY", "")

if OIDC_ISSUER:
    _missing = [
        name
        for name in ("OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URI")
        if not globals()[name]
    ]
    if _missing:
        raise ImproperlyConfigured(
            f"已设置 OIDC_ISSUER，但缺少 {', '.join(_missing)}，请参考 .env.example"
        )

# --- 应用 ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    # 让 runserver 也通过 WhiteNoise 提供静态文件，与容器内行为一致
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # 尽早生成 trace_id，后续所有日志都能带上
    "apps.core.middleware.RequestContextMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # 401 / 403 统一记录 SECURITY 日志（需要 request.user，因此放在认证之后）
    "apps.core.middleware.SecurityEventMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
CSRF_FAILURE_VIEW = "apps.core.views.csrf_failure"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- 数据库 ---
DATABASE_URL = env_str("DATABASE_URL", required=True)
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL, conn_max_age=60, conn_health_checks=True
    ),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- 用户 ---
# 自定义用户模型必须在第一次 migrate 之前确定，之后几乎无法更换，因此在模板中预先提供
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- 国际化 ---
LANGUAGE_CODE = "zh-hans"
# 只影响页面显示；数据库存 UTC（USE_TZ），日志固定输出 UTC
TIME_ZONE = env_str("DJANGO_TIME_ZONE", "Asia/Shanghai")
USE_I18N = True
USE_TZ = True

# --- 静态文件与前端产物 ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # collectstatic 的输出目录，容器启动时生成
# 运行测试时没有执行 collectstatic：Manifest 存储找不到清单会报错，WhiteNoise 也会警告 STATIC_ROOT 不存在。
# 因此测试改用普通存储，并让 WhiteNoise 直接从各 app 的 static 目录查找文件。
TESTING = "test" in sys.argv
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if TESTING
        else "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
if TESTING:
    WHITENOISE_AUTOREFRESH = True

# Vite 构建产物（index.html 与 assets/）。容器内为 /app/frontend/dist。
# 由 WhiteNoise 按站点根路径直接提供，因此 Vite 保持默认 base: '/' 即可，不需要与 STATIC_URL 对齐。
FRONTEND_DIST_DIR = REPO_DIR / "frontend" / "dist"
if FRONTEND_DIST_DIR.is_dir():
    WHITENOISE_ROOT = FRONTEND_DIST_DIR

# Vite 产物文件名带内容哈希（如 index-BdT3k9aZ.js），可以长期缓存
_HASHED_FILE = re.compile(r"^.+[.-][0-9a-zA-Z_-]{8,12}\..+$")


def _immutable_file_test(path, url):
    return bool(_HASHED_FILE.match(url))


WHITENOISE_IMMUTABLE_FILE_TEST = _immutable_file_test

# --- 日志：只输出到 stdout，单行 JSON（见 AGENTS.md）---
LOG_LEVEL = env_str("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {"()": "apps.core.log_filters.RequestContextFilter"},
    },
    "formatters": {
        "json": {"()": "logging_json.JsonFormatter"},
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
            "filters": ["request_context"],
        },
    },
    "root": {"handlers": ["stdout"], "level": LOG_LEVEL},
    # Django 的默认配置把 django 日志写到 stderr，必须显式覆盖
    "loggers": {
        "django": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        # 4xx 由 SecurityEventMiddleware 等按规范记录；这里只保留 5xx（带 stack_trace）
        "django.request": {
            "handlers": ["stdout"],
            "level": "ERROR",
            "propagate": False,
        },
        # CSRF 失败已由 SecurityEventMiddleware 记为 SECURITY 日志，避免再输出一条重复的 APP 警告
        "django.security.csrf": {
            "handlers": ["stdout"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.server": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
    },
}
