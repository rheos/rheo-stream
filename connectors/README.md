# Connectors

Reserved for external source and destination adapters: authenticated intake,
webhooks, imports, polling, and approved handoffs.

Connectors own transport and provider translation, not domain policy. Credentials
and account-specific configuration stay private. Custom funnels should use a
generic contract without requiring a provider-specific branch in the core.
