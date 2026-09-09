# Module contract, version 1

**Part of:** the [architecture specification](README.md). Designs against D5, D11, FR 9, FR 11,
FR 24, FR 26, FR 52, and criteria 24, 25, 26, 33, 54, 66. Closes idea-document question 21 for
release one and writes the full lifecycle on paper as D5 requires.
**Decision:** A6. See the [decision list](README.md#architecture-decisions).

## The shape in one paragraph

A module is an ordinary Python distribution that exposes one `Module` object through the
`rheo.modules` packaging entry-point group. The object carries a **manifest** (a typed,
validated model in `packages/contracts`) and a **register** function that the core calls once per
process start to attach the module's operations, tools, event handlers, jobs, schedules,
resolvers, and web contribution to the global registry. Host-installed availability is "the
distribution is importable"; per-workspace activation is a row in `core.module_state`. The core
imports no module; a module imports the core and the contracts and, if it declares one, another
module's public contract package. That is the whole mechanism; the rest of this document is what
the manifest says and what the lifecycle does.

## The manifest

`rheo_contracts.ModuleManifest`, a pydantic model. Every field is required unless marked
optional; a missing field fails validation at install with the field named (criterion 25).

| Field | Type | Meaning |
| --- | --- | --- |
| `module_id` | slug | Stable identity; the namespace for everything the module registers. |
| `package_version` | semantic version | The distribution's version. |
| `core_contract_versions` | list of integers | Contract major versions this module is written against. Release one publishes contract version 1. |
| `dependencies` | list of `Dependency(module_id, version_range, optional)` | Required and optional modules. Cycles and unsatisfiable ranges are rejected at install. |
| `record_types` | list of `RecordType` | See [owned record types](#owned-record-types). |
| `storage` | `StorageDeclaration(schema_name, migrations_path, required_extensions)` | `schema_name` must equal `module_id`. `required_extensions` names Postgres extensions the migrations need. |
| `configuration_schema` | a pydantic model class | The module's settings keys with scope and floor annotations ([configuration](storage-and-workspaces.md#a5-configuration-precedence-and-the-policy-floor-fr-12)). Keys must start with `<module_id>.`. |
| `operations` | list of `OperationDeclaration` | Name, safety class, input and output models, idempotency, audit subject, guards. See [operations](#operations-tools-events). |
| `tools` | list of `ToolDeclaration` | MCP tools, each naming an operation and restating its class. |
| `events` | list of `EventDeclaration(type, schema_version, data_model)` | Events the module publishes. |
| `subscriptions` | list of `Subscription(event_type, consumer_id, replay_safe)` | Events the module consumes. |
| `jobs` | list of `JobKind(name, handler, max_attempts, cancellable)` | Background work kinds. |
| `schedules` | list of `Schedule(name, job_kind, cron, enabled_by_default)` | Per-workspace schedules created at enable. |
| `resolvers` | mapping of record type to resolver | One per owned record type ([identifiers](identifiers.md#resolution-under-permission)). |
| `deletion_participants` | list of `DeletionParticipant(record_types, handler)` | Hooks the [deletion coordinator](deletion-export-migration.md#the-cascade) calls. |
| `export` | `ExportDeclaration(format_version, schema_path, exporter, importer)` | The module's versioned export format. |
| `web` | optional `WebContribution(package_name, navigation, routes, record_views, forms, search_providers)` | The TypeScript contribution composed into `apps/web`. |
| `agent_guidance` | optional path | Text a runtime may include as tool guidance. It describes use; it grants nothing (idea document). |
| `secret_scopes` | list of scope prefixes | Empty for domain modules in release one. Only components that present secrets declare any. |
| `connector_bindings` | list of `ConnectorBinding(transport, service_operation)` | Which of the module's operations a transport connector may call. Leads declares three. |
| `health_checks` | list of callables | Run by `rheo doctor` and the workspace status operation. |
| `contract_tests` | path | The module's behavioural suite entry, run by the install path in test profile and by CI. |
| `sensitivity` | mapping of record type to field tiers | Which fields are `public`, `internal`, `restricted` for the [redaction contract](runtime-and-mcp.md#the-redaction-contract). |

The manifest is code, not a sidecar file: one source of truth, type-checked, no cross-validation
between two declarations. The export `schema_path` is the one static file: a JSON Schema for the
module's export records, so an export can be validated by anything that has the package installed,
whether or not the module is enabled anywhere.

### Owned record types

```text
RecordType
  name: slug                      # "opportunity"; the reference form is "leads.opportunity"
  table: str                      # "leads.opportunity"; must be in the module's schema
  deletable: bool                 # true for the three R5 types and any type a module chooses
  exportable: bool
  audience_field: str | None      # column holding the record's audience, when records carry one
```

A record type appears in exactly one manifest. Two modules declaring the same
`<module_id>.<name>` cannot happen because the module id is the prefix; two modules declaring a
table outside their schema fail install.

### Operations, tools, events

```text
OperationDeclaration
  name: "<module_id>.<noun>.<verb>"
  safety_class: SafetyClass                 # exactly one of the six (R3, FR 24)
  input: type[BaseModel]                    # may not declare workspace_id, actor_id, tenant, database, schema, connection fields
  output: type[BaseModel]
  handler: Callable[[WorkspaceContext, UnitOfWork, input], output]
  roles: set[Role]                          # who may call; default {owner, member}
  idempotency: Idempotency                  # NONE | NATURAL | KEYED(field_name)
  audit: AuditSpec | None                   # required unless safety_class is READ
  guards: list[ExecutionGuard]              # rechecks run at execution for DESTRUCTIVE, EXTERNAL, FINANCIAL
  long_running: bool                        # returns an operation id and runs as a job
```

Registration rules the core enforces at startup (criterion 18, criterion 14, criterion 6):

- No `safety_class`: refused, naming the operation.
- Class above `READ` with `audit = None`: refused, naming the operation.
- Class in `DESTRUCTIVE`, `EXTERNAL`, `FINANCIAL` with no `guards`: refused. The core supplies
  `ActorPermissionGuard` and every module in that class adds the domain guards it needs
  ([confirmation](confirmation-and-safety.md#execution-guards)).
- An input model with a reserved field name (`workspace_id`, `workspace`, `actor_id`, `actor`,
  `tenant_id`, `database`, `schema`, `connection_string`, `dsn`, `sql`, `table_name`,
  `statement`): refused. The last three make criterion 20's "accepts no SQL, table name, or query
  fragment" a mechanical check over the registered input models.
- `KEYED` idempotency names a field of the input model; the core stores
  `(operation_name, key)` in `core.audit_record` and returns the recorded output on a repeat.

```text
ToolDeclaration
  name: "<module_id>_<verb>[_<noun>]"       # MCP-safe characters only
  operation: str                            # the operation it calls; nothing else
  safety_class: SafetyClass                 # must equal the operation's, or registration fails
  description: str
  input_schema: derived from the operation's input model
```

A tool is a name and a description over an operation. It has no handler of its own, so it cannot
reach storage except through the operation (FR 22, criterion 20).

```text
EventDeclaration
  type: "<module_id>.<record_type>.<verb>"
  schema_version: int
  data: type[BaseModel]                     # references and small facts, no record copies
```

Event and subscription shapes, delivery, and replay are in [intake and events](intake-and-events.md#events-and-the-outbox-fr-15).

### Extension points

The `web` contribution is a TypeScript package under the module directory (`modules/leads/web`)
that the web application composes at build time. It exports:

| Export | Shape | Filtered by |
| --- | --- | --- |
| `navigation` | list of `{ id, label, surface, path, roles }` | enabled modules for the session's workspace, role |
| `routes` | a route tree mounted under the module's surface ([topology](identity-and-topology.md#the-routing-table)) | enabled modules |
| `recordViews` | `{ recordType, component }` | permission through the record resolver |
| `forms` | `{ operation, component }` for operations that need a bespoke form | operation set, role |
| `searchProviders` | `{ id, operation }` naming a read-class search operation | enabled modules |

Composition is a generated file (`apps/web/src/modules.generated.ts`) produced from the installed
distributions' manifests by `rheo web compose`; it is never hand-edited. Enablement is applied at
runtime from the core's `workspace_status` response, so a module that is installed on the host and
not enabled in the workspace contributes nothing visible. A build is required to add a module's
screens, which is the "code installation may require a build or restart" the idea document allows.

## Discovery and registration

At process start, in `core` and `worker` alike:

1. `importlib.metadata.entry_points(group="rheo.modules")` lists the host-installed modules. The
   deployment setting `modules.installed` (a list of module ids, default: every discovered module)
   selects which of them the host loads; a discovered module not in the list is ignored, so a
   private module's presence on disk does not activate it (workspace-layout rule).
2. Each selected module's manifest is validated: schema, namespace prefixes, dependency ranges
   against the other selected modules, contract version against the running core.
3. Dependencies are topologically sorted; a cycle or an unsatisfied required dependency fails
   startup naming both modules.
4. `register(registry)` runs per module in that order. Every registration is checked against the
   manifest: an operation registered in code that the manifest does not declare, or declared and
   not registered, fails startup.
5. The production-profile assertion runs (criterion 18): under `RHEO_PROFILE=production` the
   registry must contain no item whose `origin` is `test_harness` and no operation in the
   `EXTERNAL` or `FINANCIAL` classes. Test fixtures register with `origin=test_harness` through a
   harness-only entry point that the production profile does not load.

The registry is global to the process. Per-workspace activation is applied at every boundary by
`WorkspaceContext.enabled_modules`, so a tool listing, a route resolution, an event fan-out, a
job dispatch, and a schedule tick each filter by the workspace they are acting for.

## Lifecycle

Per workspace, in `core.module_state.state`:

```text
(absent) --install--> installed --enable--> enabled
                                    ^          |
                                    +--re-enable--+--disable--> disabled --remove--> removed --purge--> (absent, data gone)
                                                                   |
                                                                   +--restore--> installed (from an export)
```

### Install and enable (release one, in code)

**Install** (`core.module.install`, owner or operator, class mutate, long-running):

1. The module must be host-loaded. Otherwise refuse with `module_unavailable`.
2. Dependencies must be installed in this workspace at a satisfying version; optional ones may be
   absent and are recorded as absent.
3. `required_extensions` are created in the workspace database (`CREATE EXTENSION IF NOT
   EXISTS`); failure names the extension and stops before any migration.
4. The module's schema is created and its migration chain applied under the workspace's advisory
   lock; each applied step writes `core.module_schema_version`.
5. `core.module_state` gets the row `installed` with the package version.
6. The module's `contract_tests` run when the profile is `test`; in other profiles the health
   checks run.
7. Configuration keys from the module's schema become settable; none are required to enable.

**Enable** (`core.module.enable`, owner or operator, class mutate):

1. State must be `installed` or `disabled`.
2. Required dependencies must be `enabled`.
3. Settings keys the module's schema marks `explicit_per_workspace` are written as rows from
   their package defaults (FR 29's retention setting; criterion 30). Schedules declared
   `enabled_by_default` are created in `core.schedule` for this workspace.
4. State becomes `enabled`; from the next request, the workspace's `enabled_modules` includes it,
   and its tools, routes, navigation, subscriptions, and jobs are live for that workspace.

The memory module's install and enable is criterion 24's test: no core file changes, and the
workspace status operation reports the version and schema version afterward. Relationships and
Leads install the same way in phase three.

### Upgrade, disable, re-enable, remove, purge, restore (on paper, D5)

Written now so a builder in the later milestone has a contract, not a blank page. None of it is
release-one code, and no release-one path depends on it.

| Operation | Contract |
| --- | --- |
| **Upgrade** | The host loads the new package version. Per workspace: check `core_contract_versions` and dependency ranges; run the migration chain from the recorded schema version; a migration marked `destructive` requires an export newer than the upgrade's first attempt; on success update `module_state.package_version`. A workspace that fails stays on the old schema version and goes `unavailable` for that module only (its tools and routes refuse with `module_unavailable`) while the rest of the workspace serves. |
| **Disable** | Block new operations of the module (refused `module_disabled`); mark schedules paused; stop fanning new events to its consumers; cancel or drain its queued jobs (each job kind's `cancellable` flag decides which); remove its tool and navigation contributions from the next listing; invalidate cached tool lists for open MCP sessions by bumping the workspace's registration epoch, which every session compares on each call. Running jobs finish or fail through the ordinary operation path; already-dispatched external actions reconcile through `external_action` and are never pretended reversed. Data untouched. |
| **Re-enable** | Same checks as enable. Schedules resume from now, not from where they paused. Events fanned out while disabled were never delivered to the module (fan-out is at write time), so there is no catch-up and therefore no replay of completed external effects. |
| **Remove** | Refuse while a required dependent is enabled or installed, naming it. Check unresolved operations and external actions owned by the module; refuse while any exists. Produce a workspace export that includes the module's records (retained export). Revoke module-owned connector bindings and secret references. State `removed`; the schema and its data remain, readable through the record resolver as `state = unavailable`. |
| **Purge** | Destructive class, per-action confirmation. Requires state `removed` and a retained export newer than the removal. Runs the deletion coordinator for every deletable record type the module owns (so derived memories, queued actions, and held exports cascade under the R5 rules), then `DROP SCHEMA <module> CASCADE`, then deletes `module_state` and `module_schema_version` rows. |
| **Restore** | From an export whose manifest lists the module at a version the host can load: install at that version, then import through the module's `importer`. Pending approvals inside the import are written `requires_reapproval` ([export and restore](deletion-export-migration.md#export-and-restore-fr-52)). |

Host-level package removal is a separate operator concern: `rheo module hosts <id>` lists every
workspace still in a state other than `absent` for the module, and the operator removes those
first.

## Capability and version compatibility

- **Contract version.** `packages/contracts` carries `CONTRACT_VERSION = 1`. A breaking change
  to any model in it increments the major; a module lists the majors it supports. The core loads
  a module only for a listed major.
- **Module version.** Semantic. Dependency ranges use the usual caret and tilde forms. A
  dependency on a module's *behaviour* is a dependency on its package version, because release
  one has no separate capability registry (the requirements keep it out of scope); the idea
  document's "capabilities as versioned semantic contracts" arrives with the framework-proof
  phase as named capability declarations layered over the same manifest.
- **Replacement providers.** Nothing in release one replaces a module with another
  implementation of the same contract. When that arrives, the mechanism is a manifest field
  `provides: [capability@version]` and a dependency form that names a capability rather than a
  module; both are additive to this manifest.

## Proving the boundary by absence

Criteria 33 and 66 require the phase suites to pass in a workspace where the memory module was
never installed. Structurally that holds because:

- `rheo_core` and `rheo_contracts` depend on no module distribution (an import-graph check in
  CI).
- The composition root reads `modules.installed` from configuration; the test profile for the
  no-memory run sets it to `relationships, leads`.
- `leads` declares `recallatron` as an optional dependency and calls it only through
  `ctx.enabled_modules` checks around a registered operation name, never an import.
- Event fan-out at write time consults the workspace's enabled consumers, so an event nobody
  subscribes to is written to the outbox with zero deliveries and is complete on commit.

The same three facts are what make a synthetic specialist module in phase seven a manifest and a
distribution, with no change to the core.
