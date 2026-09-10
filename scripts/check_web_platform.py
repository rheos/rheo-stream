#!/usr/bin/env python3
"""Platform-only denylist scan of apps/web (the criterion-23 gate).

`next build` does not fail on a `@vercel/*` import or an edge-runtime declaration,
so this static scan — not the build — is what keeps apps/web a plain, self-hostable
Next.js app with no platform-only feature. It is a foundation, not exhaustive: later
phases tighten it as the web surface grows (spec.md Technical Risks, risk 5).

Runs under the system python3 (3.9-compatible, no third-party deps), mirroring
scripts/check_repository.py. Scans source only: `.next/`, `node_modules/`, and other
generated dirs carry `@vercel/*` and "edge" strings from Next.js/vendor internals, so
they are skipped — and the CI web job runs `next build` before this gate, so
apps/web/.next exists at scan time.
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "apps" / "web"

# Generated build output and vendored dependencies — skipped so their internals do
# not false-positive this scan.
SKIP_DIRS = frozenset({".next", "node_modules", "dist", "build", ".turbo"})

CODE_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})

# A JS/TS string literal quote: " or ' or ` (backtick as \x60 to avoid quoting noise).
_QUOTE = r"[\x22'\x60]"

# import/require/from ... "@vercel/..." — a platform-only package import.
_VERCEL_IMPORT = re.compile(r"(?:from|import|require)\s*\(?\s*" + _QUOTE + r"@vercel/")
# export const runtime = 'edge' | "edge" | `edge`
_EDGE_EXPORT = re.compile(r"export\s+const\s+runtime\s*=\s*(" + _QUOTE + r")edge\1")
# a runtime: 'edge' key inside a next.config.*
_EDGE_CONFIG_KEY = re.compile(r"\bruntime\s*:\s*(" + _QUOTE + r")edge\1")
_NEXT_CONFIG = re.compile(r"^next\.config\.(?:js|mjs|ts|cjs)$")


def _source_files():
    for dirpath, dirnames, filenames in os.walk(WEB_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def check():
    if not WEB_ROOT.is_dir():
        return [f"apps/web not found at {WEB_ROOT}"]
    errors = []
    for path in sorted(_source_files()):
        relative = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            # Non-text/unreadable file under a source tree: nothing to scan.
            continue
        if path.suffix in CODE_SUFFIXES:
            if _VERCEL_IMPORT.search(text):
                errors.append(f"Platform-only @vercel/* import: {relative}")
            if _EDGE_EXPORT.search(text):
                errors.append(f"Edge runtime export declared: {relative}")
        if _NEXT_CONFIG.match(path.name) and _EDGE_CONFIG_KEY.search(text):
            errors.append(f"Edge runtime configured in next.config: {relative}")
    return errors


def main():
    try:
        findings = check()
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
        print(f"Web platform check failed: {error}", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding, file=sys.stderr)
    if not findings:
        print("Web platform checks passed: apps/web is platform-neutral.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
