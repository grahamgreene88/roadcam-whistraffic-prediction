import hashlib

import pytest

from whistler_traffic.storage import Buffer, Uploader


class FakeS3:
    def __init__(self, fail=False):
        self.fail, self.objects = fail, {}

    def put_object(self, Bucket, Key, Body, ContentType):
        if self.fail:
            raise ConnectionError("storage down")
        self.objects[Key] = Body
        return {"ETag": f'"{hashlib.md5(Body).hexdigest()}"'}


def test_buffer_refuses_overwrite(tmp_path):
    b = Buffer(tmp_path)
    b.put("raw/x/a.jpg", b"1")
    with pytest.raises(FileExistsError):
        b.put("raw/x/a.jpg", b"2")
    assert (tmp_path / "raw/x/a.jpg").read_bytes() == b"1"


def test_drain_deletes_only_after_confirmed_upload(tmp_path):
    b = Buffer(tmp_path)
    b.put("raw/x/a.jpg", b"1")
    assert Uploader(FakeS3(fail=True), "bkt").drain(b) == (0, 1)
    assert len(b.pending()) == 1
    s3 = FakeS3()
    assert Uploader(s3, "bkt").drain(b) == (1, 0)
    assert b.pending() == [] and s3.objects == {"raw/x/a.jpg": b"1"}
