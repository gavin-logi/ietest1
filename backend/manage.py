#!/usr/bin/env python
# 变更记录: 20261126-0841 新增：Django 命令入口（settings 模块固定为 config.settings，不含项目名）
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
