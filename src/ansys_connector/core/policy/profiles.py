from __future__ import annotations

from typing import cast

from ansys_connector.products.base import ActionProfile


DEFAULT_PROFILE: ActionProfile = "safe"


def normalize_profile(profile: str | None = None) -> ActionProfile:
    value = str(profile or DEFAULT_PROFILE).strip().lower()
    if value not in {"safe", "expert"}:
        raise ValueError(f"Unsupported profile: {profile}")
    return cast(ActionProfile, value)
