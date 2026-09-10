"""The deployment layer: ``<data_root>/config/deployment.toml``, then the environment.

Later wins. The TOML is private to the operator and absent is fine (an empty layer).
Environment mapping: for key ``k`` the variable is ``RHEO__`` + ``k`` with every ``.``
replaced by ``__`` (``identity.token_max_days.cli`` becomes
``RHEO__identity__token_max_days__cli``); that exact form is tried first, then its
fully-uppercased variant. Values are coerced
by the key's declared type. ``profile`` additionally reads the plain ``RHEO_PROFILE``
variable, which compose, CI and ``tests/conftest.py`` set, and ``RHEO_PROFILE`` wins
over ``RHEO__profile`` when both are present.

Undeclared keys are refused at both sources: a TOML key with no declaration raises
naming it, and any ``RHEO__*`` variable that maps to no declared key raises naming the
variable. The ``RHEO__`` prefix is reserved for settings, so a stray one is an
operator error and startup fails loudly rather than silently ignoring it.
"""

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from rheo_core.settings.defaults import flatten_table
from rheo_core.settings.schema import (
    PROFILE_KEY,
    REGISTRY,
    FrozenValue,
    SettingUndeclared,
    check_value,
    decode_text,
)

ENV_PREFIX: Final = "RHEO__"
PROFILE_VARIABLE: Final = "RHEO_PROFILE"
DEPLOYMENT_TOML: Final = Path("config") / "deployment.toml"


def env_variable_names(key: str) -> tuple[str, str]:
    """The two variable names read for ``key``: the exact form, then uppercased."""
    exact = ENV_PREFIX + key.replace(".", "__")
    return exact, exact.upper()


def deployment_toml_path(data_root: Path) -> Path:
    return data_root / DEPLOYMENT_TOML


def load_deployment_toml(path: Path) -> dict[str, FrozenValue]:
    """The typed values in ``path``; ``{}`` when the file is absent.

    Values are TOML-native (an ``int`` key needs a TOML integer, a ``list[str]`` key a
    TOML array of strings); a mismatch raises ``setting_type`` naming the key, and an
    undeclared key raises ``setting_undeclared`` naming it.
    """
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        table = tomllib.load(handle)
    layer: dict[str, FrozenValue] = {}
    for key, value in flatten_table(table).items():
        spec = REGISTRY.lookup(key)
        if spec is None:
            raise SettingUndeclared(
                f"{key}: {path} names a key no settings schema declares", key=key
            )
        layer[key] = check_value(spec, value, source=str(path))
    return layer


def load_environment(environ: Mapping[str, str]) -> dict[str, FrozenValue]:
    """The typed values set through ``RHEO__*`` variables and ``RHEO_PROFILE``."""
    layer: dict[str, FrozenValue] = {}
    consumed: set[str] = set()
    for spec in REGISTRY.specs():
        for name in env_variable_names(spec.key):
            if name in environ:
                layer[spec.key] = decode_text(spec, environ[name], source=name)
                consumed.add(name)
                break
        # The variant not chosen may still be present; it is a declared key's
        # variable either way, so it is not a stray.
        consumed.update(n for n in env_variable_names(spec.key) if n in environ)
    if PROFILE_VARIABLE in environ:
        layer[PROFILE_KEY] = decode_text(
            REGISTRY.get(PROFILE_KEY),
            environ[PROFILE_VARIABLE],
            source=PROFILE_VARIABLE,
        )
    strays = sorted(
        name for name in environ if name.startswith(ENV_PREFIX) and name not in consumed
    )
    if strays:
        first = strays[0]
        derived = first[len(ENV_PREFIX) :].replace("__", ".").lower()
        raise SettingUndeclared(
            f"{derived}: environment variable {first} names a key no settings "
            f"schema declares (stray RHEO__ variables: {strays})",
            key=derived,
        )
    return layer


def _data_root_for(environ: Mapping[str, str]) -> Path:
    # rheo_core.storage is populated by C3 with modules that import this package,
    # so the data-root resolver is imported at call time to keep the import graph
    # acyclic. Resolution reads the environment only; it creates nothing.
    from rheo_core.storage.data_root import resolve_data_root

    return resolve_data_root(environ).path


def deployment_layer(
    *, environ: Mapping[str, str] | None = None
) -> dict[str, FrozenValue]:
    """``deployment.toml`` under the resolved data root, then the environment."""
    env = os.environ if environ is None else environ
    layer = load_deployment_toml(deployment_toml_path(_data_root_for(env)))
    layer.update(load_environment(env))
    return layer


def current_profile(*, environ: Mapping[str, str] | None = None) -> str:
    """The deployment-resolved ``profile`` alone, for the harness registration gate.

    ``RHEO_PROFILE``, then ``RHEO__profile`` / ``RHEO__PROFILE``, then the TOML, then
    the package default. Reads only; creates nothing.
    """
    env = os.environ if environ is None else environ
    spec = REGISTRY.get(PROFILE_KEY)
    if PROFILE_VARIABLE in env:
        return str(decode_text(spec, env[PROFILE_VARIABLE], source=PROFILE_VARIABLE))
    for name in env_variable_names(PROFILE_KEY):
        if name in env:
            return str(decode_text(spec, env[name], source=name))
    from_toml = load_deployment_toml(deployment_toml_path(_data_root_for(env)))
    return str(from_toml.get(PROFILE_KEY, spec.default))
