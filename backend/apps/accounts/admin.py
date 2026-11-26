# 变更记录: 20261126-0841 新增：用户后台，在默认 UserAdmin 基础上显示与搜索工号
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "employee_number",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
    )
    search_fields = ("username", "employee_number", "email", "first_name", "last_name")
    fieldsets = (
        *BaseUserAdmin.fieldsets,
        ("SSO", {"fields": ("employee_number",)}),
    )
    add_fieldsets = (
        *BaseUserAdmin.add_fieldsets,
        ("SSO", {"fields": ("employee_number", "email")}),
    )
