import type { RoutingConfig } from "@/lib/routing/config";
import { continueHref } from "@/lib/routing/links";
import { joinPrefix } from "@/lib/routing/url-for";

/**
 * The pure builder behind `middleware.ts`'s unauthenticated redirect (C9, B18).
 *
 * Kept separate from the middleware so it can be tested without a request object,
 * and so the one rule that matters here is visible on its own: the redirect is
 * built with **`urlFor`** (through `continueHref`), never `identityPath`.
 *
 * `identityPath` returns a bare path with no host. In subdomain mode the
 * unauthenticated request is sitting on the *shell* host, so a bare path leaves
 * the browser exactly where it started — the identity host is never reached, the
 * session cookie it holds is never consulted, and the open-redirect guard on
 * `/auth/continue` never runs. The tests assert the built URL is absolute and on
 * the identity host precisely so that regression cannot pass.
 *
 * The `return` target is built from the **forwarded host**, never a configured or
 * hard-coded name, so a deployment behind a proxy returns the browser to the host
 * it actually asked for. That value is attacker-influenceable, and deliberately
 * not validated here: `/auth/continue` refuses `invalid_return` for any host
 * outside `application_hosts()`, and that refusal is the guard. What this builder
 * must guarantee — and does, because the target comes only from the routing
 * configuration — is that the *redirect destination itself* can never be
 * attacker-controlled.
 */

/** The host-only nonce cookie bound to the grant `/auth/continue` writes. */
export const CONTINUE_COOKIE = "rheo_continue";

/** 128 bits, per `spec.md` § Web. */
const NONCE_BYTES = 16;

/**
 * A 128-bit nonce as lowercase hex.
 *
 * `crypto.getRandomValues`, never `Math.random`: this value is the only thing
 * binding a grant to the browser that asked for it, so a predictable one would let
 * a third party redeem someone else's grant.
 */
export function mintNonce(): string {
  const bytes = new Uint8Array(NONCE_BYTES);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/**
 * The absolute `/auth/continue` URL for an unauthenticated request on `host`
 * asking for `path`.
 */
export function continueRedirect(
  config: RoutingConfig,
  options: { host: string; path: string; nonce: string },
): string {
  const returnTarget = `${config.scheme}://${options.host}${joinPrefix("", options.path)}`;
  return continueHref(config, { returnTarget, nonce: options.nonce });
}
