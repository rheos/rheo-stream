import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchCoreHealth } from "./core-health";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchCoreHealth fail-soft mapping", () => {
  it("degrades a fetch rejection to unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("ECONNREFUSED")));

    await expect(fetchCoreHealth("http://core.internal")).resolves.toEqual({
      status: "unavailable",
    });
  });

  it("degrades a non-200 response to unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ status: "ok", contract_version: 1 }),
      }),
    );

    await expect(fetchCoreHealth("http://core.internal")).resolves.toEqual({
      status: "unavailable",
    });
  });

  it("degrades a mismatched body to unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ wrong: "shape" }),
      }),
    );

    await expect(fetchCoreHealth("http://core.internal")).resolves.toEqual({
      status: "unavailable",
    });
  });

  it("maps a valid body to ok with camelCase contractVersion", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ status: "ok", contract_version: 1 }),
      }),
    );

    await expect(fetchCoreHealth("http://core.internal")).resolves.toEqual({
      status: "ok",
      contractVersion: 1,
    });
  });
});
