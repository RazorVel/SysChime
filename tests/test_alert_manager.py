import asyncio
import unittest

from syschime.core.alerts import AlertManager
from syschime.core.models import AlertProfile, AlertSpec, Severity, SoundMode, SoundPolicy


class FakeNotifier:
    def __init__(self):
        self.shown = []
        self.closed = []
        self.callbacks = {}
        self.next_id = 1

    async def show(self, spec, on_acknowledge):
        nid = self.next_id
        self.next_id += 1
        self.shown.append(spec)
        self.callbacks[nid] = on_acknowledge
        return nid

    async def close(self, notification_id):
        self.closed.append(notification_id)
        self.callbacks.pop(notification_id, None)


class FakeAudio:
    def __init__(self):
        self.started = []
        self.stopped = []
        self.fail_start = False

    async def start(self, key, policy):
        self.started.append((key, policy))
        if self.fail_start:
            raise RuntimeError("audio unavailable")

    async def stop(self, key):
        self.stopped.append(key)

    async def stop_all(self):
        pass


class AlertManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.notifier = FakeNotifier()
        self.audio = FakeAudio()
        self.manager = AlertManager(self.notifier, self.audio)
        profile = AlertProfile(
            name="test",
            severity=Severity.WARNING,
            sound=SoundPolicy(mode=SoundMode.ONCE),
        )
        self.spec = AlertSpec("key", "test", "Title", "Message", profile)

    async def test_raise_is_idempotent(self):
        self.assertTrue(await self.manager.raise_alert(self.spec))
        self.assertFalse(await self.manager.raise_alert(self.spec))
        self.assertEqual(len(self.notifier.shown), 1)
        self.assertEqual(len(self.audio.started), 1)

    async def test_acknowledge_stops_audio_but_keeps_alert_active(self):
        await self.manager.raise_alert(self.spec)
        self.assertTrue(await self.manager.acknowledge("key"))
        self.assertIn("key", self.manager.active)
        self.assertTrue(self.manager.active["key"].acknowledged)
        self.assertIn("key", self.audio.stopped)

    async def test_resolve_closes_notification(self):
        await self.manager.raise_alert(self.spec)
        self.assertTrue(await self.manager.resolve("key"))
        self.assertNotIn("key", self.manager.active)
        self.assertEqual(self.notifier.closed, [1])

    async def test_notification_callback_acknowledges(self):
        await self.manager.raise_alert(self.spec)
        self.notifier.callbacks[1]()
        await asyncio.sleep(0)
        self.assertTrue(self.manager.active["key"].acknowledged)

    async def test_audio_failure_does_not_suppress_notification(self):
        self.audio.fail_start = True
        self.assertTrue(await self.manager.raise_alert(self.spec))
        self.assertIn("key", self.manager.active)
        self.assertEqual(len(self.notifier.shown), 1)


if __name__ == "__main__":
    unittest.main()
