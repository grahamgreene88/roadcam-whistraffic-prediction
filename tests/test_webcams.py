from datetime import UTC, datetime

import httpx

from whistler_traffic.http import make_client
from whistler_traffic.logger.webcams import image_mtime, poll_once
from whistler_traffic.storage import Buffer

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
ETAG_2300Z = '"6b076870-10"'  # nginx format: mtime 2026-11-25T23:00:00Z, size 16


def handler(request):
    name = request.url.path.rsplit("/", 1)[-1]
    if name == "1.jpg":
        return httpx.Response(200, content=JPEG, headers={"ETag": ETAG_2300Z})
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
    assert first[0]["image_mtime"] == "2026-11-25T23:00:00Z"
    [(key, path)] = buffer.pending()
    assert key.startswith("raw/webcams/1/") and path.read_bytes() == JPEG


def test_image_mtime_sources():
    etag_only = httpx.Headers({"ETag": ETAG_2300Z})
    assert image_mtime(etag_only) == datetime(2026, 11, 25, 23, tzinfo=UTC)
    lm = httpx.Headers({"Last-Modified": "Wed, 25 Nov 2026 22:00:00 GMT", "ETag": ETAG_2300Z})
    assert image_mtime(lm) == datetime(2026, 11, 25, 22, tzinfo=UTC)  # Last-Modified wins
    for bad in ('"zzzz-10"', '"6b076870"', "", 'W/"nope"'):
        assert image_mtime(httpx.Headers({"ETag": bad})) is None
