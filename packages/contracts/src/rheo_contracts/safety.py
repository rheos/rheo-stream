"""The operation safety classes (FR-24, R3).

Six classes, exactly as ratified in ``docs/architecture/confirmation-and-safety.md``
§ The six classes and what the dispatcher does with each. This module holds the names
only. The dispatcher behaviour behind them — approvals, guards, audit rows, external
actions — is 0c's, and a partial version of it here would be a boundary violation, not
a head start.
"""

from enum import StrEnum


class SafetyClass(StrEnum):
    """Exactly one is declared per operation and per tool; registration refuses none."""

    READ = "read"
    DRAFT = "draft"
    MUTATE = "mutate"
    DESTRUCTIVE = "destructive"
    EXTERNAL = "external"
    FINANCIAL = "financial"
