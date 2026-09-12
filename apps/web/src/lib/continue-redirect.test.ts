import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { continueRedirect, mintNonce } from "@/lib/continue-redirect";
import type { RoutingConfig } from "@/lib/routing/config";
import { urlFor } from "@/lib/routing/url-for";

/**
 * The middleware's redirect builder, in both topologies.
 *
 * The assertion that matters is that the result is the **`urlFor`** value: an
 * absolute URL on the identity host. A regression to `identityPath` would return
 * a bare `/auth/continue?...`, which in subdomain mode leaves the browser on the
 * shell host it started on — the identity host's session cookie is never
 * consulted and `/auth/continue`'s open-redirect guard never runs. Every
 * assertion below that goes through `new URL(...)` fails outright on a bare path,
 * and the subdomain case additionally pins a host different from the one the
 * request carried.
 */
const FIXTURES = path.resolve(
  import.meta.dirname,
  "../../../../tests/fixtures/routing",
);

function readFixture(name: string): RoutingConfig {
  return JSON.parse(readFileSync(path.join(FIXTURES, name), "utf8")) as RoutingConfig;
}

const CONFIGS = {
  path: readFixture("path-mode.json"),
  subdomain: readFixture("subdomain-mode.json"),
} as const;

const NONCE = "0123456789abcdef0123456789abcdef";

describe("continueRedirect in subdomain mode", () => {
  const config = CONFIGS.subdomain;
  const requestHost = "circuit.example.test";
  const href = continueRedirect(config, {
    host: requestHost,
    path: "/reports?page=2",
    nonce: NONCE,
  });

  it("crosses to the identity host", () => {
    const url = new URL(href);
    expect(url.host).toBe("auth.example.test");
    expect(url.host).not.toBe(requestHost);
    expect(url.pathname).toBe("/auth/continue");
  });

  it("returns the browser to the host it actually asked for", () => {
    const url = new URL(href);
    expect(url.searchParams.get("return")).toBe(
      "https://circuit.example.test/reports?page=2",
    );
    expect(url.searchParams.get("nonce")).toBe(NONCE);
  });

  it("is exactly the urlFor value, not the identityPath one", () => {
    expect(href).toBe(
      urlFor(
        config,
        "identity",
        `/continue?return=${encodeURIComponent("https://circuit.example.test/reports?page=2")}&nonce=${NONCE}`,
      ),
    );
    expect(href.startsWith("https://")).toBe(true);
  });
});

describe("continueRedirect in path mode", () => {
  const config = CONFIGS.path;
  const requestHost = "example.test";
  const href = continueRedirect(config, {
    host: requestHost,
    path: "/",
    nonce: NONCE,
  });

  it("stays absolute on the single application host", () => {
    const url = new URL(href);
    expect(url.host).toBe("example.test");
    expect(url.pathname).toBe("/auth/continue");
    expect(url.searchParams.get("return")).toBe("https://example.test/");
    expect(url.searchParams.get("nonce")).toBe(NONCE);
  });
});

describe("continueRedirect details", () => {
  it("keeps the port of the forwarded host", () => {
    // A developer on localhost:3000 has to come back to :3000. `/auth/continue`
    // strips the port itself before checking the host against application_hosts().
    const href = continueRedirect(CONFIGS.path, {
      host: "example.test:3000",
      path: "/",
      nonce: NONCE,
    });
    expect(new URL(href).searchParams.get("return")).toBe(
      "https://example.test:3000/",
    );
  });

  it("normalises a path with no leading slash", () => {
    const href = continueRedirect(CONFIGS.path, {
      host: "example.test",
      path: "reports",
      nonce: NONCE,
    });
    expect(new URL(href).searchParams.get("return")).toBe(
      "https://example.test/reports",
    );
  });
});

describe("mintNonce", () => {
  it("is 128 bits of hex", () => {
    expect(mintNonce()).toMatch(/^[0-9a-f]{32}$/);
  });

  it("does not repeat", () => {
    const minted = new Set(Array.from({ length: 64 }, () => mintNonce()));
    expect(minted.size).toBe(64);
  });
});
