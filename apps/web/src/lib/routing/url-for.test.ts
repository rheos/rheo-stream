import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  API,
  DOCS,
  IDENTITY,
  INTEGRATION,
  MCP,
  SHELL,
  isRoutingConfig,
  type RoutingConfig,
} from "@/lib/routing/config";
import {
  applicationHosts,
  identityPath,
  joinPrefix,
  urlFor,
} from "@/lib/routing/url-for";

/**
 * The TypeScript half of B10, driven by the same three fixture files the Python
 * suite reads (`tests/test_routing.py`).
 *
 * The fixture is the contract, not a convenience: `tests/fixtures/routing/*.json`
 * is 06's, and if an expected string and this implementation disagree, the
 * implementation is wrong. Nothing here edits a fixture entry to make an
 * assertion pass — that would silently retire the cross-language half of B10,
 * which is the entire reason the files exist.
 *
 * Read with `readFileSync`, not a static `import`: the files live at the
 * repository root, five directory levels above this one (`apps` -> `web` -> `src`
 * -> `lib` -> `routing`), and `import.meta.dirname` rather than `__dirname`
 * because this package transforms to ESM under Vitest.
 */
const FIXTURES = path.resolve(
  import.meta.dirname,
  "../../../../../tests/fixtures/routing",
);

function readFixture<T>(name: string): T {
  return JSON.parse(readFileSync(path.join(FIXTURES, name), "utf8")) as T;
}

const MODES = ["path", "subdomain"] as const;
type Mode = (typeof MODES)[number];

const CONFIGS: Record<Mode, RoutingConfig> = {
  path: readFixture<RoutingConfig>("path-mode.json"),
  subdomain: readFixture<RoutingConfig>("subdomain-mode.json"),
};

interface Expectation {
  mode: Mode;
  surface?: string;
  identity_path?: boolean;
  application_hosts?: string[];
  path?: string;
  expected?: string;
}

const EXPECTATIONS = readFixture<Expectation[]>("expected-urls.json");

const RAW_MODE = process.env.RHEO_ROUTING_MODE ?? "path";

describe("the mode under test", () => {
  it("is one of the two topologies the fixture covers", () => {
    // A typo in RHEO_ROUTING_MODE would otherwise select nothing and make every
    // mode-driven assertion below pass by covering zero cases.
    expect(MODES).toContain(RAW_MODE);
  });
});

const MODE = RAW_MODE as Mode;
const CONFIG = CONFIGS[MODE];

const urlCases = EXPECTATIONS.filter(
  (entry) => entry.mode === MODE && entry.surface !== undefined,
);
const identityPathCases = EXPECTATIONS.filter(
  (entry) => entry.mode === MODE && entry.identity_path === true,
);
const hostCases = EXPECTATIONS.filter(
  (entry) => entry.mode === MODE && entry.application_hosts !== undefined,
);

describe(`the fixture for ${MODE} mode`, () => {
  it("parses as a routing configuration", () => {
    for (const mode of MODES) {
      expect(isRoutingConfig(CONFIGS[mode])).toBe(true);
    }
  });

  it("covers both modes and every non-external surface", () => {
    expect(new Set(urlCases.map((entry) => entry.surface))).toEqual(
      new Set([SHELL, IDENTITY, API, MCP]),
    );
    expect(identityPathCases.length).toBeGreaterThan(0);
    expect(hostCases).toHaveLength(1);
  });
});

describe(`urlFor in ${MODE} mode`, () => {
  it.each(urlCases.map((entry) => [`${entry.surface} ${entry.path}`, entry]))(
    "matches the fixture for %s",
    (_label, entry) => {
      expect(urlFor(CONFIG, entry.surface as string, entry.path as string)).toBe(
        entry.expected,
      );
    },
  );
});

describe(`identityPath in ${MODE} mode`, () => {
  it.each(identityPathCases.map((entry) => [entry.path as string, entry]))(
    "matches the fixture for %s",
    (_label, entry) => {
      expect(identityPath(CONFIG, entry.path as string)).toBe(entry.expected);
    },
  );
});

describe(`applicationHosts in ${MODE} mode`, () => {
  it("matches the fixture", () => {
    const expected = [...(hostCases[0].application_hosts as string[])].sort();
    expect(applicationHosts(CONFIG)).toEqual(expected);
  });

  it("does not include a host this application never serves", () => {
    expect(applicationHosts(CONFIG)).not.toContain("docs.example.test");
    expect(applicationHosts(CONFIG)).not.toContain("elsewhere.example.test");
  });
});

// --- the rules the fixture must not be able to retire -------------------------
//
// Asserted against literals in both modes, in every mode run, so that editing a
// fixture entry cannot quietly remove them — and so a mutant that swaps the two
// mode formulas fails here even if a mode's own cases were somehow empty. The
// Python suite pins the identical pair.

describe("rules asserted against literals, in both modes", () => {
  it("builds the documented OAuth callback URL", () => {
    expect(urlFor(CONFIGS.subdomain, IDENTITY, "/callback")).toBe(
      "https://auth.example.test/auth/callback",
    );
    expect(urlFor(CONFIGS.path, IDENTITY, "/callback")).toBe(
      "https://example.test/auth/callback",
    );
  });

  it("does not double the slash for a root surface path", () => {
    // `shell`'s path is `/`; the naive `surface.path + path` concatenation yields
    // `https://example.test//login`, which is a different origin to a browser.
    expect(urlFor(CONFIGS.path, SHELL, "/login")).toBe("https://example.test/login");
    expect(urlFor(CONFIGS.subdomain, SHELL, "/login")).toBe(
      "https://circuit.example.test/login",
    );
    expect(urlFor(CONFIGS.path, SHELL, "/")).toBe("https://example.test/");
    expect(urlFor(CONFIGS.subdomain, SHELL, "/")).toBe("https://circuit.example.test/");
  });

  it("keeps the two modes distinct for every case covered in both", () => {
    const byCase = new Map<string, Set<string>>();
    for (const entry of EXPECTATIONS) {
      if (entry.surface === undefined || entry.expected === undefined) {
        continue;
      }
      const key = `${entry.surface} ${entry.path}`;
      const seen = byCase.get(key) ?? new Set<string>();
      seen.add(entry.expected);
      byCase.set(key, seen);
    }
    const covered = [...byCase.entries()].filter(([, seen]) => seen.size > 0);
    expect(covered.length).toBeGreaterThan(0);
    for (const key of [`${IDENTITY} /callback`, `${SHELL} /login`]) {
      expect(byCase.get(key)?.size).toBe(MODES.length);
    }
  });
});

// --- the join rule ------------------------------------------------------------

describe("joinPrefix", () => {
  it("normalises a path with no leading slash", () => {
    // `"/api" + "v1/ops"` is `/apiv1/ops` — silently wrong, not loudly wrong.
    expect(joinPrefix("/api", "v1/ops")).toBe("/api/v1/ops");
    expect(joinPrefix("/api", "/v1/ops")).toBe("/api/v1/ops");
  });

  it("lets a root prefix contribute nothing", () => {
    expect(joinPrefix("/", "/login")).toBe("/login");
    expect(joinPrefix("", "/login")).toBe("/login");
    expect(joinPrefix("/", "/")).toBe("/");
  });

  it.each(MODES)("is the same rule urlFor and identityPath apply (%s)", (mode) => {
    const config = CONFIGS[mode];
    expect(urlFor(config, API, "v1/operations")).toBe(
      urlFor(config, API, "/v1/operations"),
    );
    expect(identityPath(config, "continue")).toBe("/auth/continue");
    expect(urlFor(config, SHELL, "")).toBe(urlFor(config, SHELL, "/"));
  });

  it.each(MODES)(
    "keeps a relocated root identity prefix from going protocol-relative (%s)",
    (mode) => {
      // `routing.identity.path` is operator-settable with no closed choice set.
      // Raw concatenation turned `"/"` into `"//continue"`, which a browser reads
      // as scheme-relative: a URL for a host called `continue`.
      const relocated: RoutingConfig = {
        ...CONFIGS[mode],
        surfaces: {
          ...CONFIGS[mode].surfaces,
          identity: { ...CONFIGS[mode].surfaces.identity, path: "/" },
        },
      };
      expect(identityPath(relocated, "/continue")).toBe("/continue");
      expect(identityPath(relocated, "/continue").startsWith("//")).toBe(false);
      expect(urlFor(relocated, IDENTITY, "/continue").endsWith("/continue")).toBe(true);
    },
  );
});

// --- refusals -----------------------------------------------------------------

describe(`urlFor refusals in ${MODE} mode`, () => {
  it("refuses an unknown surface", () => {
    expect(() => urlFor(CONFIG, "nonesuch", "/")).toThrow(/nonesuch/);
  });

  it.each([DOCS, INTEGRATION])("refuses the %s surface", (surface) => {
    // Matched on the refusal's own words rather than the surface name: the name
    // alone would also match the unknown-surface error, so the assertion would
    // still pass against an implementation that had simply lost the surface.
    expect(() => urlFor(CONFIG, surface, "/")).toThrow(
      /not served by this application/,
    );
  });

  it("has no module surfaces in this release", () => {
    expect(CONFIG.surfaces.modules).toEqual({});
  });
});
