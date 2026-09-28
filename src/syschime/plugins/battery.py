from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ..config import BatteryConfig
from ..core.models import AlertAction, RaiseAlert, ResolveAlert


class BatteryState(StrEnum):
    UNKNOWN = "unknown"
    CHARGING = "charging"
    DISCHARGING = "discharging"
    EMPTY = "empty"
    FULL = "full"
    PENDING_CHARGE = "pending-charge"
    PENDING_DISCHARGE = "pending-discharge"


@dataclass(frozen=True, slots=True)
class BatterySnapshot:
    percentage: float
    state: BatteryState


class BatteryProvider(Protocol):
    async def snapshot(self) -> BatterySnapshot: ...


class BatteryStateMachine:
    WARNING_KEY = "battery:warning"
    CRITICAL_KEY = "battery:critical"

    def __init__(self, config: BatteryConfig) -> None:
        self.config = config
        self.level: str | None = None

    def evaluate(self, snapshot: BatterySnapshot) -> list[AlertAction]:
        actions: list[AlertAction] = []
        pct = snapshot.percentage
        discharging = snapshot.state in {BatteryState.DISCHARGING, BatteryState.PENDING_DISCHARGE}

        if not discharging:
            if self.level == "warning":
                actions.append(ResolveAlert(self.WARNING_KEY))
            elif self.level == "critical":
                actions.append(ResolveAlert(self.CRITICAL_KEY))
            self.level = None
            return actions

        if self.level is not None and pct > self.config.reset_threshold:
            key = self.WARNING_KEY if self.level == "warning" else self.CRITICAL_KEY
            actions.append(ResolveAlert(key))
            self.level = None

        if self.level is None:
            if pct <= self.config.critical_threshold:
                self.level = "critical"
                actions.append(self._raise_critical(pct))
            elif pct <= self.config.warning_threshold:
                self.level = "warning"
                actions.append(self._raise_warning(pct))
            return actions

        if self.level == "warning" and pct <= self.config.critical_threshold:
            actions.append(ResolveAlert(self.WARNING_KEY))
            self.level = "critical"
            actions.append(self._raise_critical(pct))

        return actions

    def _raise_warning(self, pct: float) -> RaiseAlert:
        return RaiseAlert(
            key=self.WARNING_KEY,
            title="Low Battery",
            message=f"Battery is at {pct:.0f}% and discharging.",
            profile_name=self.config.warning_profile,
            metadata={"percentage": f"{pct:.1f}"},
        )

    def _raise_critical(self, pct: float) -> RaiseAlert:
        return RaiseAlert(
            key=self.CRITICAL_KEY,
            title="Critical Battery",
            message=f"Battery is at {pct:.0f}%. Connect the charger now.",
            profile_name=self.config.critical_profile,
            metadata={"percentage": f"{pct:.1f}"},
        )
