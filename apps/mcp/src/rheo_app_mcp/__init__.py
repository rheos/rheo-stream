"""MCP facade (C8, run 0b2): the session resolver and the ``call_tool`` seam.

Imports ``rheo_core.boundary``, ``rheo_core.operations`` and ``rheo_core.tokens``
(the AST scan in ``tests/test_mcp_boundary.py`` pins this allowlist, landed in
0b2 rather than "later") plus ``rheo_contracts``, and nothing from
``rheo_core.storage``, ``rheo_core.migrations``, or a DB driver. No transport
yet: the streamable-HTTP server and the ``mcp`` SDK land in 0c3.
"""

from rheo_contracts import CONTRACT_VERSION

__all__ = ["CONTRACT_VERSION"]
