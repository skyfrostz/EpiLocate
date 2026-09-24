from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


EXPECTED_PROTOCOL_ID = "formal-series-selection-rule-b-v1"
EXPECTED_PROTOCOL_SHA256 = "16c9d104c9a5d7dcbcff5dee14037d45664f8351078fb4741f930e0d6af2b868"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_path: Path
    bundle_path: Path
    environment: str = "production"
    allowed_hosts: tuple[str, ...] = ("review.epilocate.cn", "localhost", "127.0.0.1", "testserver")
    allowed_origins: tuple[str, ...] = ("https://review.epilocate.cn",)
    session_hours: int = 8
    secure_cookies: bool = True
    trust_proxy_headers: bool = False

    @property
    def production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def session_cookie_name(self) -> str:
        return "__Host-epilocate_session" if self.secure_cookies else "epilocate_session"

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("EPILOCATE_ENV", "production")
        default_secure = environment.lower() == "production"
        hosts = tuple(
            item.strip()
            for item in os.getenv(
                "EPILOCATE_ALLOWED_HOSTS",
                "review.epilocate.cn,localhost,127.0.0.1,testserver",
            ).split(",")
            if item.strip()
        )
        origins = tuple(
            item.strip().rstrip("/")
            for item in os.getenv("EPILOCATE_ALLOWED_ORIGINS", "https://review.epilocate.cn").split(",")
            if item.strip()
        )
        return cls(
            database_path=Path(
                os.getenv("EPILOCATE_DATABASE", "/var/lib/epilocate-review/review.sqlite3")
            ).expanduser(),
            bundle_path=Path(
                os.getenv("EPILOCATE_BUNDLE", "/opt/epilocate-review/review_bundle/bundle.json")
            ).expanduser(),
            environment=environment,
            allowed_hosts=hosts,
            allowed_origins=origins,
            session_hours=int(os.getenv("EPILOCATE_SESSION_HOURS", "8")),
            secure_cookies=_env_bool("EPILOCATE_SECURE_COOKIES", default_secure),
            trust_proxy_headers=_env_bool("EPILOCATE_TRUST_PROXY_HEADERS", False),
        )
