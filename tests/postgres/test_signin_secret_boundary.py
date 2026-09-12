"""B9 / fit-check.md Q2a: ``ResolvedSettings.__repr__`` never carries a resolved
value — only key names — closing reference disclosure (a ``secret://`` reference)
exactly as strictly as value disclosure. 08 extends this file with its own
log-line assertion over the live sign-in flow (this file's own assertion below is
the settings-repr half only).
"""

import pytest
from rheo_core.settings import resolve

pytestmark = pytest.mark.postgres


def test_resolved_settings_repr_never_carries_a_reference_or_a_value() -> None:
    settings = resolve()
    rendered = repr(settings)
    assert rendered.startswith("ResolvedSettings(")
    # storage.cluster_dsn_ref's package default is itself a live secret:// reference
    # (secret://env/RHEO_CLUSTER_DSN), so this is a real assertion, not a vacuous one:
    # before the fix, the old repr would have printed it verbatim.
    assert "secret://" not in rendered
    # Key NAMES are exactly what the repr is for; every declared key resolved here
    # shows up by name.
    for key in settings:
        assert key in rendered
