import httpx

from whistler_traffic.http import make_client
from whistler_traffic.logger.webcams import poll_once
from whistler_traffic.storage import Buffer

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


def handler(request):
    name = request.url.path.rsplit("/", 1)[-1]
    if name == "1.jpg":
        return httpx.Response(200, content=JPEG,
                              headers={"Last-Modified": "Wed, 25 Nov 2026 23:00:00 GMT"})
    if name == "2.jpg":
        return httpx.Response(404)
    raise httpx.ConnectError("boom", request=request)


def test_poll_saves_then_dedupes_and_survives_errors(tmp_path):
    cams = [(c, f"https://cams.test/images/{c}.jpg") for c in ("1", "2", "3")]
    buffer, hashes = Buffer(tmp_path), {}
    with make_client("test@example.com", transport=httpx.MockTransport(handler)) as client:
        first = poll_once(client, cams, hashes, buffer)
        second = poll_once(client, cams, hashes, buffer)
    assert [r["result"] for r in first] == ["saved", "http_error", "fetch_error"]
    assert [r["result"] for r in second] == ["duplicate", "http_error", "fetch_error"]
    [(key, path)] = buffer.pending()
    assert key.startswith("raw/webcams/1/") and path.read_bytes() == JPEG
