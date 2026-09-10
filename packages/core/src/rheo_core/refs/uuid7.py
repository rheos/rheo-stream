"""RFC 9562 §5.7 UUID version 7, minted in-process.

Python 3.12's standard library has no ``uuid7``; ``docs/architecture/identifiers.md``
allows "a vetted fallback", and twenty lines with a version/variant/ordering test beats
adding a Rust wheel to the frozen lock. The web tier never mints durable identifiers:
every id in this system is minted here, in the transaction that creates the row.
"""

import secrets
import threading
import time
from uuid import UUID

_LOCK = threading.Lock()
_LAST = 0


def uuid7() -> UUID:
    """Mint a UUIDv7: 48-bit big-endian Unix-ms timestamp, version 7, variant 10.

    Strictly increasing, including within a single millisecond and across a backwards
    clock step. That is RFC 9562 §6.2's dedicated-counter method, applied to the low
    bits of ``rand_b``: incrementing the previous value by one cannot disturb the
    version or variant bits without 2**62 mints inside one millisecond, and it is what
    keeps B-tree inserts local when a batch of rows is created together.
    """
    global _LAST
    timestamp_ms = time.time_ns() // 1_000_000
    raw = bytearray(timestamp_ms.to_bytes(6, "big") + secrets.token_bytes(10))
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    value = int.from_bytes(raw, "big")
    with _LOCK:
        if value <= _LAST:
            value = _LAST + 1
        _LAST = value
    return UUID(int=value)
