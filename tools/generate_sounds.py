#!/usr/bin/env python3
from __future__ import annotations

import math
import wave
from pathlib import Path

RATE = 44100
AMP = 0.34
OUT = Path(__file__).resolve().parents[1] / "src" / "syschime" / "assets"


def tone(freq: float, duration: float, amplitude: float = AMP) -> list[float]:
    count = int(RATE * duration)
    fade = min(int(RATE * 0.012), max(1, count // 4))
    samples: list[float] = []
    for i in range(count):
        env = 1.0
        if i < fade:
            env = i / fade
        elif i >= count - fade:
            env = (count - 1 - i) / fade
        samples.append(amplitude * env * math.sin(2 * math.pi * freq * i / RATE))
    return samples


def silence(duration: float) -> list[float]:
    return [0.0] * int(RATE * duration)


def pattern(parts: list[tuple[float | None, float, float | None]]) -> list[float]:
    data: list[float] = []
    for freq, duration, amplitude in parts:
        if freq is None:
            data.extend(silence(duration))
        else:
            data.extend(tone(freq, duration, AMP if amplitude is None else amplitude))
    return data


def write(name: str, samples: list[float]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        frames = bytearray()
        for sample in samples:
            value = max(-1.0, min(1.0, sample))
            integer = int(value * 32767)
            frames.extend(integer.to_bytes(2, byteorder="little", signed=True))
        wav.writeframes(bytes(frames))
    print(path)


def main() -> None:
    write("warning-soft", pattern([
        (660, 0.12, 0.22), (None, 0.07, None), (780, 0.15, 0.20),
    ]))
    write("warning-medium", pattern([
        (740, 0.17, 0.30), (None, 0.10, None), (740, 0.17, 0.30), (None, 0.18, None),
    ]))
    write("warning-urgent", pattern([
        (880, 0.10, 0.34), (None, 0.06, None), (880, 0.10, 0.34),
        (None, 0.06, None), (980, 0.13, 0.34),
    ]))
    write("warning-critical", pattern([
        (980, 0.14, 0.38), (None, 0.05, None), (760, 0.14, 0.38),
        (None, 0.05, None), (980, 0.14, 0.38), (None, 0.16, None),
    ]))
    write("disconnect", pattern([
        (760, 0.14, 0.28), (None, 0.04, None), (570, 0.18, 0.30),
        (None, 0.04, None), (420, 0.22, 0.28),
    ]))
    write("resolved", pattern([
        (520, 0.10, 0.20), (None, 0.04, None), (660, 0.10, 0.20),
        (None, 0.04, None), (820, 0.16, 0.22),
    ]))


if __name__ == "__main__":
    main()
