import { defineConfig } from "vitest/config";

/**
 * The web tier's vitest configuration (C9).
 *
 * Created by this chunk — `apps/web` ran vitest configless until now, and
 * `core-health.test.ts` (0a's) must keep passing under it unchanged.
 *
 * Two things this file deliberately does NOT do:
 *
 * - It does not set `server.fs.allow` for the repo-root fixture. That is a Vite
 *   **dev-server** option and has no effect on `vitest run`; the routing tests read
 *   `tests/fixtures/routing/*.json` with `readFileSync` from `import.meta.dirname`
 *   instead, which needs no allowance at all.
 * - It adds no plugin and no new dependency. Every test here is over plain
 *   functions or `next/server` objects; nothing renders a component, so no DOM
 *   environment and no React transform are needed.
 *
 * `RHEO_ROUTING_MODE` needs no passthrough machinery either — vitest already
 * exposes `process.env` in the node environment. The `env` entry below is only a
 * default for a bare local `pnpm -C apps/web test`; CI overrides it per mode
 * (`RHEO_ROUTING_MODE=path` then `=subdomain`), and an exported value always wins
 * over this default.
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    env: {
      RHEO_ROUTING_MODE: process.env.RHEO_ROUTING_MODE ?? "path",
    },
  },
});
