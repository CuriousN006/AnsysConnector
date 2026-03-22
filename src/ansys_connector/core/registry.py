from __future__ import annotations

from dataclasses import dataclass

from ansys_connector.core.environment import EnvironmentInfo
from ansys_connector.products import FluentAdapter, MechanicalAdapter, WorkbenchAdapter
from ansys_connector.products.base import ActionProfile, Adapter, AdapterStatus


@dataclass
class AdapterRegistry:
    """Adapter registry."""

    adapters: dict[str, Adapter]

    def get(self, name: str) -> Adapter:
        try:
            return self.adapters[name]
        except KeyError as exc:
            raise KeyError(f"Unknown adapter: {name}") from exc

    def statuses(self, env: EnvironmentInfo) -> list[AdapterStatus]:
        return [adapter.inspect(env) for adapter in self.adapters.values()]

    def describe_actions(self, name: str, profile: ActionProfile | None = None) -> list[dict]:
        return self.get(name).describe_actions(profile)


def build_registry() -> AdapterRegistry:
    return AdapterRegistry(
        adapters={
            "fluent": FluentAdapter(),
            "workbench": WorkbenchAdapter(),
            "mechanical": MechanicalAdapter(),
        }
    )
