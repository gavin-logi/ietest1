# 变更记录: 20261126-0841 新增：仅供测试的路由，模拟返回 401 / 403 与写日志的视图
import logging

from django.http import HttpResponse, JsonResponse
from django.urls import path


def denied(request):
    return JsonResponse({"detail": "denied"}, status=403)


def denied_with_reason(request):
    response = JsonResponse({"detail": "denied"}, status=403)
    response.security_reason = "not_project_member"
    return response


def unauthenticated(request):
    return JsonResponse({"detail": "login required"}, status=401)


def writes_log(request):
    logging.getLogger("apps.test").info("inside request")
    return HttpResponse("ok")


def accepts_post(request):
    return HttpResponse("ok")


urlpatterns = [
    path("denied/", denied),
    path("denied-reason/", denied_with_reason),
    path("unauthenticated/", unauthenticated),
    path("writes-log/", writes_log),
    path("post/", accepts_post),
]
