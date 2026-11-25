"""Central configuration. Everything is overridable through environment variables
(loaded from a local, git-ignored .env file) so tests can point at temp dirs."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is in requirements
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env")


def _path(env: str, default: Path) -> Path:
    value = os.getenv(env)
    return Path(value) if value else default


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: _path("SKILLRADAR_DATA_DIR", PROJECT_ROOT / "data"))
    db_path: Path | None = None
    # demo sandboxes read the real ESCO CSVs (read-only) instead of copying 33 MB
    esco_dir_override: Path | None = None
    # demos inject a dummy key for the in-memory mock server (never sent to the network)
    softon_api_key_override: str | None = None
    # Synthetic demo mode (SKILLRADAR_DEMO=1): separate data dir, synthetic data, live API always disabled
    demo_mode: bool = field(default_factory=lambda: os.getenv("SKILLRADAR_DEMO", "").lower() in ("1", "true", "yes"))

    # Softon API
    softon_base_url: str = field(default_factory=lambda: os.getenv("SOFTON_BASE_URL", "https://api.softon.dev/v1"))
    softon_city: str = field(default_factory=lambda: os.getenv("SOFTON_CITY", "Bakı"))
    softon_page_limit: int = field(default_factory=lambda: int(os.getenv("SOFTON_PAGE_LIMIT", "100")))
    # Free plan = 100 requests / month (docs/vendor/softon_schema.json -> limits.plans)
    softon_monthly_budget: int = field(default_factory=lambda: int(os.getenv("SOFTON_MONTHLY_BUDGET", "100")))
    softon_max_pages_per_run: int = field(default_factory=lambda: int(os.getenv("SOFTON_MAX_PAGES_PER_RUN", "3")))
    softon_timeout_s: float = field(default_factory=lambda: float(os.getenv("SOFTON_TIMEOUT_S", "30")))
    softon_max_retries: int = field(default_factory=lambda: int(os.getenv("SOFTON_MAX_RETRIES", "3")))
    softon_backoff_s: float = field(default_factory=lambda: float(os.getenv("SOFTON_BACKOFF_S", "2")))
    # politeness delay between pages (free plan: 5 req/s) and requests kept in reserve for the month
    softon_page_delay_s: float = field(default_factory=lambda: float(os.getenv("SOFTON_PAGE_DELAY_S", "1")))
    softon_quota_reserve: int = field(default_factory=lambda: int(os.getenv("SOFTON_QUOTA_RESERVE", "5")))

    # Pipeline behaviour
    task_retries: int = field(default_factory=lambda: int(os.getenv("SKILLRADAR_TASK_RETRIES", "1")))
    task_retry_delay_s: float = field(default_factory=lambda: float(os.getenv("SKILLRADAR_TASK_RETRY_DELAY_S", "2")))
    # Block publication if the candidate dataset shrinks below this share of the last publication
    min_volume_ratio: float = field(default_factory=lambda: float(os.getenv("SKILLRADAR_MIN_VOLUME_RATIO", "0.5")))
    schedule_interval_hours: float = field(default_factory=lambda: float(os.getenv("SKILLRADAR_SCHEDULE_HOURS", "6")))

    def __post_init__(self) -> None:
        if self.db_path is None:
            self.db_path = _path("SKILLRADAR_DB_PATH", self.data_dir / "warehouse" / "skillradar.db")

    @property
    def softon_api_key(self) -> str | None:
        # read lazily, never stored in logs or DB
        if self.demo_mode and not self.softon_api_key_override:
            return None  # the synthetic demo never calls the live API
        return self.softon_api_key_override or os.getenv("SOFTON_API_KEY") or None

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def softon_raw_dir(self) -> Path:
        return self.raw_dir / "softon"

    @property
    def snapshot_dir(self) -> Path:
        return self.softon_raw_dir / "snapshots"

    @property
    def esco_dir(self) -> Path:
        return Path(self.esco_dir_override) if self.esco_dir_override else self.raw_dir / "esco"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure_dirs(self) -> None:
        for p in (self.snapshot_dir, self.processed_dir, self.log_dir, self.db_path.parent):
            p.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()
