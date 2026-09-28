from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .core.models import AlertProfile, Severity, SoundMode, SoundPolicy


@dataclass(frozen=True, slots=True)
class BatteryConfig:
    enabled: bool = True
    warning_threshold: float = 20.0
    critical_threshold: float = 10.0
    reset_threshold: float = 25.0
    poll_interval: float = 5.0
    warning_profile: str = "battery_warning"
    critical_profile: str = "battery_critical"

    def __post_init__(self) -> None:
        if not 0 <= self.critical_threshold <= self.warning_threshold <= 100:
            raise ValueError("battery thresholds must satisfy 0 <= critical <= warning <= 100")
        if not self.warning_threshold <= self.reset_threshold <= 100:
            raise ValueError("battery reset_threshold must be >= warning_threshold and <= 100")
        if self.poll_interval <= 0:
            raise ValueError("battery poll_interval must be > 0")


@dataclass(frozen=True, slots=True)
class ThermalBandConfig:
    warning: float
    critical: float
    warning_duration: float
    critical_duration: float
    recover: float

    def __post_init__(self) -> None:
        if self.recover >= self.warning:
            raise ValueError("thermal recover temperature must be below warning temperature")
        if self.warning >= self.critical:
            raise ValueError("thermal warning temperature must be below critical temperature")
        if self.warning_duration < 0 or self.critical_duration < 0:
            raise ValueError("thermal durations must be >= 0")


@dataclass(frozen=True, slots=True)
class ThermalConfig:
    enabled: bool = True
    poll_interval: float = 2.0
    warning_profile: str = "thermal_warning"
    critical_profile: str = "thermal_critical"
    cpu: ThermalBandConfig = field(default_factory=lambda: ThermalBandConfig(90, 97, 20, 5, 80))
    gpu: ThermalBandConfig = field(default_factory=lambda: ThermalBandConfig(85, 92, 20, 5, 75))
    nvme: ThermalBandConfig = field(default_factory=lambda: ThermalBandConfig(75, 85, 30, 10, 65))

    def __post_init__(self) -> None:
        if self.poll_interval <= 0:
            raise ValueError("thermal poll_interval must be > 0")


@dataclass(frozen=True, slots=True)
class VpnConfig:
    enabled: bool = True
    poll_interval: float = 2.0
    watch: tuple[str, ...] = ()
    disconnect_profile: str = "vpn_disconnect"

    def __post_init__(self) -> None:
        if self.poll_interval <= 0:
            raise ValueError("vpn poll_interval must be > 0")


@dataclass(frozen=True, slots=True)
class AppConfig:
    profiles: dict[str, AlertProfile]
    battery: BatteryConfig = field(default_factory=BatteryConfig)
    thermal: ThermalConfig = field(default_factory=ThermalConfig)
    vpn: VpnConfig = field(default_factory=VpnConfig)

    def __post_init__(self) -> None:
        required = {
            self.battery.warning_profile,
            self.battery.critical_profile,
            self.thermal.warning_profile,
            self.thermal.critical_profile,
            self.vpn.disconnect_profile,
        }
        missing = sorted(required - self.profiles.keys())
        if missing:
            raise ValueError(f"missing alert profile(s): {', '.join(missing)}")


def default_profiles() -> dict[str, AlertProfile]:
    return {
        "battery_warning": AlertProfile(
            name="battery_warning",
            severity=Severity.WARNING,
            sound=SoundPolicy(sound="warning-medium", mode=SoundMode.LOOP, volume=0.85),
        ),
        "battery_critical": AlertProfile(
            name="battery_critical",
            severity=Severity.CRITICAL,
            sound=SoundPolicy(sound="warning-critical", mode=SoundMode.LOOP, volume=1.0),
        ),
        "thermal_warning": AlertProfile(
            name="thermal_warning",
            severity=Severity.WARNING,
            sound=SoundPolicy(
                sound="warning-urgent",
                mode=SoundMode.INTERVAL,
                interval_seconds=60.0,
                volume=0.85,
            ),
        ),
        "thermal_critical": AlertProfile(
            name="thermal_critical",
            severity=Severity.CRITICAL,
            sound=SoundPolicy(
                sound="warning-critical",
                mode=SoundMode.REPEAT,
                repeat_count=3,
                repeat_gap_seconds=1.0,
                volume=1.0,
            ),
        ),
        "vpn_disconnect": AlertProfile(
            name="vpn_disconnect",
            severity=Severity.WARNING,
            sound=SoundPolicy(sound="disconnect", mode=SoundMode.ONCE, volume=0.8),
        ),
    }


def default_config() -> AppConfig:
    return AppConfig(profiles=default_profiles())


def default_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "syschime" / "config.toml"


def _sound_policy(data: dict, fallback: SoundPolicy) -> SoundPolicy:
    return SoundPolicy(
        sound=str(data.get("sound", fallback.sound)),
        mode=SoundMode(str(data.get("mode", fallback.mode.value))),
        repeat_count=int(data.get("repeat_count", fallback.repeat_count)),
        repeat_gap_seconds=float(data.get("repeat_gap_seconds", fallback.repeat_gap_seconds)),
        interval_seconds=float(data.get("interval_seconds", fallback.interval_seconds)),
        volume=float(data.get("volume", fallback.volume)),
    )


def _profile(name: str, data: dict, fallback: AlertProfile) -> AlertProfile:
    return AlertProfile(
        name=name,
        severity=Severity(str(data.get("severity", fallback.severity.value))),
        persistent=bool(data.get("persistent", fallback.persistent)),
        sound=_sound_policy(data, fallback.sound),
    )


def _thermal_band(data: dict, fallback: ThermalBandConfig) -> ThermalBandConfig:
    return ThermalBandConfig(
        warning=float(data.get("warning", fallback.warning)),
        critical=float(data.get("critical", fallback.critical)),
        warning_duration=float(data.get("warning_duration", fallback.warning_duration)),
        critical_duration=float(data.get("critical_duration", fallback.critical_duration)),
        recover=float(data.get("recover", fallback.recover)),
    )


def load_config(path: Path | None = None) -> AppConfig:
    defaults = default_config()
    path = path or default_config_path()
    if not path.exists():
        return defaults

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    profile_data = raw.get("alerts", {}).get("profiles", {})
    profiles = dict(defaults.profiles)
    for name, data in profile_data.items():
        fallback = profiles.get(
            name,
            AlertProfile(
                name=name,
                severity=Severity.WARNING,
                sound=SoundPolicy(),
            ),
        )
        profiles[name] = _profile(name, data, fallback)

    plugins = raw.get("plugins", {})
    battery_raw = plugins.get("battery", {})
    thermal_raw = plugins.get("thermal", {})
    vpn_raw = plugins.get("vpn", {})

    battery = BatteryConfig(
        enabled=bool(battery_raw.get("enabled", defaults.battery.enabled)),
        warning_threshold=float(battery_raw.get("warning_threshold", defaults.battery.warning_threshold)),
        critical_threshold=float(battery_raw.get("critical_threshold", defaults.battery.critical_threshold)),
        reset_threshold=float(battery_raw.get("reset_threshold", defaults.battery.reset_threshold)),
        poll_interval=float(battery_raw.get("poll_interval", defaults.battery.poll_interval)),
        warning_profile=str(battery_raw.get("warning_profile", defaults.battery.warning_profile)),
        critical_profile=str(battery_raw.get("critical_profile", defaults.battery.critical_profile)),
    )

    thermal = ThermalConfig(
        enabled=bool(thermal_raw.get("enabled", defaults.thermal.enabled)),
        poll_interval=float(thermal_raw.get("poll_interval", defaults.thermal.poll_interval)),
        warning_profile=str(thermal_raw.get("warning_profile", defaults.thermal.warning_profile)),
        critical_profile=str(thermal_raw.get("critical_profile", defaults.thermal.critical_profile)),
        cpu=_thermal_band(thermal_raw.get("cpu", {}), defaults.thermal.cpu),
        gpu=_thermal_band(thermal_raw.get("gpu", {}), defaults.thermal.gpu),
        nvme=_thermal_band(thermal_raw.get("nvme", {}), defaults.thermal.nvme),
    )

    watch = vpn_raw.get("watch", list(defaults.vpn.watch))
    if not isinstance(watch, list) or not all(isinstance(x, str) for x in watch):
        raise ValueError("plugins.vpn.watch must be a list of connection names")
    vpn = VpnConfig(
        enabled=bool(vpn_raw.get("enabled", defaults.vpn.enabled)),
        poll_interval=float(vpn_raw.get("poll_interval", defaults.vpn.poll_interval)),
        watch=tuple(watch),
        disconnect_profile=str(vpn_raw.get("disconnect_profile", defaults.vpn.disconnect_profile)),
    )

    config = AppConfig(profiles=profiles, battery=battery, thermal=thermal, vpn=vpn)

    # Fail fast for mistyped built-in names and missing custom sound files.
    from .core.audio import resolve_sound

    for profile in config.profiles.values():
        if profile.sound.mode != SoundMode.NONE:
            resolve_sound(profile.sound.sound)
    return config
