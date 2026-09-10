"""The engine pool: one ``Engine`` per ``database_name``, in an LRU.

The LRU caches **engines only**, keyed by the database name the caller read from the
registry row. It never caches a ``workspace_id -> database_name`` mapping: that read
happens in ``routing.route()`` on every call, so a renamed or re-pointed workspace can
never be served from a stale decision. Eviction disposes the evicted engine, so a
deployment with more workspaces than ``storage.pool_cache_size`` holds at most that
many connection pools open.
"""

import re
import threading
from collections import OrderedDict
from typing import Final

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL

_DATABASE_NAME: Final = re.compile(r"[a-z_][a-z0-9_]{0,62}")


def check_database_name(name: str) -> str:
    """Refuse anything that is not a lowercase identifier of at most 63 characters.

    Every database name this package interpolates into DDL (``CREATE DATABASE``,
    ``DROP DATABASE``) passes through here first, and is quoted besides.
    """
    if not isinstance(name, str) or not _DATABASE_NAME.fullmatch(name):
        raise ValueError("database names are lowercase identifiers of at most 63 chars")
    return name


class EnginePool:
    """An LRU of engines keyed by database name, all on one cluster URL."""

    def __init__(self, cluster_url: URL, *, cache_size: int, pool_size: int) -> None:
        if cache_size < 1 or pool_size < 1:
            raise ValueError("cache_size and pool_size must be positive")
        self._cluster_url = cluster_url
        self._cache_size = cache_size
        self._pool_size = pool_size
        self._engines: OrderedDict[str, Engine] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def cluster_url(self) -> URL:
        """The cluster URL every engine is derived from (password hidden in ``str``)."""
        return self._cluster_url

    def engine_for(self, database_name: str) -> Engine:
        """The engine for ``database_name``, created on first use and kept while hot."""
        name = check_database_name(database_name)
        with self._lock:
            engine = self._engines.get(name)
            if engine is not None:
                self._engines.move_to_end(name)
                return engine
            engine = create_engine(
                self._cluster_url.set(database=name),
                pool_size=self._pool_size,
                max_overflow=0,
                pool_pre_ping=True,
            )
            self._engines[name] = engine
            evicted: list[Engine] = []
            while len(self._engines) > self._cache_size:
                _, stale = self._engines.popitem(last=False)
                evicted.append(stale)
        for stale in evicted:
            stale.dispose()
        return engine

    def cached(self) -> tuple[str, ...]:
        """The database names currently holding an engine, least recent first."""
        with self._lock:
            return tuple(self._engines)

    def discard(self, database_name: str) -> None:
        """Dispose and forget the engine for ``database_name``, if cached."""
        with self._lock:
            engine = self._engines.pop(database_name, None)
        if engine is not None:
            engine.dispose()

    def dispose_all(self) -> None:
        with self._lock:
            engines = list(self._engines.values())
            self._engines.clear()
        for engine in engines:
            engine.dispose()
