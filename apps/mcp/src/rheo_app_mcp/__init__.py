"""MCP facade placeholder.

Imports contracts only. Must never import rheo_core.storage or a DB driver
(criterion 20) — tests/test_mcp_boundary.py pins this as a static scan.
The service registry (rheo_core.operations) is a 0c dependency, not 0a's.
"""

from rheo_contracts import CONTRACT_VERSION

__all__ = ["CONTRACT_VERSION"]
