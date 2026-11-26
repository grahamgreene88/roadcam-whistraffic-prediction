"""Runtime settings, all from environment variables (see .env.example)."""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable {name}")
    return value


def _optional(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    contact_email: str
    r2_endpoint_url: str
    r2_bucket: str
    r2_access_key_id: str
    r2_secret_access_key: str
    cameras_csv: Path
    healthcheck_webcams: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(_require("DATA_DIR")),
            contact_email=_require("CONTACT_EMAIL"),
            r2_endpoint_url=_require("R2_ENDPOINT_URL"),
            r2_bucket=_require("R2_BUCKET"),
            r2_access_key_id=_require("R2_ACCESS_KEY_ID"),
            r2_secret_access_key=_require("R2_SECRET_ACCESS_KEY"),
            cameras_csv=Path(
                os.environ.get("CAMERAS_CSV", REPO_ROOT / "config" / "sea_to_sky_cameras.csv")
            ),
            healthcheck_webcams=_optional("HEALTHCHECK_URL_WEBCAMS"),
        )
