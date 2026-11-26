# 变更记录: 20261126-0841 新增：accounts app，提供自定义用户模型（为 SSO 预留 employee_number）
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "账号"
