from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from ..plugins.thermal import ThermalReading


def classify_hwmon(name: str) -> str | None:
    lowered = name.lower()
    if any(token in lowered for token in ("coretemp", "k10temp", "zenpower", "cpu_thermal")):
        return "cpu"
    if any(token in lowered for token in ("nvidia", "amdgpu", "gpu")):
        return "gpu"
    if "nvme" in lowered:
        return "nvme"
    return None


def parse_nvidia_smi(output: str) -> list[ThermalReading]:
    readings: list[ThermalReading] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            index_text, temp_text = (part.strip() for part in line.split(",", 1))
            index = int(index_text)
            temperature = float(temp_text)
        except (ValueError, TypeError):
            continue
        readings.append(
            ThermalReading(
                category="gpu",
                sensor_id=f"nvidia-smi:gpu{index}",
                label=f"NVIDIA GPU {index}",
                temperature_c=temperature,
            )
        )
    return readings


class HwmonThermalProvider:
    def __init__(self, root: Path = Path("/sys/class/hwmon")) -> None:
        self.root = root

    async def readings(self) -> list[ThermalReading]:
        readings = self.readings_sync()
        if any(reading.category == "gpu" for reading in readings):
            return readings

        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return readings
        try:
            process = await asyncio.create_subprocess_exec(
                nvidia_smi,
                "--query-gpu=index,temperature.gpu",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2.0)
            if process.returncode == 0:
                readings.extend(parse_nvidia_smi(stdout.decode(errors="replace")))
        except (OSError, asyncio.TimeoutError):
            if 'process' in locals() and process.returncode is None:
                process.kill()
                await process.wait()
        return readings

    def readings_sync(self) -> list[ThermalReading]:
        readings: list[ThermalReading] = []
        if not self.root.exists():
            return readings

        for hwmon in sorted(self.root.glob("hwmon*")):
            try:
                name = (hwmon / "name").read_text().strip()
            except OSError:
                continue
            category = classify_hwmon(name)
            if category is None:
                continue

            for input_path in sorted(hwmon.glob("temp*_input")):
                stem = input_path.name.removesuffix("_input")
                label_path = hwmon / f"{stem}_label"
                try:
                    raw = input_path.read_text().strip()
                    temperature_c = float(raw) / 1000.0
                    label = label_path.read_text().strip() if label_path.exists() else stem
                except (OSError, ValueError):
                    continue
                readings.append(
                    ThermalReading(
                        category=category,
                        sensor_id=f"{name}:{stem}",
                        label=f"{name}/{label}",
                        temperature_c=temperature_c,
                    )
                )
        return readings
