/**
 * The web tier's read of `core`'s liveness/composition seam.
 *
 * This helper — not `next build` — is where the fail-soft behaviour lives. The
 * shell page sets `export const dynamic = 'force-dynamic'`, so the route is never
 * prerendered and this code never runs during a build; a broken mapping here would
 * pass every build gate and only surface at a real `next start` with `core` down.
 * `core-health.test.ts` pins it instead.
 *
 * The source `/healthz` body (owned by `apps/core`) is snake_case
 * `{ "status": "ok", "contract_version": <int> }`; the camelCase `contractVersion`
 * on the return type is the web-side shape.
 */

export type CoreHealthResult =
  | { status: "ok"; contractVersion: number }
  | { status: "unavailable" };

interface CoreHealthBody {
  status: string;
  contract_version: number;
}

function isCoreHealthBody(value: unknown): value is CoreHealthBody {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const body = value as Record<string, unknown>;
  return (
    typeof body.status === "string" &&
    typeof body.contract_version === "number"
  );
}

/**
 * Fetch and parse `core`'s `/healthz`. Never throws: any failure — the fetch
 * rejecting (network error / `core` unreachable), a non-200 response, or a body
 * that does not parse or match the expected shape — degrades to
 * `{ status: "unavailable" }`.
 */
export async function fetchCoreHealth(baseUrl: string): Promise<CoreHealthResult> {
  try {
    const response = await fetch(`${baseUrl}/healthz`, { cache: "no-store" });
    if (!response.ok) {
      return { status: "unavailable" };
    }
    const body: unknown = await response.json();
    if (isCoreHealthBody(body)) {
      return { status: "ok", contractVersion: body.contract_version };
    }
    return { status: "unavailable" };
  } catch {
    return { status: "unavailable" };
  }
}
