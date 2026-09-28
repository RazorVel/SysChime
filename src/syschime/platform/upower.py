from __future__ import annotations

from ..plugins.battery import BatterySnapshot, BatteryState


_STATE_MAP = {
    0: BatteryState.UNKNOWN,
    1: BatteryState.CHARGING,
    2: BatteryState.DISCHARGING,
    3: BatteryState.EMPTY,
    4: BatteryState.FULL,
    5: BatteryState.PENDING_CHARGE,
    6: BatteryState.PENDING_DISCHARGE,
}


class UPowerBatteryProvider:
    SERVICE = "org.freedesktop.UPower"
    PATH = "/org/freedesktop/UPower"
    IFACE = "org.freedesktop.UPower"
    DEVICE_IFACE = "org.freedesktop.UPower.Device"
    PROPS_IFACE = "org.freedesktop.DBus.Properties"

    def __init__(self) -> None:
        self._bus = None
        self._device_path: str | None = None
        self._props = None

    async def connect(self) -> None:
        if self._props is not None:
            return
        from dbus_next import BusType
        from dbus_next.aio import MessageBus

        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        root_intro = await self._bus.introspect(self.SERVICE, self.PATH)
        root_obj = self._bus.get_proxy_object(self.SERVICE, self.PATH, root_intro)
        upower = root_obj.get_interface(self.IFACE)
        device_path = await upower.call_get_display_device()
        self._device_path = str(device_path)

        device_intro = await self._bus.introspect(self.SERVICE, self._device_path)
        device_obj = self._bus.get_proxy_object(self.SERVICE, self._device_path, device_intro)
        self._props = device_obj.get_interface(self.PROPS_IFACE)

    async def snapshot(self) -> BatterySnapshot:
        await self.connect()
        values = await self._props.call_get_all(self.DEVICE_IFACE)
        percentage = float(values["Percentage"].value)
        state = _STATE_MAP.get(int(values["State"].value), BatteryState.UNKNOWN)
        return BatterySnapshot(percentage=percentage, state=state)

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
        self._bus = None
        self._props = None
        self._device_path = None
