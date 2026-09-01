"""Environment-based application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _csv(name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, "").split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    slack_bot_token: str
    slack_app_token: str
    openai_api_key: str
    openai_model: str
    notion_token: str | None
    notion_root_page_ids: tuple[str, ...]
    google_oauth_token_file: str | None
    slurm_ssh_target: str | None
    slurm_ssh_identity_file: str | None
    slurm_ssh_known_hosts_file: str | None
    slurm_ssh_timeout_seconds: int
    slurm_status_channel_id: str | None
    slurm_status_interval_seconds: int
    slurm_status_start_at: datetime | None
    timezone: str
    enabled_features: frozenset[str]

    @classmethod
    def from_env(cls) -> Settings:
        enabled_features = frozenset(
            _csv("SKIML_FEATURES") or ("knowledge", "meetings", "server_status")
        )

        def feature_value(feature: str, name: str) -> str | None:
            return _required(name) if feature in enabled_features else None

        status_channel_id = os.getenv("SLURM_STATUS_CHANNEL_ID", "").strip() or None
        status_start_at: datetime | None = None
        if status_channel_id:
            status_start_at = datetime.fromisoformat(_required("SLURM_STATUS_START_AT"))
            if status_start_at.tzinfo is None or status_start_at.utcoffset() is None:
                raise ValueError("SLURM_STATUS_START_AT must include a timezone offset")

        return cls(
            slack_bot_token=_required("SLACK_BOT_TOKEN"),
            slack_app_token=_required("SLACK_APP_TOKEN"),
            openai_api_key=_required("OPENAI_API_KEY"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            notion_token=feature_value("knowledge", "NOTION_TOKEN"),
            notion_root_page_ids=_csv("NOTION_ROOT_PAGE_IDS"),
            google_oauth_token_file=feature_value("meetings", "GOOGLE_OAUTH_TOKEN_FILE"),
            slurm_ssh_target=feature_value("server_status", "SLURM_SSH_TARGET"),
            slurm_ssh_identity_file=os.getenv("SLURM_SSH_IDENTITY_FILE") or None,
            slurm_ssh_known_hosts_file=os.getenv("SLURM_SSH_KNOWN_HOSTS_FILE") or None,
            slurm_ssh_timeout_seconds=int(os.getenv("SLURM_SSH_TIMEOUT_SECONDS", "10")),
            slurm_status_channel_id=status_channel_id,
            slurm_status_interval_seconds=int(os.getenv("SLURM_STATUS_INTERVAL_SECONDS", "1800")),
            slurm_status_start_at=status_start_at,
            timezone=os.getenv("LAB_TIMEZONE", "Asia/Seoul"),
            enabled_features=enabled_features,
        )
