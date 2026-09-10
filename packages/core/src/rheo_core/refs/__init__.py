"""Identifier minting, and (from C4) the record resolver over typed record references.

0b1 populates the UUIDv7 generator only. ``resolver.py`` — resolution of a
``RecordRef`` under the caller's permission — arrives with the context boundary.
"""

from rheo_core.refs.uuid7 import uuid7

__all__ = ["uuid7"]
