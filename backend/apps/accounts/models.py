# 变更记录: 20261126-0841 新增：自定义用户模型。SSO 以 employee_number（Okta employeeNumber claim）识别用户，email 仅作辅助信息
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """项目用户。

    识别规则（SSO 接入时使用）：
    - employee_number：唯一识别字段，对应 Okta 的 employeeNumber claim。工号在 preprod 与 prod 中相同、
      不随邮箱变更，管理员也能据此预先开通账号。Okta 的 sub 在不同环境中不同，因此不作为识别字段。
    - email：辅助信息，每次 SSO 登录时同步，可能变化，不用于识别用户。
    - employee_number 允许为空，用于不经 SSO 的本地账号（如初始化时用 createsuperuser 创建的管理员）。
      PostgreSQL 的唯一约束允许多个 NULL，因此多个本地账号不会冲突。

    只放 SSO 必需的字段；业务字段由具体项目自行添加。
    """

    employee_number = models.CharField(
        "工号",
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        help_text="SSO 识别字段，对应 Okta employeeNumber。本地账号可留空。",
    )

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = "用户"

    def save(self, *args, **kwargs):
        # 空字符串统一存为 NULL，否则多个空工号会违反唯一约束（admin 表单提交空值时为 ""）
        if not self.employee_number:
            self.employee_number = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.employee_number or self.get_username()
