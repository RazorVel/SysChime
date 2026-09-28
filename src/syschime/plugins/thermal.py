from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import ThermalBandConfig, ThermalConfig
from ..core.models import AlertAction, RaiseAlert, ResolveAlert


@dataclass(frozen=True, slots=True)
class ThermalReading:
    category: str
    sensor_id: str
    label: str
    temperature_c: float


class ThermalProvider(Protocol):
    async def readings(self) -> list[ThermalReading]: ...


@dataclass(slots=True)
class _ThermalState:
    level: str | None = None
    warning_since: float | None = None
    critical_since: float | None = None


class ThermalStateMachine:
    def __init__(self, config: ThermalConfig) -> None:
        self.config = config
        self._states: dict[str, _ThermalState] = {}

    def evaluate(
        self,
        category: str,
        temperature_c: float,
        sensor_label: str,
        now: float,
    ) -> list[AlertAction]:
        band = self._band(category)
        if band is None:
            return []
        state = self._states.setdefault(category, _ThermalState())
        actions: list[AlertAction] = []
        warning_key = f"thermal:{category}:warning"
        critical_key = f"thermal:{category}:critical"

        if state.level is not None and temperature_c <= band.recover:
            actions.append(ResolveAlert(critical_key if state.level == "critical" else warning_key))
            state.level = None
            state.warning_since = None
            state.critical_since = None
            return actions

        if temperature_c >= band.critical:
            if state.critical_since is None:
                state.critical_since = now
            if state.warning_since is None:
                state.warning_since = now

            if state.level != "critical" and now - state.critical_since >= band.critical_duration:
                if state.level == "warning":
                    actions.append(ResolveAlert(warning_key))
                state.level = "critical"
                actions.append(
                    RaiseAlert(
                        key=critical_key,
                        title=f"Critical {category.upper()} Temperature",
                        message=f"{sensor_label}: {temperature_c:.1f}°C",
                        profile_name=self.config.critical_profile,
                        metadata={"category": category, "temperature_c": f"{temperature_c:.1f}"},
                    )
                )
            return actions

        state.critical_since = None

        if temperature_c >= band.warning:
            if state.warning_since is None:
                state.warning_since = now
            if state.level is None and now - state.warning_since >= band.warning_duration:
                state.level = "warning"
                actions.append(
                    RaiseAlert(
                        key=warning_key,
                        title=f"High {category.upper()} Temperature",
                        message=f"{sensor_label}: {temperature_c:.1f}°C",
                        profile_name=self.config.warning_profile,
                        metadata={"category": category, "temperature_c": f"{temperature_c:.1f}"},
                    )
                )
            return actions

        state.warning_since = None
        return actions

    def _band(self, category: str) -> ThermalBandConfig | None:
        return {
            "cpu": self.config.cpu,
            "gpu": self.config.gpu,
            "nvme": self.config.nvme,
        }.get(category)
