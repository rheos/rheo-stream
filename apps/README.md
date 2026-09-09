# Application entry points

Reserved for application composition and interface adapters, such as a CLI, web
application, MCP endpoint, or worker entry point. No applications are implemented.

Entry points resolve trusted workspace context and call application services.
They must not duplicate domain rules or require a model session for deterministic
intake and ordinary operations. App boundaries do not imply separate deployments.
