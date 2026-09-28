from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from .config import default_config_path, load_config
from .core.alerts import AlertManager
from .core.audio import AudioController, BUILTIN_SOUNDS, CommandAudioBackend
from .core.models import AlertProfile, AlertSpec, Severity, SoundMode, SoundPolicy
from .core.notification import DbusNotifier
from .daemon import run_daemon
from .platform.hwmon import HwmonThermalProvider


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="syschime", description="Linux system-condition alert daemon")
    parser.add_argument("--config", type=Path, default=None, help="config TOML path")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("daemon", help="run the alert daemon")
    sub.add_parser("validate", help="validate configuration")
    sub.add_parser("sensors", help="list detected thermal sensors")

    sound = sub.add_parser("test-sound", help="play a built-in or custom sound once")
    sound.add_argument("sound", help="built-in sound name or audio file path")
    sound.add_argument("--volume", type=float, default=0.8)

    alert = sub.add_parser("test-alert", help="show a test notification and warning sound")
    alert.add_argument("--sound", default="warning-medium", help="built-in sound name or audio file path")
    alert.add_argument("--mode", choices=[m.value for m in SoundMode], default="once")
    alert.add_argument("--seconds", type=float, default=5.0, help="auto-resolve after N seconds")
    return parser


async def _test_sound(name: str, volume: float) -> None:
    backend = CommandAudioBackend()
    print(f"Detected audio backends: {', '.join(backend.available_backends)}")
    controller = AudioController(backend)
    policy = SoundPolicy(sound=name, mode=SoundMode.ONCE, volume=volume)
    await controller.start("cli-test", policy)
    await controller.wait_idle("cli-test")
    print(f"Played '{name}' via {backend.selected_backend}")


async def _test_alert(sound: str, mode: str, seconds: float) -> None:
    notifier = DbusNotifier()
    audio = AudioController()
    manager = AlertManager(notifier, audio)
    profile = AlertProfile(
        name="cli-test",
        severity=Severity.WARNING,
        sound=SoundPolicy(
            sound=sound,
            mode=SoundMode(mode),
            repeat_count=3,
            interval_seconds=2.0,
            volume=0.8,
        ),
    )
    await manager.raise_alert(
        AlertSpec(
            key="cli:test",
            source="test",
            title="SysChime Test Alert",
            message="If you can see and hear this, the alert path works.",
            profile=profile,
        )
    )
    try:
        await asyncio.sleep(max(0.1, seconds))
    finally:
        await manager.resolve("cli:test")
        await notifier.close_bus()


async def _sensors() -> None:
    readings = await HwmonThermalProvider().readings()
    if not readings:
        print("No supported CPU/GPU/NVMe hwmon temperature sensors detected.")
        return
    for reading in readings:
        print(f"{reading.category:5}  {reading.temperature_c:6.1f}°C  {reading.label}")


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config_path = args.config or default_config_path()

    if args.command == "validate":
        config = load_config(config_path)
        print(f"Configuration OK: {config_path if config_path.exists() else '(built-in defaults)'}")
        print(f"Profiles: {', '.join(sorted(config.profiles))}")
        return

    if args.command == "sensors":
        asyncio.run(_sensors())
        return

    if args.command == "test-sound":
        try:
            asyncio.run(_test_sound(args.sound, args.volume))
        except (RuntimeError, OSError) as exc:
            raise SystemExit(f"Audio test failed:\n{exc}") from exc
        return

    if args.command == "test-alert":
        asyncio.run(_test_alert(args.sound, args.mode, args.seconds))
        return

    if args.command == "daemon":
        config = load_config(config_path)
        asyncio.run(run_daemon(config))
        return

    raise SystemExit(2)
