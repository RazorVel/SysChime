from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SoundMode(StrEnum):
    NONE = "none"
    ONCE = "once"
    REPEAT = "repeat"
    LOOP = "loop"
    INTERVAL = "interval"


@dataclass(frozen=True, slots=True)
class SoundPolicy:
    sound: str = "warning-medium"
    mode: SoundMode = SoundMode.ONCE
    repeat_count: int = 3
    repeat_gap_seconds: float = 1.0
    interval_seconds: float = 60.0
    volume: float = 0.8

    def __post_init__(self) -> None:
        if not 0.0 <= self.volume <= 1.0:
            raise ValueError("sound volume must be between 0.0 and 1.0")
        if self.repeat_count < 1:
            raise ValueError("repeat_count must be >= 1")
        if self.repeat_gap_seconds < 0:
            raise ValueError("repeat_gap_seconds must be >= 0")
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")


@dataclass(frozen=True, slots=True)
class AlertProfile:
    name: str
    severity: Severity
    sound: SoundPolicy
    persistent: bool = True


@dataclass(frozen=True, slots=True)
class AlertSpec:
    key: str
    source: str
    title: str
    message: str
    profile: AlertProfile
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ActiveAlert:
    spec: AlertSpec
    notification_id: int | None = None
    acknowledged: bool = False


@dataclass(frozen=True, slots=True)
class RaiseAlert:
    key: str
    title: str
    message: str
    profile_name: str
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResolveAlert:
    key: str


AlertAction = RaiseAlert | ResolveAlert
