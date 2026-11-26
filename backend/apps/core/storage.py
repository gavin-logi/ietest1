# 变更记录: 20261126-1345 新增：双 S3 客户端。internal 负责读写对象；public 只用于生成预签名 URL（endpoint 须为浏览器可达地址）
"""对象存储封装。

业务代码只调用 `put_object`、`download_url`，不直接创建 boto3 客户端，避免两个 endpoint 混用。

为什么要两个客户端：预签名 URL 的签名包含 host，而 host 取自客户端的 endpoint。
应用容器只能访问 `minio:9000`，浏览器只能访问 `localhost:9000`（或局域网 IP），
因此签名必须使用浏览器可达的 endpoint。两者只有 endpoint 不同，凭证相同。
"""

import functools

import boto3
from botocore.config import Config
from django.conf import settings


def _client(endpoint_url):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,  # None 时使用 AWS 默认地址（ECS）
        aws_access_key_id=settings.S3_ACCESS_KEY_ID or None,  # 为空则走 IAM 角色
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY or None,
        region_name=settings.S3_REGION,
        # 显式 path-style，链接形如 host/bucket/key，避免 bucket.host 形式
        # SigV4：SigV2 已被 AWS 淘汰，且 boto3 默认对自定义 endpoint 可能仍使用 SigV2
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@functools.lru_cache(maxsize=1)
def internal_client():
    """内部客户端：上传、删除、读取对象，连接 S3_ENDPOINT_URL。"""
    return _client(settings.S3_ENDPOINT_URL)


@functools.lru_cache(maxsize=1)
def public_client():
    """公开客户端：只用于本地计算签名，不发起网络请求。未配置公开地址时与内部客户端相同。"""
    return _client(settings.S3_PUBLIC_ENDPOINT_URL or settings.S3_ENDPOINT_URL)


def put_object(key, body):
    internal_client().put_object(Bucket=settings.S3_BUCKET, Key=key, Body=body)


def download_url(key, expires=300):
    return public_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )
