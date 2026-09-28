from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .models import AlertSpec, Severity

LOG = logging.getLogger(__name__)


class DbusNotifier:
    """Desktop notifications using org.freedesktop.Notifications."""

    SERVICE = "org.freedesktop.Notifications"
    PATH = "/org/freedesktop/Notifications"
    INTERFACE = "org.freedesktop.Notifications"

    def __init__(self) -> None:
        self._bus = None
        self._interface = None
        self._callbacks: dict[int, Callable[[], None]] = {}

    async def connect(self) -> None:
        if self._interface is not None:
            return

        from dbus_next.aio import MessageBus

        bus = await MessageBus().connect()
        introspection = await bus.introspect(self.SERVICE, self.PATH)
        obj = bus.get_proxy_object(self.SERVICE, self.PATH, introspection)
        interface = obj.get_interface(self.INTERFACE)
        interface.on_notification_closed(self._on_notification_closed)
        interface.on_action_invoked(self._on_action_invoked)
        self._bus = bus
        self._interface = interface

    async def show(self, spec: AlertSpec, on_acknowledge: Callable[[], None]) -> int:
        await self.connect()
        assert self._interface is not None

        from dbus_next import Variant

        urgency = {
            Severity.INFO: 0,
            Severity.WARNING: 1,
            Severity.CRITICAL: 2,
        }[spec.profile.severity]
        hints = {
            "urgency": Variant("y", urgency),
            "category": Variant("s", f"device.{spec.source}"),
        }
        expire_timeout = 0 if spec.profile.persistent else -1
        notification_id = await self._interface.call_notify(
            "SysChime",
            0,
            "dialog-warning",
            spec.title,
            spec.message,
            ["ack", "Acknowledge"],
            hints,
            expire_timeout,
        )
        self._callbacks[int(notification_id)] = on_acknowledge
        return int(notification_id)

    async def close(self, notification_id: int) -> None:
        if self._interface is None:
            return
        # Remove callback first: a programmatic close is resolution, not a user ack.
        self._callbacks.pop(notification_id, None)
        try:
            await self._interface.call_close_notification(notification_id)
        except Exception as exc:  # notification may already be gone
            LOG.debug("failed to close notification %s: %s", notification_id, exc)

    async def close_bus(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
        self._bus = None
        self._interface = None
        self._callbacks.clear()

    def _on_notification_closed(self, notification_id: int, reason: int) -> None:
        callback = self._callbacks.pop(int(notification_id), None)
        if callback is not None:
            callback()

    def _on_action_invoked(self, notification_id: int, action_key: str) -> None:
        if action_key != "ack":
            return
        callback = self._callbacks.pop(int(notification_id), None)
        if callback is not None:
            callback()
            if self._interface is not None:
                asyncio.create_task(self._interface.call_close_notification(notification_id))
