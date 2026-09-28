from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Protocol

from .audio import AudioController
from .models import ActiveAlert, AlertSpec

LOG = logging.getLogger(__name__)


class Notifier(Protocol):
    async def show(self, spec: AlertSpec, on_acknowledge: Callable[[], None]) -> int: ...
    async def close(self, notification_id: int) -> None: ...


class AlertManager:
    def __init__(self, notifier: Notifier, audio: AudioController) -> None:
        self._notifier = notifier
        self._audio = audio
        self._active: dict[str, ActiveAlert] = {}
        self._lock = asyncio.Lock()

    @property
    def active(self) -> dict[str, ActiveAlert]:
        return dict(self._active)

    async def raise_alert(self, spec: AlertSpec) -> bool:
        async with self._lock:
            if spec.key in self._active:
                return False

            active = ActiveAlert(spec=spec)
            self._active[spec.key] = active
            try:
                notification_id = await self._notifier.show(
                    spec,
                    lambda key=spec.key: asyncio.create_task(self.acknowledge(key)),
                )
                active.notification_id = notification_id
            except Exception:
                self._active.pop(spec.key, None)
                raise

            try:
                await self._audio.start(spec.key, spec.profile.sound)
            except Exception as exc:
                # A missing/broken audio backend must not suppress the desktop alert.
                LOG.error("audio failed for alert %s; notification remains active: %s", spec.key, exc)

            LOG.info("raised alert %s: %s", spec.key, spec.message)
            return True

    async def acknowledge(self, key: str) -> bool:
        async with self._lock:
            active = self._active.get(key)
            if active is None or active.acknowledged:
                return False
            active.acknowledged = True
            await self._audio.stop(key)
            LOG.info("acknowledged alert %s", key)
            return True

    async def resolve(self, key: str) -> bool:
        async with self._lock:
            active = self._active.pop(key, None)
            if active is None:
                return False
            await self._audio.stop(key)
            if active.notification_id is not None:
                await self._notifier.close(active.notification_id)
            LOG.info("resolved alert %s", key)
            return True

    async def shutdown(self) -> None:
        for key in list(self._active):
            await self.resolve(key)
        await self._audio.stop_all()
