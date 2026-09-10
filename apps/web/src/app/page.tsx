import { fetchCoreHealth, type CoreHealthResult } from "@/lib/core-health";

// Never prerender this route: reading `core`'s /healthz is request-time work, and
// this line — not the fetchCoreHealth try/catch — is what keeps `next build` green
// with no `core` process running (the page body never executes at build time).
export const dynamic = "force-dynamic";

export default async function Page() {
  const baseUrl = process.env.RHEO_CORE_INTERNAL_URL;
  const health: CoreHealthResult = baseUrl
    ? await fetchCoreHealth(baseUrl)
    : { status: "unavailable" };

  return (
    <main>
      <h1>rheoStream</h1>
      {health.status === "ok" ? (
        <p>core: ok (contract v{health.contractVersion})</p>
      ) : (
        <p>core: unavailable</p>
      )}
    </main>
  );
}
