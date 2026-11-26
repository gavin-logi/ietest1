#!/bin/sh
# 变更记录: 20261126-0922 新增：后端提交门禁。Django 系统检查、迁移漂移检查、测试套件（SQLite 内存库，不依赖容器）
set -eu
cd "$(dirname "$0")/../backend"
# 未设置时临时生成密钥，不写入任何文件
: "${DJANGO_SECRET_KEY:=$(uv run --python 3.12 python -c 'import secrets; print(secrets.token_urlsafe(32))')}"
# 命令行变量优先于 .env，因此即使本机 .env 指向 PostgreSQL，门禁也只用内存库
export DJANGO_SECRET_KEY
export DATABASE_URL=sqlite://:memory:
uv run --python 3.12 python manage.py check
uv run --python 3.12 python manage.py makemigrations --check --dry-run
uv run --python 3.12 python manage.py test
