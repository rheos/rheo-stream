# Framework core

Reserved for workspace identity, policy enforcement, module registration and
lifecycle, durable execution, audit, secret access, and data-operation coordination.

The core must remain independent of professions and optional domain modules.
Modules request scoped private storage; they do not write user data into source
packages. Implementation language and storage adapters remain undecided.
