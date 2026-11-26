# 变更记录: 20261126-0841 新增：健康检查、SPA 兜底页、CSRF 失败视图（返回 JSON 并标注安全日志原因）
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def health(request):
    """存活检查，供 ALB / 容器编排使用。不访问数据库，避免数据库抖动导致实例被反复摘除。"""
    return JsonResponse({"status": "ok"})


@require_safe
def spa_index(request):
    """返回前端 index.html，前端路由（如 /orders/42）刷新时也能打开页面。

    index.html 不缓存，保证发布后浏览器立即拿到引用新哈希资源的入口文件。
    """
    index_file = Path(settings.FRONTEND_DIST_DIR) / "index.html"
    if not index_file.is_file():
        raise Http404(
            "前端尚未构建：请在 frontend/ 下运行 npm run build，或在开发时访问 Vite 开发服务器"
        )
    response = HttpResponse(
        index_file.read_bytes(), content_type="text/html; charset=utf-8"
    )
    response["Cache-Control"] = "no-cache"
    return response


def csrf_failure(request, reason=""):
    """CSRF 校验失败：返回 JSON（前端易于处理），并由 SecurityEventMiddleware 记录安全日志。"""
    response = JsonResponse({"detail": "CSRF verification failed"}, status=403)
    response.security_reason = f"csrf_failed: {reason}" if reason else "csrf_failed"
    return response
