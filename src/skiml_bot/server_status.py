"""On-demand Slurm server status domain logic."""

from __future__ import annotations

import re
from dataclasses import dataclass

MENTION_PATTERN = re.compile(r"<@[A-Z0-9]+>", re.IGNORECASE)
SERVER_PATTERN = re.compile(r"(?:연구실\s*서버|서버|slurm|노드)", re.IGNORECASE)
STATUS_PATTERN = re.compile(
    r"(?:상태|status).*(?:알려|일려|확인|보여|체크|어때)|"
    r"(?:알려|일려|확인|보여|체크).*(?:상태|status)",
    re.IGNORECASE,
)
STORAGE_DISPLAY_LIMIT = 3
STORAGE_WARNING_PERCENT = 90


def is_server_status_request(text: str) -> bool:
    """Return true only for a mentioned, explicit server-status request."""
    if MENTION_PATTERN.search(text) is None:
        return False
    command = MENTION_PATTERN.sub("", text).strip()
    return SERVER_PATTERN.search(command) is not None and STATUS_PATTERN.search(command) is not None


@dataclass(frozen=True)
class SlurmNode:
    name: str
    state: str
    reason: str | None = None

    @property
    def is_drain(self) -> bool:
        normalized = self.state.casefold().rstrip("*~#+")
        return normalized.startswith(("drain", "drng"))


@dataclass(frozen=True)
class StorageVolume:
    filesystem: str
    size: str
    used: str
    available: str
    use_percent: int
    mount_point: str


@dataclass(frozen=True)
class ServerStatus:
    nodes: tuple[SlurmNode, ...]
    storage: tuple[StorageVolume, ...] = ()

    @property
    def drain_nodes(self) -> tuple[SlurmNode, ...]:
        return tuple(node for node in self.nodes if node.is_drain)

    @property
    def low_storage_volumes(self) -> tuple[StorageVolume, ...]:
        return tuple(
            volume for volume in self.storage if volume.use_percent >= STORAGE_WARNING_PERCENT
        )

    def for_slack(self) -> str:
        drained = self.drain_nodes
        lines = [
            "*[연구실 서버 상태]*",
            "*Master SSH* — 🟢 접속 정상",
            f"*전체 노드* — {len(self.nodes)}개",
            f"*DRAIN 계열* — {len(drained)}개",
        ]
        if not drained:
            lines.append("🟢 DRAIN 상태인 노드가 없습니다.")
        else:
            lines.extend(_format_drain_node(node) for node in drained)
        if self.storage:
            lines.append("*스토리지 여유 공간 - 상위 3개*")
            lines.extend(
                _format_storage_volume(volume) for volume in self.storage[:STORAGE_DISPLAY_LIMIT]
            )
        return "\n".join(lines)


def _format_drain_node(node: SlurmNode) -> str:
    reason = f" — {node.reason}" if node.reason else ""
    return f"🟠 `{node.name}` — {node.state}{reason}"


def _format_storage_volume(volume: StorageVolume) -> str:
    indicator = "🔴" if volume.use_percent >= 90 else "🟢"
    return (
        f"{indicator} `{volume.mount_point}` — {volume.available} 남음 / "
        f"{volume.size} ({volume.use_percent}% 사용)"
    )
