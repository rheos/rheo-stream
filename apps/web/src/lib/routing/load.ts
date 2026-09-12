import { isRoutingConfig, type RoutingConfig } from "@/lib/routing/config";

/**
 * The internal-API client for the routing configuration (C9).
 *
 * Mirrors `core-health.ts:41`'s `fetchCoreHealth` exactly: one `try`, a narrowing
 * guard, and a single "unavailable" sentinel for every failure — a rejected fetch,
 * a non-200, an unparseable or mis-shaped body, **and an unset environment
 * variable**. It never throws, so no page has to catch.
 *
 * Two environment variables, both required, neither interchangeable:
 *
 * - `RHEO_CORE_INTERNAL_API_URL` — the internal listener (port 8100,
 *   container-network only). **Not `RHEO_CORE_INTERNAL_URL`**, which is 0a's
 *   variable for the *public* listener on 8000 and stays pointed there for
 *   `page.tsx`'s `/healthz` read. The two resolve to the same place on a
 *   developer's laptop and to different ones inside the container network, which
 *   is exactly the kind of confusion a green local suite would not catch.
 * - `RHEO_INTERNAL_SECRET` — the shared secret every internal request presents in
 *   `X-Rheo-Internal`; the listener refuses before either endpoint runs without it.
 *
 * Fetched once per process (`spec.md` § Web) and memoised on success only: the
 * routing table is deployment configuration, and the middleware would otherwise
 * make an extra round trip on every navigation. Failures are never memoised, so a
 * shell that started before `core` recovers on its own. `cache: "no-store"` keeps
 * Next's own fetch cache out of that one request.
 */

/**
 * The internal listener's two endpoints.
 *
 * They live here — rather than each beside its caller — so that no file under
 * `apps/web/src` outside this `routing/` package contains a route literal at all,
 * which lets `scripts/check_routing_literals.py` (11's) scan for one without an
 * allowlist. Note what they are not: neither is a routing-table surface. They are
 * served by the internal listener, never reachable from a browser, and identical
 * in both topologies, so they are constants rather than `urlFor` calls.
 */
export const INTERNAL_ROUTING_PATH = "/internal/v1/routing";
export const INTERNAL_SESSION_PATH = "/internal/v1/session";

/** The shared-secret header every internal-listener request carries. */
export const INTERNAL_SECRET_HEADER = "X-Rheo-Internal";

export type RoutingConfigResult =
  | { state: "ok"; config: RoutingConfig }
  | { state: "unavailable" };

/** The internal listener's base URL and shared secret, or `null` if either is unset. */
export function internalApiCredentials(): { baseUrl: string; secret: string } | null {
  const baseUrl = process.env.RHEO_CORE_INTERNAL_API_URL;
  const secret = process.env.RHEO_INTERNAL_SECRET;
  if (!baseUrl || !secret) {
    return null;
  }
  return { baseUrl, secret };
}

let cached: RoutingConfig | null = null;

export async function loadRoutingConfig(): Promise<RoutingConfigResult> {
  if (cached !== null) {
    return { state: "ok", config: cached };
  }
  const credentials = internalApiCredentials();
  if (credentials === null) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${credentials.baseUrl}${INTERNAL_ROUTING_PATH}`,
      {
        cache: "no-store",
        headers: { [INTERNAL_SECRET_HEADER]: credentials.secret },
      },
    );
    if (!response.ok) {
      return { state: "unavailable" };
    }
    const body: unknown = await response.json();
    if (!isRoutingConfig(body)) {
      return { state: "unavailable" };
    }
    cached = body;
    return { state: "ok", config: body };
  } catch {
    return { state: "unavailable" };
  }
}
