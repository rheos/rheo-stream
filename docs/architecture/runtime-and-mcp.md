# Runtime contract, the MCP facade, and the redaction contract

**Part of:** the [architecture specification](README.md). Designs against D4, FR 13, FR 19 to
FR 25, FR 27, and criteria 15 to 20. Closes idea-document question 12 (what reaches a model
provider) and the capability-check half of question 10.
**Decisions:** A9 (runtime contract), A10 (MCP facade), A13 (redaction tiers). See the
[decision list](README.md#architecture-decisions).

## Runtime contract, version 1

The runtime owns model conversation mechanics. Rheo Stream owns identity, authorization, tool
policy, domain data, audit, and durable work state (idea document). The contract is the seam
between the two, in `packages/contracts.runtime`, and every domain service that wants a model
depends on it and on nothing more specific (FR 19, guardrail 4).

### Request binding

A `RuntimeRequest` is built by the core's `runtime` package from a `WorkspaceContext` and an
operation; no module constructs one.

| Field | Meaning |
| --- | --- |
| `operation_id` | The durable operation this run belongs to. Every run is an operation. |
| `actor`, `workspace_id`, `audience` | Copied from the context; the runtime may not change them. |
| `purpose` | From the purpose vocabulary; drives redaction and permission filtering. |
| `task` | The instruction text, as data. Never interpolated into a shell command. |
| `context_items` | List of `ContextItem(ref, tier, text)` already permission-checked and redacted by the context builder. |
| `permitted_tools` | List of tool names. Derived from the actor's operation set intersected with the operation's declared tool needs; never wider than the actor. |
| `output` | `text`, `structured(json_schema)`, or `stream`. |
| `requirements` | Set of capability names the workflow needs (below). |
| `limits` | `deadline_seconds` (default and ceiling `runtime.max_deadline_seconds`, package default 600, floor `min`), `max_iterations` (default 40), `max_output_bytes`. |
| `continuation` | `None`, or the id of a `runtime_session` row the caller may resume. |
| `credential_slot` | A slot name such as `model`. The adapter maps it to a secret reference from its private configuration; the reference never enters the request ([secrets](storage-and-workspaces.md#a4-the-secret-store-fr-13-guardrail-14)). |
| `runtime_id`, `model_id` | Chosen from the workspace's permitted set, itself a subset of the operator's (`runtime.allowed_runtimes`, `runtime.allowed_models`, floor `subset`). Runtime and model are separate settings. |

### Capability discovery (FR 20)

```text
RuntimeAdapter.capabilities() -> RuntimeCapabilities
  tool_calling: bool
  structured_output: bool
  streaming: bool
  continuation: bool
  cancellation: bool
  usage_reporting: "exact" | "estimate" | "none"
  isolation: "enforced" | "advisory"      # can the adapter bound filesystem and network access
```

`RuntimeGate.check(request.requirements, adapter.capabilities())` runs before the adapter is
invoked and refuses with `UnmetCapability(name)` naming the first unmet requirement (criterion
15). A workflow that requires `isolation = enforced` is refused on an adapter that reports
`advisory`; that is the "CLI without enforceable isolation is rejected before the workflow
starts" case in the idea document's scenario table.

### Normalized outcomes

The adapter yields `RuntimeEvent`s and ends with exactly one terminal event:

| Event | Fields | Notes |
| --- | --- | --- |
| `progress` | `text`, `fraction` | Forwarded to the operation record. |
| `tool_call` | `tool`, `arguments_digest` | Arguments are not stored in the runtime request record; the tool's own audit row carries the request digest. |
| `tool_result` | `tool`, `outcome` | `ok`, `refused`, `approval_required(approval_id)`, `error`. |
| `usage` | `input_tokens`, `output_tokens`, `cost`, `kind` | `kind` is `exact` or `estimate`, kept separate. |
| `final_output` | `text` or `structured` | Structured output is validated client-side against the request's schema; a mismatch is `failure(output_invalid)`. |
| `failure` | `kind`, `detail` | Terminal. |
| `cancelled` | | Terminal. |
| `approval_required` | `approval_id` | Terminal for this run: the run stops, the operation goes `approval_required`, and a later run resumes with `continuation` after approval. |

Failure kinds, fixed: `executable_unavailable`, `credential_invalid`, `tool_denied`,
`deadline_exceeded`, `stream_truncated`, `output_invalid`, `iteration_limit`, `runtime_error`.
The five criterion 16 induces are the first five. Each maps to an operation `failed` with the kind
as `error_code`, within the deadline, with no `succeeded` possible: the operation's
`terminal_check_kind` for a run is `handler_returned` only when a `final_output` was received, so
"a text reply is not proof a domain action succeeded" is enforced by the domain operation that
consumed the output checking its own record, not by the runtime.

### Native session handles

| `core.runtime_session` column | Meaning |
| --- | --- |
| `id uuid` | The handle the core hands out as `continuation`. |
| `runtime_id`, `credential_scope text`, `actor_kind`, `actor_id`, `audience_kind`, `audience_id` | The binding. A lookup must supply all of them; there is no "latest". |
| `native_handle text` | The adapter's own session id, opaque to the core. |
| `created_at`, `last_used_at`, `expires_at` | Sessions expire with `runtime.session_ttl_hours` (default 72). |

Switching runtimes starts a new native session with the selected authorized context; nothing
is carried across adapters. Completed effects are never replayed because effects are external
actions with their own records, not part of the transcript.

### What the core records about a run

| `core.runtime_request` column | Meaning |
| --- | --- |
| `id`, `operation_id`, `runtime_id`, `model_id`, `purpose` | |
| `context_refs text[]`, `context_digest bytea` | Which references were sent and a digest of the redacted text. Not the text. |
| `permitted_tools text[]`, `requirements text[]`, `limits` columns | |
| `terminal_event text`, `failure_kind null`, `usage_*` columns, `usage_kind` | |
| `started_at`, `ended_at` | |

Transcripts (model output and tool result summaries) go to `core.runtime_transcript` with
`retention_until` set from `runtime.transcript_retention_days` (default 90, floor `min`); the
retention sweep job removes them. No secret value or reference, no tool argument, and no raw
context text is in either table (criterion 17).

## `ClaudeCliRuntime`

The first adapter, in `runtimes/claude_cli`. It spawns the local `claude` executable in print mode
and uses that program's own agent loop.

| Concern | Design |
| --- | --- |
| Executable | `runtime.claude_cli.executable`, a deployment setting (absolute path); never from a workspace setting or a request. Missing or non-executable at spawn is `executable_unavailable`. |
| Arguments | A fixed list: `-p`, `--output-format stream-json`, `--verbose`, `--max-turns <max_iterations>`, `--mcp-config <generated file>`, `--allowedTools <permitted tool names>`, `--resume <native_handle>` when continuing. No argument is built from task text. |
| Task input | Written to the child's stdin as data. |
| Tools | The adapter writes a per-run MCP configuration file pointing at this deployment's MCP endpoint with a **run-scoped token**: an `access_token` of kind `mcp`, `issued_from = runtime`, whose operation set is exactly `permitted_tools`, whose `purpose` is the run's, valid for the run's deadline, revoked at run end. The permitted set is therefore enforced by the facade on every call, not only by the CLI's allow list, and tool outputs are redacted under the run's purpose. |
| Working directory | `<data_root>/workspaces/<id>/runs/<operation_id>/`, created empty, removed after the run. The parent development workspace is never the working directory. |
| Configuration directory | `<data_root>/workspaces/<id>/runtime/claude-cli/`, passed as the executable's configuration-directory variable (`CLAUDE_CONFIG_DIR`) and as `HOME`, so that everything the executable writes by convention (its session files among them) lands under the data root and nowhere else. It is per workspace, not per run, because `continuation` resumes a native session from a later operation; a per-run directory would lose it. The retention sweep removes files in it older than `runtime.transcript_retention_days`. |
| Environment | An allowlist: locale, path, the two directory variables above, and the variables the executable needs for its own credential; the model credential comes from the `credential_slot` mapping in the adapter's private configuration, resolved through the adapter's secret scope, and is passed in the child environment only. |
| Isolation | Reports `advisory` in release one: the adapter constrains the working directory and the tool allow list but cannot enforce a filesystem or network sandbox on its own. Workflows requiring `enforced` are refused on it until an operator-provided sandbox is configured. |
| Deadline | A timer kills the process group at `deadline_seconds`; `deadline_exceeded`. |
| Stream parsing | One JSON object per line. A process exit with no terminal `result` object is `stream_truncated`. An authentication error object is `credential_invalid`. A tool refusal from the facade surfaces as `tool_result(refused)` and, if the run cannot proceed, `tool_denied`. |
| Continuation | The `session_id` in the stream is stored as `native_handle`; resumed only through the bound lookup. The phase-one runtime test starts a run, ends it, and resumes it from a second operation with `continuation`, which is what proves the per-workspace configuration directory carries the native session across runs. |
| Usage | Reported as `exact` when the result object carries it. |

The adapter never opens a database, never sees a `WorkspaceContext`, and never sees a secret
reference outside its own configuration.

## The OpenRouter adapter (phase six, shape only)

Recorded so the contract above is known to fit a structurally different adapter. It calls the
provider's API and supplies its own loop: send the task and context, receive tool-call requests,
dispatch each through the same facade with the same run-scoped token, return results, repeat to
`max_iterations`. It reports `tool_calling`, `structured_output`, `streaming`, `cancellation`,
and `usage_reporting = exact`; `continuation` is implemented by the core storing the message list
under the `runtime_session`, and `isolation = enforced` because nothing runs locally. Model and
provider allow lists, required-parameter enforcement, and a fallback policy that cannot widen who
receives private context are adapter settings under the operator floor. It changes no domain
module, which is the point of the second adapter (D4).

## The embedding provider

Embeddings are model-provider calls and sit behind the same kind of seam:
`EmbeddingProvider.embed(texts) -> vectors` with `model_id` and `dimensions` reported. The memory
module's dense strategy depends on the protocol; release one ships one implementation over an
HTTP embeddings API selected by `recallatron.embedding.provider`, with the credential in a slot.
Inputs pass through the redaction contract with purpose `internal_analysis`.

## The MCP facade

`apps/mcp`, served by the `core` process over streamable HTTP at the `mcp` surface (subdomain
mode `mcp.<base>/`; path mode `/mcp`). Bearer token only; cookies are ignored on this surface.

**Session resolution.** The token resolves to an `access_token` row, and the boundary builds the
`WorkspaceContext` from it: workspace, actor `token`, role from the token's account membership,
`operation_set` from the token, `audience = token`. A malformed, expired, revoked, or wrong-kind
token is refused at the transport with a distinct state and no tool runs (criterion 9).

**Listing.** `tools/list` returns the registered tools whose operation is in the token's operation
set and whose module is enabled in the workspace, filtered again on every `tools/call`, so a tool
listed before a revocation is refused after it (idea document: discovery grants nothing).

**Signature conventions.**

- Name: `<module>_<verb>[_<noun>]`; core tools use `workspace_`, `operations_`, `audit_`.
- Input: the operation's input model, with the reserved names forbidden at registration
  (criterion 6). Record references are strings in the documented form; a reference from another
  workspace resolves to nothing and the call fails `not_found`.
- Class: declared on the tool and required to equal the operation's ([module contract](module-contract.md#operations-tools-events)).
- Output: the operation's output model, rendered by the facade through the owning module's
  `render_for_model` under the [redaction tiers](#tiers) with the token's `purpose`
  (`internal_analysis` when the token carries none), so a tool never returns a `restricted`
  field, a contact value, or a secret reference to a model, whatever the operation returns to a
  person. A destructive, external, or financial call without an approval returns
  `approval_required` with the approval id and the operation id, distinct from success and from
  error (criterion 19).
- Long-running operations return `{ operation_id, state }` and the caller polls `operations_get`.

**No SQL, no repository.** A tool has no handler; `apps/mcp` imports the service registry and the
contracts and nothing from `rheo_core.storage` or any driver (criterion 20).

**Approvals are never given through MCP.** The token kinds differ: `mcp` tokens cannot carry
`core.approval.*` in their operation set (issuance refuses), so a model cannot approve what it
proposed. Approval happens in the web interface or through a `cli` token in a person's hands
(R3 item 8). A tool may *request* an approval on behalf of the actor, which is what
`approval_required` is.

**Release-one tool set.** Each names one operation and restates its class and roles; the
operation tables in the module documents are authoritative.

| Phase | Tool | Class | Roles |
| --- | --- | --- | --- |
| One (core) | `workspace_status`, `operations_get`, `operations_list` | read | owner, member |
| One (core) | `audit_list` | read | owner |
| Two (memory) | `recallatron_recall` | read | owner, member |
| Two (memory) | `recallatron_remember`, `recallatron_derive`, `recallatron_correct`, `recallatron_supersede` | mutate | owner, member |
| Two (memory) | `recallatron_forget` | destructive | owner, member |
| Three (relationships) | `relationships_find_party`, `relationships_get_party`, `relationships_list_review` | read | owner, member |
| Three (relationships) | `relationships_merge_parties`, `relationships_unmerge`, `relationships_resolve_review` | mutate | owner, member |
| Three (relationships) | `relationships_delete_party` | destructive | owner |
| Three (leads) | `leads_search`, `leads_list`, `leads_get`, `leads_get_handoff` | read | owner, member |
| Three (leads) | `leads_connection_health` | read | owner |
| Three (leads) | `leads_capture`, `leads_update`, `leads_qualify`, `leads_transition` | mutate | owner, member |
| Three (leads) | `leads_handoff` | mutate; writes the handoff record and returns `unavailable` with no destination (criterion 64) | owner, member |
| Three (leads) | `leads_prepare_followup` | draft | owner, member |
| Three (leads) | `leads_delete` | destructive | owner |

No tool in the production set is external or financial class. The recording sink and the
destructive fixture are test-harness registrations, never in the production set (criterion 18);
the sink is release one's only external-class operation anywhere.

## The redaction contract

What leaves the deployment for a model provider, and what does not. FR 13 and FR 27 fix the
boundary; this is the operational rule.

### Tiers

Every field of every record type is in one tier, declared in the owning module's manifest
(`sensitivity`):

| Tier | Contents | Sent to a model |
| --- | --- | --- |
| `public` | Titles, stage labels, notes the workspace wrote for itself, message bodies the sender addressed to the workspace, qualification explanations | Yes, when the caller may read the record. |
| `internal` | Party display names, organization names, opportunity value estimates, dates | Yes for purposes the workspace enables (`redaction.internal_purposes`, default `respond, follow_up, internal_analysis`), no otherwise. |
| `restricted` | Contact point values (email, phone, address), permission records, member credentials, every secret reference, other members' personal material, raw delivery payloads | Never by default. `redaction.contact_points_to_model` (`and` floor, package default false) may allow contact point values for `respond`; nothing enables the rest. |

Secrets are not a tier; they cannot enter a context item because no domain service can resolve
one. The tier for secrets exists so that a *reference* string in a record is also withheld.

### The context builder

`core.runtime.build_context(ctx, purpose, refs)`: resolve each reference under `ctx`, drop those
not readable, obtain memory items only through `recallatron.memory.recall` with the same
`purpose` (which applies the audience, purpose, link, and contact-permission filters,
[memory](memory.md#retrieval-fr-27-fr-30-criteria-27-and-31); FR 27), render each readable
record through its module's `render_for_model(record, tier_policy)` which omits fields above the
allowed tier, and cap total bytes at `runtime.max_context_bytes` (package default 200000, floor
`min`). Restricted values that appear inside free text (an email address inside a message body)
are masked by pattern before sending unless the `respond` allowance is on. Derived memories carry
the intersection of their sources' audiences and purposes, so the filter on a memory is never
looser than on what it was made from (criterion 28).

### Retention and control

- The core stores context references and a digest, and transcripts for the retention period.
  The provider's copy is outside the deployment's control, and the documentation says so rather
  than claiming otherwise. The CLI's local files are directed under the data root by the
  per-workspace configuration directory and swept with the transcripts; the contract claims only
  that the deployment removes what it can see, and the phase-one runtime test (a run resumed
  from a second operation) is where a builder verifies the executable writes nowhere else
  before the claim is widened.
- The workspace owner controls the internal-purpose list and the contact-point allowance within
  the operator's floor, the runtime and model allow lists within the operator's, and transcript
  retention within the operator's maximum.
- A record type can be marked `never_to_model` at the workspace level per module
  (`<module>.redaction.exclude_types`), which the builder honours before tiering.
