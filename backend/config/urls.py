# 变更记录: 20261126-0841 新增：路由。/api/ 为后端接口，/admin/ 为 Django 后台，其余路径交给前端 SPA
# 变更记录: 20261126-0902 新增 /api/auth/（SSO 登录、回调、登出、当前用户）
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from apps.core import views as core_views

admin.site.site_header = settings.APP_DISPLAY_NAME
admin.site.site_title = settings.APP_DISPLAY_NAME

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", core_views.health, name="health"),
    path("api/auth/", include("apps.accounts.urls")),
    # 兜底：非 api/admin/static 的路径都返回前端 index.html，由 Vue Router 处理
    re_path(r"^(?!api/|admin/|static/).*$", core_views.spa_index, name="spa"),
]
