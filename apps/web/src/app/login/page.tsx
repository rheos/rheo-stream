import { loginHref } from "@/lib/routing/links";
import { loadRoutingConfig } from "@/lib/routing/load";

// Request-time, like the shell: the routing configuration comes from `core` over
// the internal API, so this page must never be prerendered against a build-time
// snapshot of it.
export const dynamic = "force-dynamic";

/**
 * The sign-in page: one link, built by `loginHref`, and nothing else.
 *
 * The href differs between topologies (`https://example.test/auth/login` in path
 * mode, `https://auth.example.test/auth/login` in subdomain mode), which is why it
 * is built rather than written.
 */
export default async function LoginPage() {
  const routing = await loadRoutingConfig();

  return (
    <main>
      <h1>Sign in</h1>
      {routing.state === "ok" ? (
        <a href={loginHref(routing.config)}>Sign in</a>
      ) : (
        <p>sign-in: unavailable</p>
      )}
    </main>
  );
}
