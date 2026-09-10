"""The Rheo Stream framework core.

Boundary adapters, the service registry, storage and unit of work, migrations,
settings, secret store, identity/sessions/tokens, the outbox/worker runtime, operations
and audit, approvals, the deletion coordinator, export/restore, routing, and the record
resolver. The core imports no module distribution: neither ``rheo_core`` nor
``rheo_contracts`` depends on any ``rheo_<module>`` package.
"""
