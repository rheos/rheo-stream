"""Packaged configuration data for ``rheo_core``.

Holds ``defaults.toml``, the package defaults for the declared settings keys, read
through ``importlib.resources`` so it resolves from the installed wheel and not only
from a checkout. The declarations themselves are in ``rheo_core.settings.schema``.
"""
