# 变更记录: 20261126-0841 新增：ASGI 入口（当前部署使用 WSGI，保留以备将来需要）
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
