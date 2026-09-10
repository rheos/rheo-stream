"""The secret store (B9's store/scope/value clauses).

Seams: ``SecretStore.resolve()`` scope enforcement (a foreign scope is
``secret_scope_denied``, no scope is a type error, missing is ``secret_missing`` naming
the variable or path and never a value), ``SecretRef`` parsing, ``FileBackend.read``'s
own id validation, and ``SecretValue``'s redaction and non-serialisability through
every route (``str``, ``repr``, ``format``, ``json.dumps``, the encoder hook, pydantic,
pickle, copy).

Every secret here is a fixed literal, so no assertion samples randomness.
"""

import copy
import dataclasses
import json
import pickle
from pathlib import Path

import pytest
from harness import isolate_rheo_environment
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic_core import PydanticSerializationError
from rheo_core.secrets import (
    REDACTED,
    FileBackend,
    SecretBackend,
    SecretRef,
    SecretRefusal,
    SecretScope,
    SecretStore,
    SecretValue,
    SecretValueNotSerialisable,
    check_env_references,
    refuse_secret_values,
)
from rheo_core.settings import resolve

SECRET = b"hunter2-correct-horse-battery"
SECRET_TEXT = SECRET.decode()
DSN_VALUE = "postgresql://rheo:dsn-value-do-not-leak@db/postgres"
CLUSTER_REF = "secret://env/RHEO_CLUSTER_DSN"


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def store(data_root: Path) -> SecretStore:
    return SecretStore(data_root, environ={"RHEO_CLUSTER_DSN": DSN_VALUE})


@pytest.fixture
def storage_scope() -> SecretScope:
    return SecretStore.scope_for("storage", "secret://file/cluster/", CLUSTER_REF)


def write_secret(data_root: Path, ref_id: str, data: bytes, mode: int = 0o600) -> Path:
    path = data_root / "secrets" / ref_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(mode)
    return path


# --- SecretRef -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "backend", "ident"),
    [
        (
            "secret://file/cluster/primary-dsn",
            SecretBackend.FILE,
            "cluster/primary-dsn",
        ),
        (
            "secret://file/ws/018f6c2e-0000-7000-8000-000000000001/connection/018f/signing",
            SecretBackend.FILE,
            "ws/018f6c2e-0000-7000-8000-000000000001/connection/018f/signing",
        ),
        (
            "secret://env/GITHUB_OAUTH_CLIENT_SECRET",
            SecretBackend.ENV,
            "GITHUB_OAUTH_CLIENT_SECRET",
        ),
        ("secret://env/_lower_ok", SecretBackend.ENV, "_lower_ok"),
    ],
)
def test_secret_ref_parses_and_round_trips(
    text: str, backend: SecretBackend, ident: str
) -> None:
    ref = SecretRef.parse(text)
    assert (ref.backend, ref.id) == (backend, ident)
    assert str(ref) == text


@pytest.mark.parametrize(
    "text",
    [
        "",
        "secret:/file/x",
        "secret://vault/x",
        "secret://file",
        "secret://file/",
        "secret://env/",
        "secret://file/../etc/passwd",
        "secret://file/Upper",
        "secret://file/under_score",
        "secret://file//double",
        "secret://file/trailing-",
        "secret://env/9starts-with-digit",
        "secret://env/has-dash",
        "secret://env/a/b",
        DSN_VALUE,
    ],
)
def test_malformed_secret_ref_is_refused_without_echoing_it(text: str) -> None:
    with pytest.raises(SecretRefusal) as excinfo:
        SecretRef.parse(text)
    assert excinfo.value.state == "secret_ref_malformed"
    assert "dsn-value" not in str(excinfo.value)
    assert "vault" not in str(excinfo.value)


def test_secret_ref_rejects_a_non_string() -> None:
    with pytest.raises(SecretRefusal) as excinfo:
        SecretRef.parse(None)
    assert excinfo.value.state == "secret_ref_malformed"


# --- SecretValue: redaction and non-serialisability -----------------------------------


def test_str_and_repr_are_exactly_the_redaction() -> None:
    value = SecretValue(SECRET)
    assert str(value) == REDACTED == "SecretValue(<redacted>)"
    assert repr(value) == REDACTED
    assert f"{value}" == REDACTED
    assert f"{value!r}" == REDACTED
    assert format(value, ">40") == REDACTED
    # The %-format route is the one ``logging`` renders records through.
    assert "%s / %r" % (value, value) == f"{REDACTED} / {REDACTED}"  # noqa: UP031
    for rendering in (str(value), repr(value), format(value, "x")):
        assert SECRET_TEXT not in rendering
        assert "secret://" not in rendering


def test_bytes_are_reachable_only_through_expose() -> None:
    value = SecretValue(SECRET)
    assert value.expose() == SECRET
    assert not hasattr(value, "__dict__")
    with pytest.raises(TypeError):
        vars(value)
    with pytest.raises(TypeError):
        bytes(value)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        SecretValue("not bytes")  # type: ignore[arg-type]


def test_json_dumps_refuses_a_secret_value() -> None:
    value = SecretValue(SECRET)
    with pytest.raises(TypeError) as plain:
        json.dumps({"secret": value})
    assert SECRET_TEXT not in str(plain.value)
    with pytest.raises(SecretValueNotSerialisable) as hooked:
        json.dumps({"secret": value}, default=refuse_secret_values)
    assert SECRET_TEXT not in str(hooked.value)
    # The hook still refuses everything else the standard way.
    with pytest.raises(TypeError):
        json.dumps({"other": object()}, default=refuse_secret_values)


class Holder(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    secret: SecretValue


def test_pydantic_serialisation_of_a_model_holding_one_raises() -> None:
    holder = Holder(name="cluster", secret=SecretValue(SECRET))
    assert holder.secret.expose() == SECRET
    for dump in (holder.model_dump, holder.model_dump_json):
        with pytest.raises(PydanticSerializationError) as excinfo:
            dump()
        message = str(excinfo.value)
        assert "SecretValueNotSerialisable" in message
        assert SECRET_TEXT not in message
    with pytest.raises(PydanticSerializationError):
        holder.model_dump(mode="json")
    with pytest.raises(ValidationError):
        Holder(name="x", secret=SECRET)  # type: ignore[arg-type]


def test_pickle_and_copy_refuse() -> None:
    value = SecretValue(SECRET)
    with pytest.raises(SecretValueNotSerialisable):
        pickle.dumps(value)
    with pytest.raises(SecretValueNotSerialisable):
        copy.copy(value)
    with pytest.raises(SecretValueNotSerialisable):
        copy.deepcopy({"secret": value})


def test_equality_is_constant_time_and_type_strict() -> None:
    assert SecretValue(SECRET) == SecretValue(SECRET)
    assert SecretValue(SECRET) != SecretValue(b"other")
    assert SecretValue(SECRET) != SECRET
    assert SecretValue(SECRET) != SECRET_TEXT
    assert not (SECRET == SecretValue(SECRET))


def test_secret_value_is_unhashable_and_final() -> None:
    value = SecretValue(SECRET)
    with pytest.raises(TypeError):
        hash(value)
    with pytest.raises(TypeError):
        dict.fromkeys([value])
    with pytest.raises(TypeError):
        type("Leaky", (SecretValue,), {"__repr__": lambda self: "x"})


# --- SecretScope: accidental construction refused ------------------------------------


def test_secret_scope_cannot_be_constructed_outside_the_store() -> None:
    # The AST scan forbids the literal call ``SecretScope(`` outside rheo_core/secrets/;
    # this indirection invokes the constructor without writing that call.
    constructor = SecretScope
    with pytest.raises(TypeError, match="scope_for"):
        constructor("storage", ("secret://env/RHEO_CLUSTER_DSN",))
    with pytest.raises(TypeError, match="scope_for"):
        constructor("storage", ("secret://env/RHEO_CLUSTER_DSN",), _token=object())


def test_secret_scope_cannot_be_widened_by_replace(storage_scope: SecretScope) -> None:
    with pytest.raises(TypeError, match="scope_for"):
        dataclasses.replace(storage_scope, prefixes=("secret://file/",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        storage_scope.prefixes = ("secret://file/",)  # type: ignore[misc]


def test_secret_scope_cannot_be_subclassed_pickled_or_copied(
    storage_scope: SecretScope,
) -> None:
    with pytest.raises(TypeError, match="subclass"):
        type("Wider", (SecretScope,), {})
    with pytest.raises(TypeError, match="travel"):
        pickle.dumps(storage_scope)
    with pytest.raises(TypeError, match="travel"):
        copy.copy(storage_scope)
    with pytest.raises(TypeError, match="travel"):
        copy.deepcopy({"scope": storage_scope})


def test_scope_for_validates_its_prefixes() -> None:
    with pytest.raises(ValueError, match="no reference prefix"):
        SecretStore.scope_for("storage")
    with pytest.raises(ValueError, match="prefix"):
        SecretStore.scope_for("storage", "cluster/")
    with pytest.raises(ValueError, match="prefix"):
        SecretStore.scope_for("storage", "secret://vault/x")
    with pytest.raises(ValueError, match="component"):
        SecretStore.scope_for("", "secret://file/cluster/")


@pytest.mark.parametrize(
    ("ref", "permitted"),
    [
        ("secret://file/cluster/primary-dsn", True),
        ("secret://file/cluster/a/b", True),
        ("secret://file/clusterfoo/x", False),
        ("secret://file/identity/github/client-secret", False),
        (CLUSTER_REF, True),
        ("secret://env/RHEO_CLUSTER_DSN_ADMIN", False),
        ("secret://env/RHEO_INTERNAL_SECRET", False),
    ],
)
def test_scope_matching_is_segment_aligned(
    storage_scope: SecretScope, ref: str, permitted: bool
) -> None:
    assert storage_scope.permits(SecretRef.parse(ref)) is permitted


def test_prefix_without_trailing_slash_covers_the_subtree_only() -> None:
    scope = SecretStore.scope_for("probe", "secret://file/cluster")
    assert scope.permits(SecretRef.parse("secret://file/cluster/primary-dsn"))
    assert not scope.permits(SecretRef.parse("secret://file/clusterfoo/x"))


# --- SecretStore.resolve --------------------------------------------------------------


def test_resolve_env_reference_within_scope(
    store: SecretStore, storage_scope: SecretScope
) -> None:
    value = store.resolve(SecretRef.parse(CLUSTER_REF), storage_scope)
    assert isinstance(value, SecretValue)
    assert value.expose() == DSN_VALUE.encode()


def test_resolve_file_reference_within_scope(
    data_root: Path, store: SecretStore, storage_scope: SecretScope
) -> None:
    write_secret(data_root, "cluster/primary-dsn", SECRET)
    value = store.resolve(
        SecretRef.parse("secret://file/cluster/primary-dsn"), storage_scope
    )
    assert value.expose() == SECRET


def test_resolve_with_a_foreign_scope_is_denied(
    data_root: Path, store: SecretStore
) -> None:
    write_secret(data_root, "cluster/primary-dsn", SECRET)
    identity = SecretStore.scope_for(
        "identity",
        "secret://file/identity/github/",
        "secret://env/RHEO_GITHUB_CLIENT_SECRET",
    )
    for ref in (CLUSTER_REF, "secret://file/cluster/primary-dsn"):
        with pytest.raises(SecretRefusal) as excinfo:
            store.resolve(SecretRef.parse(ref), identity)
        assert excinfo.value.state == "secret_scope_denied"
        assert "identity" in str(excinfo.value)
        assert DSN_VALUE not in str(excinfo.value)
        assert SECRET_TEXT not in str(excinfo.value)


def test_resolve_without_a_scope_is_a_type_error(store: SecretStore) -> None:
    ref = SecretRef.parse(CLUSTER_REF)
    with pytest.raises(TypeError):
        store.resolve(ref)  # type: ignore[call-arg]
    for not_a_scope in (
        None,
        CLUSTER_REF,
        ("secret://env/RHEO_CLUSTER_DSN",),
        object(),
    ):
        with pytest.raises(TypeError):
            store.resolve(ref, not_a_scope)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        store.resolve(CLUSTER_REF, SecretStore.scope_for("storage", CLUSTER_REF))  # type: ignore[arg-type]


def test_missing_variable_is_secret_missing_naming_the_variable(
    data_root: Path,
) -> None:
    store = SecretStore(data_root, environ={})
    scope = SecretStore.scope_for("storage", CLUSTER_REF)
    with pytest.raises(SecretRefusal) as excinfo:
        store.resolve(SecretRef.parse(CLUSTER_REF), scope)
    assert excinfo.value.state == "secret_missing"
    assert "RHEO_CLUSTER_DSN" in str(excinfo.value)


def test_missing_file_is_secret_missing_naming_the_path(
    data_root: Path, store: SecretStore, storage_scope: SecretScope
) -> None:
    with pytest.raises(SecretRefusal) as excinfo:
        store.resolve(SecretRef.parse("secret://file/cluster/absent"), storage_scope)
    assert excinfo.value.state == "secret_missing"
    assert str(data_root / "secrets" / "cluster" / "absent") in str(excinfo.value)


@pytest.mark.parametrize(
    "mode", [0o640, 0o604, 0o644, 0o660, 0o666, 0o610, 0o601, 0o700, 0o755]
)
def test_loose_file_permissions_are_refused(
    data_root: Path, store: SecretStore, storage_scope: SecretScope, mode: int
) -> None:
    write_secret(data_root, "cluster/primary-dsn", SECRET, mode=mode)
    with pytest.raises(SecretRefusal) as excinfo:
        store.resolve(
            SecretRef.parse("secret://file/cluster/primary-dsn"), storage_scope
        )
    assert excinfo.value.state == "secret_permissions"
    assert SECRET_TEXT not in str(excinfo.value)


@pytest.mark.parametrize("mode", [0o600, 0o400])
def test_owner_only_file_permissions_are_accepted(
    data_root: Path, store: SecretStore, storage_scope: SecretScope, mode: int
) -> None:
    write_secret(data_root, "cluster/primary-dsn", SECRET, mode=mode)
    value = store.resolve(
        SecretRef.parse("secret://file/cluster/primary-dsn"), storage_scope
    )
    assert value.expose() == SECRET


def test_a_directory_at_the_secret_path_is_missing_not_readable(
    data_root: Path, store: SecretStore, storage_scope: SecretScope
) -> None:
    (data_root / "secrets" / "cluster" / "primary-dsn").mkdir(parents=True)
    with pytest.raises(SecretRefusal) as excinfo:
        store.resolve(
            SecretRef.parse("secret://file/cluster/primary-dsn"), storage_scope
        )
    assert excinfo.value.state == "secret_missing"


@pytest.mark.parametrize(
    "ref_id",
    [
        "../../outside/key",
        "/etc/passwd",
        "cluster/../../outside/key",
        "",
        "Cluster/Key",
        "cluster//key",
    ],
)
def test_file_backend_refuses_an_id_that_could_leave_its_root(
    tmp_path: Path, ref_id: str
) -> None:
    """The backend validates ids itself; a 0600 file outside the root stays unread."""
    outside = tmp_path / "outside" / "key"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(SECRET)
    outside.chmod(0o600)
    backend = FileBackend(tmp_path / "data" / "secrets")
    with pytest.raises(SecretRefusal) as excinfo:
        backend.read(ref_id)
    assert excinfo.value.state == "secret_ref_malformed"
    assert SECRET_TEXT not in str(excinfo.value)


# --- the startup env check -----------------------------------------------------------


def test_startup_check_refuses_when_a_named_variable_is_missing() -> None:
    settings = {
        "storage.cluster_dsn_ref": CLUSTER_REF,
        "other.file_ref": "secret://file/cluster/primary-dsn",
        "profile": "test",
        "storage.pool_cache_size": 32,
    }
    with pytest.raises(SecretRefusal) as excinfo:
        check_env_references(settings, environ={})
    assert excinfo.value.state == "secret_missing"
    assert "RHEO_CLUSTER_DSN" in str(excinfo.value)
    assert "storage.cluster_dsn_ref" in str(excinfo.value)
    assert check_env_references(settings, environ={"RHEO_CLUSTER_DSN": DSN_VALUE}) == (
        "RHEO_CLUSTER_DSN",
    )


def test_startup_check_refuses_a_malformed_reference_naming_the_key() -> None:
    settings = {"storage.cluster_dsn_ref": "secret://vault/x"}
    with pytest.raises(SecretRefusal) as excinfo:
        check_env_references(settings, environ={})
    assert excinfo.value.state == "secret_ref_malformed"
    assert "storage.cluster_dsn_ref" in str(excinfo.value)
    assert "vault" not in str(excinfo.value)


def test_startup_check_reads_the_resolved_deployment_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_rheo_environment(monkeypatch, tmp_path / "data")
    monkeypatch.setenv("RHEO__storage__cluster_dsn_ref", "secret://env/RHEO_PROBE_DSN")
    with pytest.raises(SecretRefusal) as excinfo:
        check_env_references(resolve())
    assert excinfo.value.state == "secret_missing"
    assert "RHEO_PROBE_DSN" in str(excinfo.value)
    monkeypatch.setenv("RHEO_PROBE_DSN", DSN_VALUE)
    assert check_env_references(resolve()) == ("RHEO_PROBE_DSN",)
