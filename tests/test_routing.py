"""The routing configuration and the URL builders, driven by the shared fixture.

Seam: ``rheo_core.routing.url_for`` — ``url_for``, ``identity_path``,
``application_hosts`` — exercised from ``tests/fixtures/routing/*.json``. Those three
files are the contract, not a convenience: the web tier's vitest suite reads the same
bytes, so the Python and TypeScript implementations are proven **equal** rather than
merely alike (B10). A fixture entry is therefore the authority — if an expected string
and this implementation disagree, the implementation is wrong.

Two things the fixture alone cannot pin are asserted against literals here as well, so
that editing a fixture entry cannot quietly retire them: the documented OAuth callback
URL in both modes, and the single-slash join for a surface whose path is the root.

No Postgres. The routing configuration is deployment settings and pure functions.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from rheo_core.routing import (
    API,
    DOCS,
    IDENTITY,
    INTEGRATION,
    MCP,
    SHELL,
    RoutingConfig,
    RoutingMode,
    application_hosts,
    identity_path,
    is_application_host,
    url_for,
)
from rheo_core.settings import resolve

FIXTURES = Path(__file__).parent / "fixtures" / "routing"
MODES = ("path", "subdomain")


def read_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_config(mode: str) -> RoutingConfig:
    return RoutingConfig.model_validate(read_fixture(f"{mode}-mode.json"))


CONFIGS: dict[str, RoutingConfig] = {mode: load_config(mode) for mode in MODES}
EXPECTATIONS: list[dict[str, Any]] = read_fixture("expected-urls.json")

URL_CASES = [case for case in EXPECTATIONS if "surface" in case]
IDENTITY_PATH_CASES = [case for case in EXPECTATIONS if case.get("identity_path")]
HOST_CASES = [case for case in EXPECTATIONS if "application_hosts" in case]


def url_id(case: dict[str, Any]) -> str:
    return f"{case['mode']}-{case['surface']}-{case['path']}"


def path_id(case: dict[str, Any]) -> str:
    return f"{case['mode']}-identity_path-{case['path']}"


# --- the fixture is the contract ----------------------------------------------------


def test_the_fixture_covers_both_modes_and_every_non_external_surface() -> None:
    """A vacuous fixture would make every assertion below pass by covering nothing."""
    for mode in MODES:
        surfaces = {case["surface"] for case in URL_CASES if case["mode"] == mode}
        assert surfaces == {SHELL, IDENTITY, API, MCP}
        assert [case for case in IDENTITY_PATH_CASES if case["mode"] == mode]
        assert len([case for case in HOST_CASES if case["mode"] == mode]) == 1


@pytest.mark.parametrize("case", URL_CASES, ids=url_id)
def test_url_for_matches_the_fixture(case: dict[str, Any]) -> None:
    config = CONFIGS[case["mode"]]
    assert url_for(config, case["surface"], case["path"]) == case["expected"]


@pytest.mark.parametrize("case", IDENTITY_PATH_CASES, ids=path_id)
def test_identity_path_matches_the_fixture(case: dict[str, Any]) -> None:
    config = CONFIGS[case["mode"]]
    assert identity_path(config, case["path"]) == case["expected"]


@pytest.mark.parametrize("case", HOST_CASES, ids=lambda case: str(case["mode"]))
def test_application_hosts_match_the_fixture(case: dict[str, Any]) -> None:
    config = CONFIGS[case["mode"]]
    expected = frozenset(case["application_hosts"])
    assert application_hosts(config) == expected
    for host in expected:
        assert is_application_host(config, host)
    assert not is_application_host(config, "elsewhere.example.test")
    assert not is_application_host(config, "docs.example.test")


@pytest.mark.parametrize("mode", MODES)
def test_the_fixture_round_trips_through_the_model(mode: str) -> None:
    """The serialised form 08 serves and 10 reads carries every fixture field."""
    raw = read_fixture(f"{mode}-mode.json")
    dumped = CONFIGS[mode].model_dump(mode="json")
    assert (dumped["mode"], dumped["scheme"], dumped["base_host"]) == (
        raw["mode"],
        raw["scheme"],
        raw["base_host"],
    )
    for name, surface in raw["surfaces"].items():
        if name == "modules":
            assert dumped["surfaces"]["modules"] == surface
            continue
        for field, value in surface.items():
            assert dumped["surfaces"][name][field] == value


# --- the two rules the fixture must not be able to retire ---------------------------


def test_the_identity_callback_is_the_documented_url() -> None:
    assert (
        url_for(CONFIGS["subdomain"], IDENTITY, "/callback")
        == "https://auth.example.test/auth/callback"
    )
    assert (
        url_for(CONFIGS["path"], IDENTITY, "/callback")
        == "https://example.test/auth/callback"
    )


def test_a_root_surface_path_does_not_double_the_slash() -> None:
    """``shell``'s path is ``/``; naive concatenation yields ``example.test//login``."""
    assert url_for(CONFIGS["path"], SHELL, "/login") == "https://example.test/login"
    assert (
        url_for(CONFIGS["subdomain"], SHELL, "/login")
        == "https://circuit.example.test/login"
    )
    assert url_for(CONFIGS["path"], SHELL, "/") == "https://example.test/"


def test_the_two_modes_are_not_vacuously_identical() -> None:
    """Every surface case covered in both modes must produce two different URLs."""
    by_case: dict[tuple[str, str], dict[str, str]] = {}
    for case in URL_CASES:
        by_case.setdefault((case["surface"], case["path"]), {})[case["mode"]] = case[
            "expected"
        ]
    both = {key: values for key, values in by_case.items() if len(values) == len(MODES)}
    assert (IDENTITY, "/callback") in both
    assert (SHELL, "/login") in both
    for key, values in both.items():
        assert len(set(values.values())) == len(MODES), key


# --- refusals ------------------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
def test_an_unknown_surface_refuses(mode: str) -> None:
    with pytest.raises(ValueError, match="nonesuch"):
        url_for(CONFIGS[mode], "nonesuch", "/")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("surface", [DOCS, INTEGRATION])
def test_external_and_reserved_surfaces_refuse(surface: str, mode: str) -> None:
    """This application never builds a link to ``docs.`` or ``tuttle.``."""
    with pytest.raises(ValueError, match=surface):
        url_for(CONFIGS[mode], surface, "/")


def test_modules_is_empty_in_this_release() -> None:
    for mode in MODES:
        assert dict(CONFIGS[mode].surfaces.modules) == {}


# --- the settings path ---------------------------------------------------------------


def test_from_settings_builds_the_package_default_topology() -> None:
    config = RoutingConfig.from_settings(resolve())
    assert config.mode is RoutingMode.PATH
    assert (config.scheme, config.base_host) == ("https", "localhost")
    surfaces = config.surfaces
    assert (surfaces.shell.host, surfaces.shell.path) == ("circuit", "/")
    assert (surfaces.identity.host, surfaces.identity.path) == ("auth", "/auth")
    assert (surfaces.api.host, surfaces.api.path) == ("api", "/api")
    assert (surfaces.mcp.host, surfaces.mcp.path) == ("mcp", "/mcp")
    assert (surfaces.docs.host, surfaces.docs.external) == ("docs", True)
    assert surfaces.integration.external and surfaces.integration.reserved
    assert dict(surfaces.modules) == {}
    assert application_hosts(config) == frozenset({"localhost"})
    assert url_for(config, IDENTITY, "/callback") == "https://localhost/auth/callback"


def test_identity_is_the_only_fixed_path_surface() -> None:
    """``fixed_path`` is an invariant in code, not a settings key an operator can
    move: every application host serves ``/auth/*`` in both modes."""
    surfaces = RoutingConfig.from_settings(resolve()).surfaces
    fixed = {name for name, surface in surfaces.named().items() if surface.fixed_path}
    assert fixed == {IDENTITY}
