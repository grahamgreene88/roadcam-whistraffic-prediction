"""Write-once local buffer, uploader to Cloudflare R2 (plain S3 API), and local state."""

import hashlib
import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_PART = ".part"
CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jsonl": "application/x-ndjson",
    ".xml": "application/xml",
    ".html": "text/html",
}


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + _PART)
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Buffer:
    """Files waiting for upload, laid out exactly as their object keys."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes) -> Path:
        path = self.root / key
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {key}")
        _atomic_write(path, data)
        return path

    def pending(self) -> list[tuple[str, Path]]:
        return [
            (p.relative_to(self.root).as_posix(), p)
            for p in sorted(self.root.rglob("*"))
            if p.is_file() and not p.name.endswith(_PART)
        ]


class Uploader:
    def __init__(self, s3, bucket: str):
        self.s3 = s3
        self.bucket = bucket

    @classmethod
    def from_settings(cls, settings) -> "Uploader":
        import boto3
        from botocore.config import Config

        s3 = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,  # boto3's parameter names
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",  # R2 always uses "auto"
            config=Config(
                retries={"max_attempts": 5, "mode": "standard"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        return cls(s3, settings.r2_bucket)

    def drain(self, buffer: Buffer, max_files: int = 500) -> tuple[int, int]:
        """Upload pending files; delete each only after the ETag confirms the bytes."""
        uploaded = failed = 0
        for key, path in buffer.pending()[:max_files]:
            data = path.read_bytes()
            md5 = hashlib.md5(data).hexdigest()
            try:
                resp = self.s3.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=data,
                    ContentType=CONTENT_TYPES.get(path.suffix, "application/octet-stream"),
                )
            except Exception as exc:  # network/storage outage: keep everything, retry next cycle
                log.warning("upload failed for %s, stopping drain: %r", key, exc)
                failed += 1
                break
            etag = resp.get("ETag", "").strip('"')
            if etag != md5:
                log.error("upload of %s unconfirmed (etag %s != md5 %s); kept", key, etag, md5)
                failed += 1
                continue
            path.unlink()
            uploaded += 1
        return uploaded, failed


class JsonState:
    """Small local JSON state (e.g. last image hash per camera), written atomically."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict = json.loads(path.read_text()) if path.exists() else {}

    def save(self) -> None:
        _atomic_write(self.path, json.dumps(self.data, indent=1, sort_keys=True).encode())
