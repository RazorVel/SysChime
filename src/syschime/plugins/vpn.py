from __future__ import annotations

from typing import Protocol

from ..config import VpnConfig
from ..core.models import AlertAction, RaiseAlert, ResolveAlert


class VpnProvider(Protocol):
    async def active_vpns(self) -> set[str]: ...


class VpnStateMachine:
    def __init__(self, config: VpnConfig) -> None:
        self.config = config
        self._connected: dict[str, bool] = {}
        self._known_dynamic: set[str] = set()
        self._alerted: set[str] = set()

    def evaluate(self, active: set[str]) -> list[AlertAction]:
        actions: list[AlertAction] = []

        if self.config.watch:
            targets = set(self.config.watch)
        else:
            self._known_dynamic.update(active)
            targets = set(self._known_dynamic)

        for name in sorted(targets):
            is_active = name in active
            previous = self._connected.get(name)
            key = f"vpn:{name}:disconnect"

            if previous is None:
                self._connected[name] = is_active
                continue

            if previous and not is_active:
                self._connected[name] = False
                self._alerted.add(name)
                actions.append(
                    RaiseAlert(
                        key=key,
                        title="VPN Disconnected",
                        message=f"VPN '{name}' disconnected.",
                        profile_name=self.config.disconnect_profile,
                        metadata={"connection": name},
                    )
                )
            elif not previous and is_active:
                self._connected[name] = True
                if name in self._alerted:
                    self._alerted.remove(name)
                    actions.append(ResolveAlert(key))

        return actions
