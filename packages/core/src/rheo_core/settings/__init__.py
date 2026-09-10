"""Settings and configuration precedence with the policy floor (A5).

Three sources in ascending precedence: package defaults (the registry in
``schema.py``, mirrored by ``config/defaults.toml``), deployment settings
(``deployment.py``: ``<data_root>/config/deployment.toml`` then ``RHEO__*`` variables),
and workspace/member overrides (rows, through the ``OverrideSource`` protocol C3
implements). ``resolver.py`` combines them and applies the floor on every read;
``write_path.py`` refuses an override that would relax the floor before it is stored.

Importing this package runs the registry/``defaults.toml`` identity check.
"""

from rheo_core.settings.defaults import (
    PACKAGE_DEFAULTS,
    assert_registry_matches,
    load_package_defaults,
)
from rheo_core.settings.deployment import (
    ENV_PREFIX,
    PROFILE_VARIABLE,
    current_profile,
    deployment_layer,
    deployment_toml_path,
    env_variable_names,
)
from rheo_core.settings.resolver import (
    OverrideSource,
    ResolvedSettings,
    apply_floor,
    is_looser,
    resolve,
)
from rheo_core.settings.schema import (
    CORE_ORIGIN,
    PROFILE_KEY,
    PROFILES,
    REGISTRY,
    TEST_HARNESS_ORIGIN,
    Floor,
    FrozenValue,
    KeySpec,
    Scope,
    SettingOriginRefused,
    SettingRedeclared,
    SettingsDeclarationMismatch,
    SettingsError,
    SettingsRegistry,
    SettingTypeMismatch,
    SettingUndeclared,
    SettingValue,
    ValueType,
    decode_text,
    encode_text,
    register,
    spec_for,
)
from rheo_core.settings.write_path import (
    REFUSAL_STATES,
    SettingAccepted,
    SettingRefusal,
    validate_override,
)

__all__ = [
    "CORE_ORIGIN",
    "ENV_PREFIX",
    "PACKAGE_DEFAULTS",
    "PROFILES",
    "PROFILE_KEY",
    "PROFILE_VARIABLE",
    "REFUSAL_STATES",
    "REGISTRY",
    "TEST_HARNESS_ORIGIN",
    "Floor",
    "FrozenValue",
    "KeySpec",
    "OverrideSource",
    "ResolvedSettings",
    "Scope",
    "SettingAccepted",
    "SettingOriginRefused",
    "SettingRedeclared",
    "SettingRefusal",
    "SettingTypeMismatch",
    "SettingUndeclared",
    "SettingValue",
    "SettingsDeclarationMismatch",
    "SettingsError",
    "SettingsRegistry",
    "ValueType",
    "apply_floor",
    "assert_registry_matches",
    "current_profile",
    "decode_text",
    "deployment_layer",
    "deployment_toml_path",
    "encode_text",
    "env_variable_names",
    "is_looser",
    "load_package_defaults",
    "register",
    "resolve",
    "spec_for",
    "validate_override",
]
