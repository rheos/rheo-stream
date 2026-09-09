# Confirmation, safety classes, and pipeline presets

**Part of:** the [architecture specification](README.md). Designs against R3, R5, FR 18, FR 24,
FR 25, FR 42, FR 43, FR 45, FR 46, and criteria 19, 57, 58, 60, 61, 64. Fixes the final
confirmation rules R3 outlined and closes idea-document question 17 (preset limits and record
migration).
**Decisions:** A15 (preset versioning). The safety classes themselves are R3, accepted; this
document gives them their mechanism. See the [decision list](README.md#architecture-decisions).

## The six classes and what the dispatcher does with each

Every operation and every tool declares exactly one (FR 24); registration refuses otherwise
([module contract](module-contract.md#operations-tools-events)). The service registry's
dispatcher applies the class before the handler runs:

| Class | Dispatcher behaviour | Audit | Standing grant may cover |
| --- | --- | --- | --- |
| `READ` | Authorization check, run. | No | Yes |
| `DRAFT` | Authorization check, run. The result is a record; nothing leaves. | Yes | Yes |
| `MUTATE` | Authorization check, run inside a unit of work with an audit row. | Yes | Yes |
| `DESTRUCTIVE` | Requires an `approval` in state `approved` bound to this exact call; otherwise returns `approval_required`. Guards rerun at execution. | Yes | Never |
| `EXTERNAL` | As destructive, and the effect is an `external_action` executed by a job with its own outcome record. | Yes | Never |
| `FINANCIAL` | As external, and the approval's `payload_ref` must contain `amount`, `currency`, and `payee_ref`, which the interface restates verbatim at the point of confirmation. | Yes | Never |

Workspace policy may tighten (a workspace may require confirmation for a named mutate
operation via `approvals.confirm_operations`, a list under a `union` floor that can only
grow) and can never loosen (the three upper classes cannot be moved to a standing grant by any
setting; the class-to-behaviour table is code, not configuration).

## The approval record

`core.approval`, one row per confirmation requirement:

| Column | Meaning |
| --- | --- |
| `id uuid` | Returned in the `approval_required` state. |
| `actor_kind`, `actor_id` | Who requested (the actor whose call was gated). |
| `operation_name`, `operation_id` | What. |
| `destination_ref text null` | Recipient or destination: a party reference, a connector destination, the recording sink. Null only for destructive operations on a record, where `subject_ref` is the binding. |
| `subject_ref text null` | The record acted on. |
| `payload_digest bytea` | SHA-256 of the canonical JSON of the operation input as it will execute. |
| `payload_ref` | Where the payload snapshot is held (a `core.approval_payload` row) so the interface can show what is being approved. |
| `purpose text` | From the purpose vocabulary. |
| `window_start`, `window_end` | Execution window. Default length `approvals.default_window_seconds` 900; maximum `approvals.max_window_seconds` 86400, floor `min`. |
| `state` | `pending`, `approved`, `executed`, `expired`, `invalidated`, `refused`, `requires_reapproval`. |
| `approved_by_kind`, `approved_by_id`, `approved_at`, `approved_entry` | Who approved and through which entry (`web` or `cli`; never `mcp`). |
| `executed_at`, `invalidated_reason text null` | |

**The binding tuple** (R3 item 3) is `(actor, workspace, operation_name, destination_ref or
subject_ref, payload_digest, purpose, window)`. Execution recomputes the digest from the payload
it is about to run and compares; a differing byte, a differing destination, or a time outside the
window refuses with `invalid_approval` and records nothing at the destination (criterion 60). The
workspace is implicit in which database the row lives in.

**Who may approve.** An authenticated account holding a role the operation allows, through the
web interface or a `cli` token whose operation set includes `core.approval.approve`. `mcp` tokens
cannot carry that operation ([MCP facade](runtime-and-mcp.md#the-mcp-facade)). Untrusted evidence
never approves: no path reads a payload, a memory, or a message to set `state = approved`
(FR 25, R3 item 8), and criterion 59's instructing text has no operation to reach.

**Flow.**

1. A gated operation is called. The dispatcher creates the approval `pending`, the operation
   record `approval_required`, and returns both ids. Nothing else happens; a headless caller
   gets the state within the deadline and the call ends (criterion 19).
2. A person approves: `core.approval.approve(approval_id)`, a mutate-class operation with its own
   audit row. State `approved`.
3. Execution: for destructive, the dispatcher runs the original operation now, with the approval
   id; for external and financial, it enqueues the `external_action` job. Either path reruns the
   guards first.
4. On success, `executed`; on a guard failure, `refused` with the guard named; on window
   expiry, `expired`.

## Standing grants

| `core.standing_grant` column | Meaning |
| --- | --- |
| `id`, `actor_kind`, `actor_id`, `granted_by_id`, `created_at`, `expires_at`, `revoked_at null` | |
| `classes text[]` | Subset of `{read, draft, mutate}`; any other value is refused at grant time (criterion 19, R3 item 5). |
| `operation_set_id` | A named operation set; the grant covers only those names. |

A standing grant lets a token or session run the listed operations without a per-call
confirmation the workspace would otherwise require. It never satisfies destructive, external, or
financial: the dispatcher does not consult grants for those classes at all.

## Execution guards

Guards are rechecks run at execution time, after approval, before effect (R3 item 4). The core
supplies two and modules add domain guards through the operation declaration.

| Guard | Supplied by | Refuses when |
| --- | --- | --- |
| `ActorPermissionGuard` | core | The approving actor's membership, role, or token no longer permits the operation, or the token is revoked. |
| `WindowGuard` | core | Outside `window_start` to `window_end`. |
| `ContactPermissionGuard` | Leads | `leads.contact_permission.check(destination party, purpose, channel)` fails: no permission, withdrawn, or suppressed (criterion 61). |
| `DestinationGuard` | the connector owning the destination | The destination is not configured, or the connector's credential is unavailable. With no destination configured, `leads_handoff` refuses `unavailable` (criterion 64). |
| `RecordStateGuard` | the owning module | The subject record was deleted or changed revision since approval. |

A refused guard leaves the external action `refused`, the operation `failed` with the guard's
code, and the sink or provider untouched. An earlier approval never overrides a later revocation
because the approval only gates whether execution may *start*; the guards decide whether it may
*proceed*.

## The recording sink and the destructive fixture

Test-harness registrations, never in the production set (criterion 18). The sink is an
external-class operation `test.sink.send` whose handler appends what it would have sent to a
harness table and sends nothing. The fixture is a destructive-class operation `test.fixture.act`
whose handler records the request and deletes nothing. Both exist so the approval binding, the
guards, the headless state, the export of a pending approval, and the deletion cascade's
cancellation of a dependent action have a real gated operation to run against (criteria 19, 21,
60, 61, 65, 67).

## Pipeline presets and their limits

Answers idea-document question 17: what a preset can configure, and how records move when it
changes.

### Entities

All in the `leads` schema.

| Table | Columns | Notes |
| --- | --- | --- |
| `pipeline_preset` | `id uuid`, `name`, `current_version integer`, `created_at` | A named preset. Release one ships one: inbound services. |
| `preset_version` | `preset_id`, `version integer`, `created_at`, `created_by_id`, `note text` | Primary key `(preset_id, version)`. Immutable once created. |
| `preset_stage` | `preset_id`, `version`, `stage_id slug`, `label text`, `ordinal`, `kind text`, `outcome text null` | `kind` in `open`, `terminal`. Terminal stages map to `outcome` in `succeeded`, `lost`, `disqualified`. `stage_id` is stable across versions; `label` is free. |
| `preset_transition` | `preset_id`, `version`, `from_stage_id`, `to_stage_id` | Allowed moves. |
| `preset_requirement` | `preset_id`, `version`, `to_stage_id`, `field text` | Fields that must hold a value before entering `to_stage_id`. Presence only; no expressions. |
| `preset_field` | `preset_id`, `version`, `target text`, `type text`, `required boolean`, `sensitivity text` | Extension fields `ext.<namespace>.<field>` with `type` from `text`, `integer`, `decimal`, `date`, `boolean`, `enum(values)`. |
| `preset_rubric` | `preset_id`, `version`, `rubric_ref text`, `rubric_version integer` | The qualification rubric this version uses. |
| `preset_template` | `preset_id`, `version`, `kind text`, `body text` | Draft templates with named placeholders; `kind` in `followup`, `proposal`. |
| `preset_handoff` | `preset_id`, `version`, `destination_ref text` | From registered destinations; none in release one. |
| `pipeline` | `id uuid`, `preset_id`, `name`, `owner_id`, `created_at` | A working instance. New opportunities enter it at the preset's `current_version`. |

Opportunities and qualifications pin what they were created under:

| Table | Pinned columns |
| --- | --- |
| `leads.opportunity` | `pipeline_id`, `preset_id`, `preset_version`, `stage_id`, `disposition_outcome null`, plus identity, title, owner, timestamps |
| `leads.qualification` | `opportunity_id`, `preset_version`, `rubric_ref`, `rubric_version`, `objective`, `evidence_refs text[]`, `input_revision`, `explanation`, `uncertainty`, `model_id null`, `prompt_version null`, `created_at` |

A qualification is its own record, never a column on the opportunity (criterion 58), and a later
assessment does not replace an earlier one; the newest by `input_revision` is the current view.

### What a preset can configure

Stages, their labels, order, and terminal outcomes; allowed transitions; presence requirements per
transition; extension fields from the closed type list with a sensitivity tier; the rubric
reference and version; draft templates; handoff destinations from the registered set. That is the
whole surface. A preset cannot: run scripts or expressions; write another module's records; add
a core column; change a safety class or a permission; name a runtime, model, or credential; or
define a new purpose. Unusual behaviour goes in a module, as the idea document directs.

### Editing and pinning (FR 43)

Editing a preset creates `preset_version n+1` by copying `n` and applying the change, then sets
`current_version`. Rows of earlier versions are never modified. An opportunity created under
version `n` keeps `preset_version = n`; its stages, transitions, requirements, and field schema
are read from version `n` for as long as it lives (criterion 57). Renaming a stage's label changes
`preset_stage.label` in the new version only, and the opportunity's `stage_id` reference is a
slug that the rename does not touch.

### The migration operation

`leads.pipeline.migrate_version(pipeline_id, opportunity_ids, to_version, stage_map)`, mutate
class, owner only, audited per opportunity:

- `stage_map` maps every `stage_id` in use among the selected opportunities to a `stage_id` in
  `to_version`; a missing entry refuses the whole call naming the stage.
- Extension fields present in the old version and absent in the new are kept on the opportunity
  as `ext.*` values flagged `orphaned = true`, readable and exportable, not writable.
- A field required in the new version and empty on an opportunity does not block the migration;
  the next transition into a stage that requires it does.
- Each migrated opportunity's `preset_version` is updated and an `leads.opportunity.migrated`
  event is published with both versions.

Qualification records are never migrated; they record the version and rubric they were made
under, and a new assessment under the new rubric is a new record.
