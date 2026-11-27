"""Webcam logger: poll every DriveBC view every 5 minutes and keep each new image.

Run locally: uv run --group logger --env-file .env python -m whistler_traffic.logger.webcams
"""

import csv
import hashlib
import json
import logging
import time
from collections import Counter
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from whistler_traffic.config import Settings
from whistler_traffic.http import make_client, ping
from whistler_traffic.storage import Buffer, JsonState, Uploader
from whistler_traffic.timeutil import iso_utc, key_timestamp, utc_now

log = logging.getLogger("webcams")

POLL_SECONDS = 300
STALE_AFTER_SECONDS = 3600
JPEG_MAGIC = b"\xff\xd8\xff"


def load_cameras(path: Path) -> list[tuple[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [(r["id"].strip(), r["links_imageURL"].strip()) for r in csv.DictReader(f)]


def image_mtime(headers: httpx.Headers) -> datetime | None:
    """When the server wrote the image. DriveBC (nginx) sends no Last-Modified, but its
    ETag is "<mtime hex>-<size hex>". Note: capture time (image overlay) is ~2 min earlier."""
    value = headers.get("last-modified")
    if value:
        try:
            lm = parsedate_to_datetime(value)
            if lm.tzinfo is not None:
                return lm
        except (TypeError, ValueError):
            pass
    mtime_hex, sep, _ = headers.get("etag", "").removeprefix("W/").strip('"').partition("-")
    if sep:
        try:
            return datetime.fromtimestamp(int(mtime_hex, 16), UTC)
        except (ValueError, OverflowError, OSError):
            pass
    return None


def fetch_camera(client, cam_id, url, last_hash, buffer) -> tuple[dict, str | None]:
    fetched_at = utc_now()
    rec = {"camera_id": cam_id, "url": url, "fetched_at": iso_utc(fetched_at)}
    try:
        resp = client.get(url)
    except httpx.HTTPError as exc:
        rec.update(result="fetch_error", error=repr(exc))
        return rec, None

    mtime = image_mtime(resp.headers)
    age = (fetched_at - mtime).total_seconds() if mtime else None
    rec.update(
        status=resp.status_code,
        headers=dict(resp.headers),
        image_mtime=iso_utc(mtime) if mtime else None,
        image_age_s=age,
        stale=age is not None and age > STALE_AFTER_SECONDS,
        bytes=len(resp.content),
    )
    if resp.status_code != 200:
        rec["result"] = "http_error"
        return rec, None
    if not resp.content.startswith(JPEG_MAGIC):
        rec["result"] = "not_jpeg"
        return rec, None

    digest = hashlib.sha256(resp.content).hexdigest()
    rec["sha256"] = digest
    if digest == last_hash:
        rec["result"] = "duplicate"
        return rec, None

    key = f"raw/webcams/{cam_id}/{key_timestamp(fetched_at)}.jpg"
    buffer.put(key, resp.content)  # bytes exactly as received
    rec.update(result="saved", key=key)
    return rec, digest


def poll_once(client, cameras, hashes: dict, buffer: Buffer) -> list[dict]:
    records = []
    for cam_id, url in cameras:
        try:
            rec, new_hash = fetch_camera(client, cam_id, url, hashes.get(cam_id), buffer)
        except Exception as exc:  # one bad camera must never stop the others
            log.exception("camera %s failed", cam_id)
            rec = {"camera_id": cam_id, "url": url, "fetched_at": iso_utc(utc_now()),
                   "result": "error", "error": repr(exc)}
            new_hash = None
        if new_hash:
            hashes[cam_id] = new_hash
        records.append(rec)
    return records


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    cameras = load_cameras(settings.cameras_csv)
    buffer = Buffer(settings.data_dir / "buffer")
    state = JsonState(settings.data_dir / "state" / "webcam_hashes.json")
    uploader = Uploader.from_settings(settings)
    log.info("starting: %d camera views, polling every %ds", len(cameras), POLL_SECONDS)

    with make_client(settings.contact_email) as client:
        while True:
            started = time.monotonic()
            cycle_at = utc_now()
            records = poll_once(client, cameras, state.data, buffer)
            state.save()
            buffer.put(
                f"logs/webcams/{key_timestamp(cycle_at)}.jsonl",
                "".join(json.dumps(r, sort_keys=True) + "\n" for r in records).encode(),
            )
            uploaded, failed = uploader.drain(buffer)
            counts = Counter(r["result"] for r in records)
            log.info("cycle %s | uploaded %d, upload failures %d, still buffered %d",
                     dict(counts), uploaded, failed, len(buffer.pending()))
            if failed == 0 and counts["saved"] + counts["duplicate"] > 0:
                ping(client, settings.healthcheck_webcams)
            time.sleep(max(0.0, POLL_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    run()
