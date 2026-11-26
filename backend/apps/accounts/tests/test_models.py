# 变更记录: 20261126-0841 新增：自定义用户模型测试（工号唯一、空工号存为 NULL）
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

User = get_user_model()


class UserModelTests(TestCase):
    def test_custom_user_model_is_active(self):
        self.assertEqual(User._meta.label, "accounts.User")

    def test_employee_number_is_unique(self):
        User.objects.create_user(username="a", employee_number="10086")
        with self.assertRaises(IntegrityError):
            User.objects.create_user(username="b", employee_number="10086")

    def test_blank_employee_numbers_do_not_conflict(self):
        first = User.objects.create_user(username="admin1", employee_number="")
        User.objects.create_superuser(username="admin2")  # 不传密码：设置为不可用密码
        first.refresh_from_db()
        self.assertIsNone(first.employee_number)
        self.assertEqual(User.objects.filter(employee_number__isnull=True).count(), 2)

    def test_str_prefers_employee_number(self):
        self.assertEqual(
            str(User(username="zhangsan", employee_number="10086")), "10086"
        )
        self.assertEqual(str(User(username="zhangsan")), "zhangsan")
