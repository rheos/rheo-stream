# Later phases: architectural sketches

**Part of:** the [architecture specification](README.md). One page per public phase after release
one, written to show that the release-one decisions do not foreclose them. These are sketches;
each phase is planned when its predecessor lands, as the [build plan](../requirements/build-plan.md)
says.

## Phase 4: the optional job-search workflow

**What it adds.** A capability bundle, not a module: pipeline presets for job search, extension
fields under `ext.jobsearch.*` (candidate fit, application questions), job-source connectors, the
multi-observation enrichment where an email alert, a copied search result, and a full posting
converge on one opportunity, and the proposal drafting and answer-library screens. The
`proposal` template kind joins `preset_template` here, in a Leads migration; release one carries
`followup` only.

**How it fits.** Every job-shaped field is a `preset_field` with `ext.jobsearch.` targets, so the
Leads core gains no column (FR 44). Connectors implement the same `Delivery` contract as the three
release-one transports; a job board is a connection with a mapping whose `subject_id_path` yields
the provider's posting identifier, which the routing action `attach_to_open_opportunity` uses to
enrich rather than duplicate. The field-derivation rule already handles thin-then-rich
(completeness) and the provisional score is a qualification with `uncertainty` high until a full
posting arrives. The email transport is a deterministic poller: a connector with a durable cursor
stored on the connection (`intake_connection` gains a `cursor` column in a Leads migration), no
model involved. A workspace setting `leads.capabilities.jobsearch` gates scheduling of its
workers and visibility of its screens; records stay readable and exportable with it off.

**What it must not do.** Add a core column, a provider-specific branch in the intake path, or a
second safety class. Provider licensing is reviewed per source before any hosted use.

## Phase 5: the work-in-motion module

**What it adds.** `current`: projects, tasks, next actions, status, priority, due dates,
dependencies, commitments. Ported from the predecessor's Next.js screens and moved from a local
SQLite file to the `current` schema of the workspace database.

**How it fits.** A manifest like the others; `current` requires nothing and `leads` declares it
optional. The handoff operation from phase three
([handoffs](confirmation-and-safety.md#the-handoff-operation-fr-45-criterion-64)) gains its first
registered destination: `leads.handoff.request` writes the record `pending` instead of
`unavailable` and calls `current.work.create_from_handoff(handoff_ref, snapshot)`, the
`EXTERNAL`-class execution with its own approval, `DestinationGuard`, and `external_action`
record, with `KEYED` idempotency on the handoff reference so a retry after a lost response
returns the created work reference from `core.idempotency_result` rather than creating a second.
Leads writes the outcome into `handoff.state` and `result_ref` from the operation record and
displays the work's state through the record resolver, never a second editable copy. If a preset
then needs to name a destination, a `preset_handoff(preset_id, version, destination_ref)` table
arrives in the same Leads migration; release one ships neither. Completing a task publishes
`current.task.completed`, which no other module may treat as a domain outcome.

**What it must not do.** Become invoicing or accounting; those remain the external back-office
integration's.

## Phase 6: channels and the second runtime

**What it adds.** The OpenRouter adapter ([shape](runtime-and-mcp.md#the-openrouter-adapter-phase-six-shape-only))
and a Telegram channel.

**How it fits.** The adapter satisfies the same discovery and yields the same events; criterion
15's gate and the run-scoped token are unchanged. A channel is a fifth boundary adapter: it
resolves an enrolled account through an authenticated enrollment record
(`control.channel_enrollment(channel, external_conversation_id, account_id, workspace_id,
audience_kind)`), builds a `WorkspaceContext` with `audience = channel:<conversation>`, and calls
the same services. Group conversations and private conversations are different audiences, so a
runtime session bound to one is never resumed for the other. Approval requests in a channel
return the `approval_required` state as a message with the approval id; approval itself still
happens through the web interface or the CLI, or through a channel-specific confirmation that is
itself an authenticated action by the enrolled account and is recorded with `approved_entry =
channel`. Revocation of an enrollment revokes queued work bound to that audience.

**What it must not do.** Give a channel any operation a web session lacks, or resume a global
latest session. Codex CLI stays a validation target: if its adapter is attempted, it passes the
same capability gate and contract suite before it is called supported, and no phase schedules it.

## Phase 7: framework proof and a v0.1 release

**What it adds.** The rest of the module lifecycle (disable, re-enable, remove, purge, restore)
as written in the [module contract](module-contract.md#upgrade-disable-re-enable-remove-purge-restore-on-paper-d5);
a synthetic specialist module registering records, tools, screens, jobs, migrations, and an
export through the public extension points; domain packs; the invitation flow and self-service
membership; the licence.

**How it fits.** The lifecycle operations act on `core.module_state` and the registration epoch
already present. The synthetic module is a distribution with a manifest and no core change, which
is exactly what criterion 24 already proved for the memory module. Domain packs are data:
a versioned bundle naming modules, presets, mappings, and vocabulary, applied by an operation that
produces an inspectable plan and refuses to overwrite a workspace setting it did not set; the
settings rows gain a `set_by_pack` column for that. Invitations are a control-plane state machine
(`control.invitation`) with an email delivery dependency through a connector, and FR 6 gains its
test with a second member present. Named capability declarations layer over the manifest
(`provides`), giving the capability registry the requirements kept out of release one.

**What it must not do.** Turn the synthetic module into a product for another profession.

## Phase 8: the hosted edition

**Not planned in detail**, as the build plan says. What release one leaves open for it, and what
it leaves settled:

- **Tenancy scheme.** Module subdomains versus per-tenant subdomains, decided deliberately
  ([constraint](identity-and-topology.md#constraint-carried-to-the-hosted-edition)). The routing
  configuration is the single place hosts are named, so either answer is configuration plus a
  per-tenant resolver at the boundary.
- **Storage scale.** Database-per-workspace on one cluster has a ceiling; the hosted edition
  decides between more clusters (the `cluster` table already routes by `cluster_ref`) and a
  different scheme behind the same seam. Pool caching and serial migration become real
  engineering here.
- **Credentials.** Service-owned model credentials through an API adapter; never a customer's CLI
  subscription (idea document). The OpenRouter adapter from phase six is the candidate default.
- **Encryption and keys.** Per-workspace encryption at rest and a key-management design with a
  threat model and a recovery procedure are prerequisites, not additions; the secret store's
  backend protocol is where a managed secret manager plugs in.
- **Billing.** Metadata joins the control plane here (D1, FR 7).
- **Operations.** Backups with point-in-time recovery, replica coordination against one database,
  cross-tenant metrics that leak no tenant data, and abuse controls for any public capture
  endpoint (a separate, limited contract, never the privileged intake API).
- **Provider licensing** for every job source before it is enabled in a public service.
