# 变更记录: 20261126-0841 新增：WSGI 入口，gunicorn 以 config.wsgi:application 启动（见 docker-entrypoint.sh）
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
