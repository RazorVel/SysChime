from __future__ import annotations

import asyncio
import logging
import signal
import time
from collections.abc import Awaitable, Callable

from .config import AppConfig
from .core.alerts import AlertManager
from .core.audio import AudioController
from .core.models import AlertAction, AlertSpec, RaiseAlert, ResolveAlert
from .core.notification import DbusNotifier
from .platform.hwmon import HwmonThermalProvider
from .platform.networkmanager import NetworkManagerVpnProvider
from .platform.upower import UPowerBatteryProvider
from .plugins.battery import BatteryStateMachine
from .plugins.thermal import ThermalStateMachine
from .plugins.vpn import VpnStateMachine

LOG = logging.getLogger(__name__)


async def dispatch_action(action: AlertAction, source: str, config: AppConfig, manager: AlertManager) -> None:
    if isinstance(action, ResolveAlert):
        await manager.resolve(action.key)
        return
    if isinstance(action, RaiseAlert):
        profile = config.profiles[action.profile_name]
        await manager.raise_alert(
            AlertSpec(
                key=action.key,
                source=source,
                title=action.title,
                message=action.message,
                profile=profile,
                metadata=action.metadata,
            )
        )
        return
    raise TypeError(f"unknown action: {action!r}")


async def run_battery(config: AppConfig, manager: AlertManager) -> None:
    provider = UPowerBatteryProvider()
    machine = BatteryStateMachine(config.battery)
    try:
        while True:
            snapshot = await provider.snapshot()
            for action in machine.evaluate(snapshot):
                await dispatch_action(action, "battery", config, manager)
            await asyncio.sleep(config.battery.poll_interval)
    finally:
        await provider.close()


async def run_thermal(config: AppConfig, manager: AlertManager) -> None:
    provider = HwmonThermalProvider()
    machine = ThermalStateMachine(config.thermal)
    while True:
        readings = await provider.readings()
        # Use the hottest sensor in each category to avoid duplicate alerts.
        hottest = {}
        for reading in readings:
            current = hottest.get(reading.category)
            if current is None or reading.temperature_c > current.temperature_c:
                hottest[reading.category] = reading

        now = time.monotonic()
        for category in ("cpu", "gpu", "nvme"):
            reading = hottest.get(category)
            if reading is None:
                continue
            for action in machine.evaluate(category, reading.temperature_c, reading.label, now):
                await dispatch_action(action, "thermal", config, manager)
        await asyncio.sleep(config.thermal.poll_interval)


async def run_vpn(config: AppConfig, manager: AlertManager) -> None:
    provider = NetworkManagerVpnProvider()
    machine = VpnStateMachine(config.vpn)
    try:
        while True:
            active = await provider.active_vpns()
            for action in machine.evaluate(active):
                await dispatch_action(action, "vpn", config, manager)
            await asyncio.sleep(config.vpn.poll_interval)
    finally:
        await provider.close()


async def supervise(name: str, factory: Callable[[], Awaitable[None]], retry_seconds: float = 10.0) -> None:
    while True:
        try:
            await factory()
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.exception("%s plugin crashed; retrying in %.0fs", name, retry_seconds)
            await asyncio.sleep(retry_seconds)


async def run_daemon(config: AppConfig) -> None:
    notifier = DbusNotifier()
    audio = AudioController()
    manager = AlertManager(notifier, audio)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    tasks: list[asyncio.Task[None]] = []
    if config.battery.enabled:
        tasks.append(asyncio.create_task(supervise("battery", lambda: run_battery(config, manager))))
    if config.thermal.enabled:
        tasks.append(asyncio.create_task(supervise("thermal", lambda: run_thermal(config, manager))))
    if config.vpn.enabled:
        tasks.append(asyncio.create_task(supervise("vpn", lambda: run_vpn(config, manager))))

    if not tasks:
        LOG.warning("no plugins are enabled")

    try:
        await stop_event.wait()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await manager.shutdown()
        await notifier.close_bus()
