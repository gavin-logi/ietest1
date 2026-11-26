#!/bin/sh
# 变更记录: 20261116-1520 初始创建：入口分发，读第一个参数决定本容器扮演 web / scheduler / migrate
# 变更记录: 20261124-1607 web 改用 gunicorn.conf.py 配置日志，去掉命令行日志参数
set -eu

case "${1:-web}" in
  web)
    # 静态文件总仓库在容器启动时现收，不进镜像；随后 exec 让 gunicorn 成为 PID 1
    python manage.py collectstatic --noinput
    # 日志输出在 gunicorn.conf.py 中统一配置为 stdout 单行 JSON（命令行参数会覆盖配置文件，故这里不再传日志参数）
    exec gunicorn -c gunicorn.conf.py config.wsgi:application
    ;;
  scheduler)
    exec python manage.py run_scheduler
    ;;
  migrate)
    exec python manage.py migrate --noinput
    ;;
  *)
    exec "$@"
    ;;
esac
