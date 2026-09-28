from __future__ import annotations

import asyncio
import logging
import shutil
from importlib import resources
from pathlib import Path
from typing import Protocol

from .models import SoundMode, SoundPolicy

LOG = logging.getLogger(__name__)

BUILTIN_SOUNDS = {
    "warning-soft",
    "warning-medium",
    "warning-urgent",
    "warning-critical",
    "disconnect",
    "resolved",
}


class AudioBackend(Protocol):
    async def play(self, path: Path, volume: float) -> None: ...


class AudioPlaybackError(RuntimeError):
    """Raised when no available command-line backend can play an alert sound."""


class CommandAudioBackend:
    """Play WAV files through common Linux audio commands.

    Backends are tried at playback time, not merely selected because the binary
    exists. This matters on PipeWire desktops where (for example) ``aplay`` may
    be installed but have no usable default ALSA device.

    Preference order is native PipeWire, PulseAudio/pipewire-pulse, ffplay, and
    finally direct ALSA. The last successful backend is preferred on later
    plays.
    """

    BACKEND_ORDER = ("pw-play", "paplay", "ffplay", "aplay")

    def __init__(self) -> None:
        self._backends = self._detect_backends()
        self._preferred: str | None = None

    @staticmethod
    def _detect_backends() -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for name in CommandAudioBackend.BACKEND_ORDER:
            path = shutil.which(name)
            if path:
                found.append((name, path))
        if not found:
            raise RuntimeError(
                "No supported audio player found. Install PipeWire (pw-play), "
                "PulseAudio/pipewire-pulse (paplay), ffmpeg (ffplay), or "
                "ALSA utilities (aplay)."
            )
        return found

    @property
    def available_backends(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self._backends)

    @property
    def selected_backend(self) -> str | None:
        return self._preferred

    @staticmethod
    def _args(name: str, executable: str, path: Path, volume: float) -> list[str]:
        if name == "pw-play":
            # Notification role lets WirePlumber apply the normal policy/routing
            # for system alert sounds instead of treating them as music.
            return [
                executable,
                "--media-role=Notification",
                f"--volume={volume:.3f}",
                str(path),
            ]
        if name == "paplay":
            pulse_volume = round(volume * 65536)
            return [executable, f"--volume={pulse_volume}", str(path)]
        if name == "aplay":
            if volume != 1.0:
                LOG.debug("aplay backend cannot apply per-alert volume")
            return [executable, "-q", str(path)]
        return [
            executable,
            "-nodisp",
            "-autoexit",
            "-loglevel",
            "error",
            "-volume",
            str(round(volume * 100)),
            str(path),
        ]

    async def _play_one(self, name: str, executable: str, path: Path, volume: float) -> None:
        args = self._args(name, executable, path, volume)
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            raise

        message = stderr.decode(errors="replace").strip() if stderr else ""
        # ffplay may report an audio-device failure at error log level while
        # still returning status 0, so error-level stderr is significant there.
        failed = process.returncode != 0 or (name == "ffplay" and bool(message))
        if failed:
            detail = message or "no diagnostic output"
            raise AudioPlaybackError(
                f"{name} failed (exit {process.returncode}): {detail}"
            )

    async def play(self, path: Path, volume: float) -> None:
        backends = list(self._backends)
        if self._preferred is not None:
            backends.sort(key=lambda item: item[0] != self._preferred)

        failures: list[str] = []
        for name, executable in backends:
            try:
                await self._play_one(name, executable, path, volume)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failures.append(str(exc))
                LOG.debug("audio backend %s failed: %s", name, exc)
                continue
            self._preferred = name
            return

        joined = "\n  - ".join(failures)
        raise AudioPlaybackError(
            "All detected audio backends failed:\n  - " + joined
        )


def resolve_sound(sound: str) -> Path:
    path = Path(sound).expanduser()
    if path.is_absolute() or "/" in sound:
        if not path.is_file():
            raise FileNotFoundError(f"sound file not found: {path}")
        return path

    if sound not in BUILTIN_SOUNDS:
        available = ", ".join(sorted(BUILTIN_SOUNDS))
        raise ValueError(f"unknown built-in sound '{sound}'. Available: {available}")

    resource = resources.files("syschime").joinpath("assets", f"{sound}.wav")
    path = Path(str(resource))
    if not path.is_file():
        raise FileNotFoundError(f"built-in sound asset missing: {sound}")
    return path


class AudioController:
    def __init__(self, backend: AudioBackend | None = None) -> None:
        self._backend = backend
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def active_keys(self) -> set[str]:
        return set(self._tasks)

    def _get_backend(self) -> AudioBackend:
        if self._backend is None:
            self._backend = CommandAudioBackend()
        return self._backend

    async def start(self, key: str, policy: SoundPolicy) -> None:
        await self.stop(key)
        if policy.mode == SoundMode.NONE:
            return

        sound_path = resolve_sound(policy.sound)
        task = asyncio.create_task(
            self._run(key, sound_path, policy),
            name=f"syschime-audio:{key}",
        )
        self._tasks[key] = task
        task.add_done_callback(lambda done, alert_key=key: self._cleanup(alert_key, done))

    async def stop(self, key: str) -> None:
        task = self._tasks.pop(key, None)
        if task is None:
            return
        if task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def stop_all(self) -> None:
        await asyncio.gather(*(self.stop(key) for key in list(self._tasks)))

    async def wait_idle(self, key: str) -> None:
        task = self._tasks.get(key)
        if task is None:
            return
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            pass

    def _cleanup(self, key: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(key) is task:
            self._tasks.pop(key, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            LOG.error("audio task for %s failed: %s", key, exc)

    async def _run(self, key: str, path: Path, policy: SoundPolicy) -> None:
        backend = self._get_backend()

        if policy.mode == SoundMode.ONCE:
            await backend.play(path, policy.volume)
            return

        if policy.mode == SoundMode.REPEAT:
            for index in range(policy.repeat_count):
                await backend.play(path, policy.volume)
                if index + 1 < policy.repeat_count and policy.repeat_gap_seconds:
                    await asyncio.sleep(policy.repeat_gap_seconds)
            return

        if policy.mode == SoundMode.LOOP:
            while True:
                await backend.play(path, policy.volume)

        if policy.mode == SoundMode.INTERVAL:
            while True:
                await backend.play(path, policy.volume)
                await asyncio.sleep(policy.interval_seconds)

        raise RuntimeError(f"unsupported sound mode: {policy.mode}")
