# 变更记录: 20261116-1520 初始创建：多阶段构建。Node 阶段编前端，Python 阶段装后端，只把前端产物拎过来
# 变更记录: 20261124-1637 Node 镜像升级到 24 LTS（20 已 EOL）；最终镜像改用非 root 用户运行
# 变更记录: 20261126-1046 修复 /app/backend 归 root 导致 collectstatic 无法写入 staticfiles（PermissionError）
# 变更记录: 20261126-1050 前端构建接收 APP_DISPLAY_NAME 构建参数，使容器内页面标题与本地开发一致
# 阶段一：Node 只负责编译前端，本阶段的其它东西都不会进最终镜像
FROM node:24-alpine AS frontend
# 页面标题来自 APP_DISPLAY_NAME（vite.config.js）。构建上下文不含根目录 .env，因此由 compose 以构建参数传入
ARG APP_DISPLAY_NAME=App
ENV APP_DISPLAY_NAME=${APP_DISPLAY_NAME}
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 阶段二：最终镜像，只有 Python 运行时和后端代码，没有 Node、没有编译器
FROM python:3.12-slim AS final
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
# 非 root 用户运行应用；--create-home 让 HOME 可写（gunicorn 会在 HOME 下创建控制 socket）
RUN groupadd --system app && useradd --system --gid app --create-home app
# 依赖清单单独先拷、先装：改业务代码时这一层命中缓存，不用重装依赖（依赖以 root 安装到系统目录）
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt
# --chown 让 collectstatic 能在启动时写入 backend/staticfiles
COPY --chown=app:app backend/ /app/backend/
# 前面 COPY requirements.txt 时已由 root 创建了 /app/backend，--chown 不会改已存在的目录；
# 这里显式设置属主，并预建 staticfiles，让 collectstatic 能在启动时写入
RUN mkdir -p /app/backend/staticfiles && chown app:app /app/backend /app/backend/staticfiles
COPY --from=frontend /build/dist /app/frontend/dist
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
WORKDIR /app/backend
USER app
EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
CMD ["web"]
