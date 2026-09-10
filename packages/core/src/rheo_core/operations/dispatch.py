"""``dispatch(ctx, name, payload) -> OperationOutcome``: authorize, validate, run in
one unit of work, commit.

The ``context_required`` check comes first, before any lookup: ``None`` or an object
that is not a ``WorkspaceContext`` is refused without the registry being consulted.
Then ``authorize``; then the payload is validated into the declaration's input model
(``input_invalid``, naming the failing fields but never echoing values); then **one**
``UnitOfWork`` is opened through ``route(ctx)``, the handler runs, and the unit of
work commits. A handler that raises :class:`OperationRefused` (or a
``StorageRefusal``) rolls back and yields that state; any other exception rolls back
and yields ``failed`` with the exception's class name as the code.

And nothing else. No audit row, no operation record, no outbox event, no
``operation_id`` minted — run 0c's scored work, deliberately absent here. See the
comment in the dispatcher body.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ValidationError
from rheo_contracts import WorkspaceContext

from rheo_core.boundary.context import CONTEXT_REQUIRED, Refusal
from rheo_core.operations.refusals import (
    FAILED,
    INPUT_INVALID,
    OUTPUT_INVALID,
    SUCCEEDED,
    OperationRefused,
)
from rheo_core.operations.registry import REGISTRY, OperationRegistry
from rheo_core.storage.backend import StorageRefusal, UnitOfWork
from rheo_core.storage.routing import open_unit_of_work

_DETAIL_LIMIT: Final = 2000


@dataclass(frozen=True, slots=True)
class OperationError:
    """What a non-success outcome carries: a state name and a showable text."""

    error_code: str
    error_text: str


@dataclass(frozen=True, slots=True)
class OperationOutcome:
    """``state`` is ``succeeded`` with ``result``, or a refusal state / ``failed``
    with ``error``. There is no ``operation_id``: nothing here mints one, which is
    why the API envelope (C8) carries ``operation_id: null`` until 0c."""

    state: str
    result: BaseModel | None = None
    error: OperationError | None = None

    @property
    def ok(self) -> bool:
        return self.state == SUCCEEDED


def _refused(state: str, detail: str | None) -> OperationOutcome:
    return OperationOutcome(state, error=OperationError(state, detail or state))


def _describe_validation_error(exc: ValidationError) -> str:
    """The failing locations and messages, never the input values."""
    parts: list[str] = []
    for error in exc.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)[:_DETAIL_LIMIT]


def _rollback(uow: UnitOfWork) -> None:
    # A commit that failed has already closed the transaction; the ``with`` exit
    # rolls back anything still open, so a closed unit of work is not an error here.
    try:
        uow.rollback()
    except StorageRefusal:
        pass


def dispatch(
    ctx: object,
    name: str,
    payload: Mapping[str, object] | None = None,
    *,
    registry: OperationRegistry = REGISTRY,
) -> OperationOutcome:
    """Run ``name`` for ``ctx`` with ``payload``; see the module docstring."""
    if not isinstance(ctx, WorkspaceContext):
        return _refused(
            CONTEXT_REQUIRED,
            "dispatch() needs a WorkspaceContext from a boundary factory",
        )
    authorized = registry.authorize(ctx, name)
    if isinstance(authorized, Refusal):
        return _refused(authorized.state, authorized.detail)
    operation = authorized.operation
    declaration = operation.declaration
    try:
        model_input = declaration.input_model.model_validate(
            {} if payload is None else payload
        )
    except ValidationError as exc:
        return _refused(INPUT_INVALID, _describe_validation_error(exc))
    try:
        uow = open_unit_of_work(ctx)
    except StorageRefusal as refusal:
        return _refused(refusal.state, refusal.detail)
    # Deliberately: authorize, one unit of work, the handler, commit. No audit row is
    # written here, no operation record is minted, no outbox event is enqueued and no
    # job is scheduled. Those are run 0c's scored deliverables (the hard 0c boundary);
    # ``AuditSpec`` is declared on every mutate operation so 0c2 re-declares nothing,
    # and nothing in this function acts on it.
    with uow:
        try:
            output = operation.handler(ctx, uow, model_input)
            if not isinstance(output, declaration.output):
                _rollback(uow)
                return OperationOutcome(
                    FAILED,
                    error=OperationError(
                        OUTPUT_INVALID,
                        f"{name} returned {type(output).__name__}, not "
                        f"{declaration.output.__name__}",
                    ),
                )
            uow.commit()
        except OperationRefused as refusal:
            _rollback(uow)
            return _refused(refusal.state, refusal.detail)
        except StorageRefusal as refusal:
            _rollback(uow)
            return _refused(refusal.state, refusal.detail)
        except Exception as exc:
            _rollback(uow)
            return OperationOutcome(
                FAILED,
                error=OperationError(type(exc).__name__, str(exc)[:_DETAIL_LIMIT]),
            )
    return OperationOutcome(SUCCEEDED, result=output)
