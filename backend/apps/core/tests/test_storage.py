# 变更记录: 20261126-1345 新增：双 S3 客户端测试（离线：预签名不发请求，put_object 使用 Stubber）
from urllib.parse import urlparse

from botocore.stub import Stubber
from django.test import SimpleTestCase, override_settings

from apps.core import storage

INTERNAL = "http://minio:9000"
PUBLIC = "http://localhost:9000"


@override_settings(
    S3_ENDPOINT_URL=INTERNAL,
    S3_PUBLIC_ENDPOINT_URL=PUBLIC,
    S3_BUCKET="demo",
    S3_REGION="us-east-1",
    S3_ACCESS_KEY_ID="ak",
    S3_SECRET_ACCESS_KEY="sk",
)
class DualClientTests(SimpleTestCase):
    def setUp(self):
        storage.internal_client.cache_clear()
        storage.public_client.cache_clear()

    def test_internal_and_public_endpoints_differ(self):
        self.assertEqual(storage.internal_client().meta.endpoint_url, INTERNAL)
        self.assertEqual(storage.public_client().meta.endpoint_url, PUBLIC)

    def test_download_url_uses_public_endpoint_and_path_style(self):
        url = urlparse(storage.download_url("a/b.txt"))
        self.assertEqual(f"{url.scheme}://{url.netloc}", PUBLIC)
        self.assertEqual(url.path, "/demo/a/b.txt")
        self.assertIn("X-Amz-Signature=", url.query)

    def test_put_object_uses_internal_client(self):
        stubber = Stubber(storage.internal_client())
        stubber.add_response(
            "put_object",
            {},
            expected_params={"Bucket": "demo", "Key": "k", "Body": b"x"},
        )
        with stubber:
            storage.put_object("k", b"x")
            stubber.assert_no_pending_responses()


@override_settings(
    S3_ENDPOINT_URL=INTERNAL,
    S3_PUBLIC_ENDPOINT_URL="",
    S3_BUCKET="demo",
    S3_ACCESS_KEY_ID="ak",
    S3_SECRET_ACCESS_KEY="sk",
)
class PublicFallbackTests(SimpleTestCase):
    def setUp(self):
        storage.internal_client.cache_clear()
        storage.public_client.cache_clear()

    def test_public_falls_back_to_internal_when_unset(self):
        self.assertEqual(storage.public_client().meta.endpoint_url, INTERNAL)
