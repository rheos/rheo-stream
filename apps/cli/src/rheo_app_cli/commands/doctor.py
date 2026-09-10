"""``rheo doctor``: data-root validity, cluster reachability, the control-plane head,
per-workspace state, and the ``CREATE EXTENSION`` privilege report for ``vector``
and ``pg_trgm``.

The privilege report is kept in this run per the run spec (Technical Risks item 11):
nothing in 0b installs an extension, but ``storage.template_database`` and this
report ship now so phase 2 meets a documented remedy rather than a surprise. It
reads the catalogs only and never runs ``CREATE EXTENSION``: an extension is
creatable by a superuser, or by a role with ``CREATE`` on the database when the
extension is marked trusted (Postgres 13+).

Each check is one line on stdout (``ok``, ``warn`` or ``FAIL``); the exit code is 1
when any check failed. Every step runs even when an earlier one failed, so one
report shows everything that is wrong.
"""

import argparse
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from rheo_core.migrations.orchestrator import (
    CONTROL_CHAIN,
    known_revisions,
    recorded_revisions,
)
from rheo_core.secrets import SecretRefusal, check_env_references
from rheo_core.settings import PROFILE_KEY, SettingsError, resolve
from rheo_core.storage.backend import StorageRefusal
from rheo_core.storage.control_plane import list_workspaces
from rheo_core.storage.control_tables import WorkspaceState
from rheo_core.storage.data_root import DataRootRefusal, resolve_data_root
from rheo_core.storage.postgres import PostgresBackend, get_backend
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from rheo_app_cli.context import data_root

EXTENSIONS: Final = ("vector", "pg_trgm")


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    level: str  # "ok" | "warn" | "FAIL"
    detail: str

    def line(self) -> str:
        return f"{self.level:<4} {self.name}: {self.detail}"


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    parser = subparsers.add_parser("doctor", help="diagnose the deployment")
    parser.set_defaults(handler=doctor)


def _check_data_root() -> Check:
    try:
        resolution = resolve_data_root()
        root = data_root()
    except DataRootRefusal as refusal:
        return Check("data root", "FAIL", f"{refusal.state}: {refusal.detail}")
    return Check("data root", "ok", f"{root} ({resolution.source.value})")


def _check_settings() -> Check:
    try:
        settings = resolve()
        checked = check_env_references(settings)
    except (SettingsError, SecretRefusal) as refusal:
        return Check("settings", "FAIL", f"{refusal.state}: {refusal.detail}")
    return Check(
        "settings",
        "ok",
        f"profile {settings.get_str(PROFILE_KEY)}; env references present: "
        f"{', '.join(checked) or 'none'}",
    )


def _check_cluster() -> tuple[Check, PostgresBackend | None]:
    try:
        backend = get_backend()
        with backend.maintenance_connection() as connection:
            version = connection.execute(text("SHOW server_version")).scalar_one()
    except (SettingsError, SecretRefusal, ValueError) as refusal:
        return Check("cluster", "FAIL", str(refusal)), None
    except SQLAlchemyError as exc:
        return Check("cluster", "FAIL", f"unreachable: {type(exc).__name__}"), None
    return Check("cluster", "ok", f"reachable; server {version}"), backend


def _check_control_plane(backend: PostgresBackend) -> Check:
    name = f"control plane {backend.control_database}"
    if not backend.database_exists(backend.control_database):
        return Check(name, "FAIL", "database missing; run `rheo migrate`")
    with backend.control_engine.connect() as connection:
        recorded = recorded_revisions(connection, CONTROL_CHAIN)
    ahead = recorded - known_revisions(CONTROL_CHAIN)
    if ahead:
        return Check(name, "FAIL", f"schema_ahead: records {sorted(ahead)}")
    if not recorded:
        return Check(name, "warn", "no revision recorded; run `rheo migrate`")
    return Check(name, "ok", f"at revision {', '.join(sorted(recorded))}")


def _check_workspaces(backend: PostgresBackend) -> Iterator[Check]:
    try:
        with backend.control_engine.connect() as connection:
            rows = list_workspaces(connection)
    except SQLAlchemyError as exc:
        yield Check("workspaces", "FAIL", f"cannot list: {type(exc).__name__}")
        return
    if not rows:
        yield Check("workspaces", "ok", "none")
        return
    for row in rows:
        level = "ok" if row.state is WorkspaceState.ACTIVE else "warn"
        detail = row.state.value
        if row.state_detail and row.state is not WorkspaceState.ACTIVE:
            detail += f" ({row.state_detail})"
        yield Check(f"workspace {row.id} ({row.slug})", level, detail)


def _check_extensions(backend: PostgresBackend) -> Iterator[Check]:
    template = backend.template_database
    try:
        with backend.maintenance_connection() as connection:
            superuser = bool(
                connection.execute(
                    text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
                ).scalar_one()
            )
            may_create_in_template = bool(
                connection.execute(
                    text("SELECT has_database_privilege(:db, 'CREATE')"),
                    {"db": template},
                ).scalar_one()
            )
            available = {
                str(row.name): (row.default_version, row.installed_version)
                for row in connection.execute(
                    text(
                        "SELECT name, default_version, installed_version "
                        "FROM pg_available_extensions WHERE name = ANY(:names)"
                    ),
                    {"names": list(EXTENSIONS)},
                )
            }
            trusted = {
                str(row.name): bool(row.trusted)
                for row in connection.execute(
                    text(
                        "SELECT v.name, v.trusted "
                        "FROM pg_available_extension_versions v "
                        "JOIN pg_available_extensions e ON e.name = v.name "
                        "AND e.default_version = v.version "
                        "WHERE v.name = ANY(:names)"
                    ),
                    {"names": list(EXTENSIONS)},
                )
            }
    except SQLAlchemyError as exc:
        yield Check("extensions", "FAIL", f"cannot read catalogs: {type(exc).__name__}")
        return
    for name in EXTENSIONS:
        if name not in available:
            yield Check(
                f"extension {name}",
                "warn",
                "not available on this cluster (phase 2 needs it installed)",
            )
            continue
        default_version, installed = available[name]
        is_trusted = trusted.get(name, False)
        may_create = superuser or (is_trusted and may_create_in_template)
        how = (
            "superuser"
            if superuser
            else ("trusted + CREATE on the database" if may_create else "no")
        )
        yield Check(
            f"extension {name}",
            "ok" if may_create else "warn",
            f"available {default_version}; installed in maintenance db: "
            f"{installed or 'no'}; trusted: {'yes' if is_trusted else 'no'}; "
            f"role may CREATE EXTENSION in {template}: {how}",
        )


def doctor(args: argparse.Namespace) -> int:
    checks: list[Check] = [_check_data_root(), _check_settings()]
    cluster, backend = _check_cluster()
    checks.append(cluster)
    if backend is not None:
        try:
            checks.append(_check_control_plane(backend))
        except (SQLAlchemyError, StorageRefusal) as exc:
            checks.append(
                Check("control plane", "FAIL", f"{type(exc).__name__}: {exc}")
            )
        checks.extend(_check_workspaces(backend))
        checks.extend(_check_extensions(backend))
    for check in checks:
        print(check.line())
    return 1 if any(check.level == "FAIL" for check in checks) else 0
