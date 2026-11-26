# 变更记录: 20261126-0841 新增：core app，放置与业务无关的横切能力（请求上下文、日志、审计、健康检查、SPA 兜底）
from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
