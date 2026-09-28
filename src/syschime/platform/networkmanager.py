from __future__ import annotations


class NetworkManagerVpnProvider:
    SERVICE = "org.freedesktop.NetworkManager"
    PATH = "/org/freedesktop/NetworkManager"
    NM_IFACE = "org.freedesktop.NetworkManager"
    ACTIVE_IFACE = "org.freedesktop.NetworkManager.Connection.Active"
    PROPS_IFACE = "org.freedesktop.DBus.Properties"
    ACTIVATED = 2

    def __init__(self) -> None:
        self._bus = None
        self._root_props = None

    async def connect(self) -> None:
        if self._root_props is not None:
            return
        from dbus_next import BusType
        from dbus_next.aio import MessageBus

        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        intro = await self._bus.introspect(self.SERVICE, self.PATH)
        obj = self._bus.get_proxy_object(self.SERVICE, self.PATH, intro)
        self._root_props = obj.get_interface(self.PROPS_IFACE)

    async def active_vpns(self) -> set[str]:
        await self.connect()
        active_variant = await self._root_props.call_get(self.NM_IFACE, "ActiveConnections")
        paths = list(active_variant.value)
        result: set[str] = set()

        for path in paths:
            try:
                intro = await self._bus.introspect(self.SERVICE, path)
                obj = self._bus.get_proxy_object(self.SERVICE, path, intro)
                props = obj.get_interface(self.PROPS_IFACE)
                values = await props.call_get_all(self.ACTIVE_IFACE)
                is_vpn = bool(values.get("Vpn").value) if "Vpn" in values else False
                state = int(values.get("State").value) if "State" in values else 0
                if is_vpn and state == self.ACTIVATED:
                    result.add(str(values["Id"].value))
            except Exception:
                # ActiveConnection objects can disappear while we inspect them.
                continue
        return result

    async def close(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
        self._bus = None
        self._root_props = None
