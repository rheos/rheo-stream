"""Package defaults from ``rheo_core/config/defaults.toml``, checked against the
registry.

The TOML holds only values, nested by the dotted key segments. At import time this
module loads it through ``importlib.resources`` (so the installed wheel works, not just
the checkout) and asserts that the registry's ``core`` key set and the TOML's key set
are identical, and that the two agree on every value. It raises naming the difference.

The check holds PER MERGE SHA: every later chunk that adds a key adds it to both
``schema.py`` and ``defaults.toml``, and no run declares a key that only a later run
reads. Harness keys (``origin = "test_harness"``) are registry-only by design and are
excluded from the comparison.
"""

import tomllib
from collections.abc import Mapping
from importlib import resources
from types import MappingProxyType
from typing import Final

from rheo_core.settings.schema import (
    CORE_ORIGIN,
    REGISTRY,
    FrozenValue,
    SettingsDeclarationMismatch,
    SettingsRegistry,
    check_value,
)

DEFAULTS_RESOURCE: Final = "defaults.toml"


def flatten_table(table: Mapping[str, object], prefix: str = "") -> dict[str, object]:
    """Flatten nested TOML tables into dotted keys (``[a.b] c = 1`` → ``a.b.c``)."""
    flat: dict[str, object] = {}
    for name, value in table.items():
        key = f"{prefix}{name}"
        if isinstance(value, dict):
            flat.update(flatten_table(value, f"{key}."))
        else:
            flat[key] = value
    return flat


def load_package_defaults() -> dict[str, object]:
    """Read and flatten ``defaults.toml`` from the installed package."""
    text = (
        resources.files("rheo_core.config")
        .joinpath(DEFAULTS_RESOURCE)
        .read_text(encoding="utf-8")
    )
    return flatten_table(tomllib.loads(text))


def assert_registry_matches(
    defaults: Mapping[str, object], registry: SettingsRegistry = REGISTRY
) -> Mapping[str, FrozenValue]:
    """Raise unless the ``core`` registry keys and ``defaults`` agree on keys and
    values.

    Returns the typed, frozen defaults on success.
    """
    declared = registry.keys(origin=CORE_ORIGIN)
    provided = frozenset(defaults)
    undeclared = sorted(provided - declared)
    unlisted = sorted(declared - provided)
    if undeclared or unlisted:
        raise SettingsDeclarationMismatch(
            "settings registry and defaults.toml disagree on the key set: "
            f"in defaults.toml but not declared: {undeclared}; "
            f"declared but absent from defaults.toml: {unlisted}"
        )
    typed: dict[str, FrozenValue] = {}
    drift: list[str] = []
    for key in sorted(declared):
        spec = registry.get(key)
        value = check_value(spec, defaults[key], source=DEFAULTS_RESOURCE)
        if value != spec.default:
            drift.append(f"{key}: registry {spec.default!r} vs defaults.toml {value!r}")
        typed[key] = value
    if drift:
        raise SettingsDeclarationMismatch(
            "settings registry and defaults.toml disagree on values: "
            + "; ".join(drift)
        )
    return MappingProxyType(typed)


PACKAGE_DEFAULTS: Final[Mapping[str, FrozenValue]] = assert_registry_matches(
    load_package_defaults()
)
