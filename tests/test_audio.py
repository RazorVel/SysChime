import asyncio
import unittest

from syschime.core.audio import AudioController, BUILTIN_SOUNDS, resolve_sound
from syschime.core.models import SoundMode, SoundPolicy


class FakeBackend:
    def __init__(self):
        self.calls = []
        self.gate = None

    async def play(self, path, volume):
        self.calls.append((path.name, volume))
        if self.gate is not None:
            await self.gate.wait()


class AudioControllerTests(unittest.IsolatedAsyncioTestCase):
    def test_all_builtin_sound_assets_exist(self):
        for name in BUILTIN_SOUNDS:
            self.assertTrue(resolve_sound(name).is_file(), name)

    async def test_once_plays_once(self):
        backend = FakeBackend()
        controller = AudioController(backend)
        await controller.start("x", SoundPolicy(sound="warning-soft", mode=SoundMode.ONCE))
        await controller.wait_idle("x")
        self.assertEqual(len(backend.calls), 1)

    async def test_repeat_plays_requested_count(self):
        backend = FakeBackend()
        controller = AudioController(backend)
        policy = SoundPolicy(
            sound="warning-soft",
            mode=SoundMode.REPEAT,
            repeat_count=3,
            repeat_gap_seconds=0,
        )
        await controller.start("x", policy)
        await controller.wait_idle("x")
        self.assertEqual(len(backend.calls), 3)

    async def test_loop_stops_on_cancel(self):
        backend = FakeBackend()
        backend.gate = asyncio.Event()
        controller = AudioController(backend)
        await controller.start("x", SoundPolicy(sound="warning-soft", mode=SoundMode.LOOP))
        await asyncio.sleep(0)
        self.assertEqual(len(backend.calls), 1)
        await controller.stop("x")
        self.assertNotIn("x", controller.active_keys)


class CommandAudioBackendTests(unittest.IsolatedAsyncioTestCase):
    def _backend(self, names):
        from syschime.core.audio import CommandAudioBackend

        backend = CommandAudioBackend.__new__(CommandAudioBackend)
        backend._backends = [(name, f"/usr/bin/{name}") for name in names]
        backend._preferred = None
        return backend

    def test_backend_order_prefers_session_audio_over_direct_alsa(self):
        from syschime.core.audio import CommandAudioBackend

        self.assertEqual(
            CommandAudioBackend.BACKEND_ORDER,
            ("pw-play", "paplay", "ffplay", "aplay"),
        )

    def test_pw_play_uses_notification_media_role(self):
        from pathlib import Path
        from syschime.core.audio import CommandAudioBackend

        args = CommandAudioBackend._args(
            "pw-play", "/usr/bin/pw-play", Path("alert.wav"), 0.8
        )
        self.assertIn("--media-role=Notification", args)
        self.assertIn("--volume=0.800", args)

    async def test_falls_back_when_first_backend_fails(self):
        from pathlib import Path

        backend = self._backend(["pw-play", "paplay"])
        calls = []

        async def fake_play_one(name, executable, path, volume):
            calls.append(name)
            if name == "pw-play":
                raise RuntimeError("no PipeWire server")

        backend._play_one = fake_play_one
        await backend.play(Path("alert.wav"), 0.8)
        self.assertEqual(calls, ["pw-play", "paplay"])
        self.assertEqual(backend.selected_backend, "paplay")

    async def test_all_backend_failures_are_reported(self):
        from pathlib import Path
        from syschime.core.audio import AudioPlaybackError

        backend = self._backend(["pw-play", "aplay"])

        async def fake_play_one(name, executable, path, volume):
            raise RuntimeError(f"{name} unavailable")

        backend._play_one = fake_play_one
        with self.assertRaises(AudioPlaybackError) as ctx:
            await backend.play(Path("alert.wav"), 0.8)
        message = str(ctx.exception)
        self.assertIn("pw-play unavailable", message)
        self.assertIn("aplay unavailable", message)


if __name__ == "__main__":
    unittest.main()
