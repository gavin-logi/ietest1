# 变更记录: 20261126-0902 新增：SSO 路由，挂在 /api/auth/ 下（回调地址固定为 /api/auth/callback/）
from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login, name="login"),
    path("callback/", views.callback, name="callback"),
    path("logout/", views.logout, name="logout"),
    path("me/", views.me, name="me"),
]
