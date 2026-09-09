# Intake, events, durable work, and audit

**Part of:** the [architecture specification](README.md). Designs against FR 15 to FR 18,
FR 31 to FR 39, FR 46, R2, R4, and criteria 11 to 14 and 38 to 49. Answers idea-document question
6 (event schemas, ordering, retry limits, replay) and fixes the intake contract's shapes.
**Decisions:** A7 (intake lives in Leads; transports are connectors), A8 (outbox, envelope,
worker, audit shapes). See the [decision list](README.md#architecture-decisions).

## Part one: the intake contract

### Who owns what

Intake is the Leads module's front half. Connections, mappings, routing rules, funnels, receipts,
and observations are `leads.*` record types in the `leads` schema. The three release-one
transports are **connectors**: thin adapters in `connectors/` that authenticate a delivery, turn
it into a `Delivery` value, and call `leads.intake.accept_delivery`. A connector owns transport
and translation; it holds no domain rule (connectors README). The webhook receiver's HTTP route is
registered by the Leads module under its `connector_bindings`, on the `api` surface.

The requirements' "generic intake" is generic because the contract below has no provider branch:
a funnel is a mapping plus routing rules, and two unrelated funnels (criterion 55) are two
mappings against one schema.

### Entities

All in the `leads` schema. Every table has `id uuid` (UUIDv7) unless noted.

| Table | Columns | Notes |
| --- | --- | --- |
| `funnel` | `name text`, `description text`, `created_at`, `archived_at null` | Acquisition context: a site, an event, a referral programme. |
| `campaign` | `funnel_id`, `name text`, `created_at`, `archived_at null` | Optional refinement of a funnel. |
| `intake_connection` | `name`, `transport text`, `source_namespace text unique`, `mapping_id`, `mapping_version integer`, `funnel_id`, `campaign_id null`, `priority integer`, `subject_authenticated boolean`, `email_verified boolean`, `signing_secret_ref text null`, `previous_secret_ref text null`, `previous_valid_until timestamptz null`, `state text`, `created_at`, `revoked_at null` | `transport` in `webhook`, `import`, `manual`. `source_namespace` is a URI (`urn:rheo:connection:<uuid>`) used as the CloudEvents `source`. `subject_authenticated` and `email_verified` are the operator's declaration of what this source proves, which R4 needs. |
| `connection_health` | `connection_id pk`, `last_accepted_at`, `last_processed_at`, `pending_count`, `unresolved_failures integer`, `last_error text null`, `lag_seconds integer` | Maintained by the intake worker; read by `leads.connection.health` (FR 38). |
| `field_mapping` | `id`, `version integer`, `name`, `source_kind text`, `state text` | `source_kind` in `json`, `csv`. Primary key `(id, version)`. Versions are immutable once a receipt pins them. |
| `field_mapping_identity` | `mapping_id`, `version`, `event_id_path`, `occurred_at_path`, `subject_id_path null`, `verified_email_path null` | Where identity lives in a payload. Paths are JSON Pointers for JSON, column names for CSV. |
| `field_mapping_rule` | `mapping_id`, `version`, `target text`, `source_path text`, `transform text null`, `transform_arg text null`, `required boolean`, `clear_on_null boolean` | `target` is a core fact name or `ext.<namespace>.<field>`. `transform` from a closed set: `trim`, `lower`, `email_normalize`, `phone_normalize`, `datetime(format)`, `const(value)`. |
| `routing_rule` | `id`, `connection_id`, `ordinal integer`, `action text`, `pipeline_id null`, `enabled boolean` | `action` in `create_opportunity`, `attach_to_open_opportunity`, `record_only`. First enabled match by `ordinal` wins; no match means `record_only`. |
| `routing_condition` | `rule_id`, `field text`, `op text`, `value text null` | All conditions of a rule must hold. `op` in `present`, `absent`, `equals`, `contains`. |
| `delivery_receipt` | `id`, `connection_id`, `source_event_id text`, `content_digest bytea`, `transport text`, `received_at`, `source_occurred_at null`, `mapping_id`, `mapping_version`, `state text`, `state_detail text null`, `processed_at null` | **Unique `(connection_id, source_event_id)`.** `state` in `pending`, `processed`, `refused`, `duplicate`. The receipt survives observation deletion (R5). |
| `delivery_payload` | `receipt_id pk`, `body bytea`, `content_type text`, `byte_length integer` | The bounded source copy (FR 36). Deleted with the observation; the receipt's digest remains. |
| `delivery_conflict` | `id`, `receipt_id`, `content_digest bytea`, `received_at`, `body bytea`, `resolved_at null`, `resolution text null` | A re-delivery with a different digest, or any re-delivery of a deleted observation's event (FR 34, criterion 65). |
| `observation` | `id`, `receipt_id unique`, `connection_id`, `funnel_id`, `campaign_id null`, `transport text`, `source_event_id text`, `external_subject_id text null`, `verified_email text null`, `source_occurred_at`, `received_at`, `mapping_version integer`, `completeness integer`, `party_ref text null`, `created_at` | The normalized evidence record (FR 39). `party_ref` is a record reference into `relationships`, nulled on party deletion. `verified_email` is set only when the connection declares `email_verified`. |
| `observation_field` | `observation_id`, `target text`, `value_kind text`, `value_text text null`, `source_path text`, `transform text null`, `mapping_version integer` | Per-field provenance (FR 36). `value_kind` in `value`, `cleared`. Primary key `(observation_id, target)`. |
| `import_batch` | `id`, `connection_id`, `file_ref`, `row_count`, `accepted`, `refused`, `state`, `created_at` | One per CSV or JSON import. |

### The observation envelope

The normalized envelope every transport produces and every consumer of intake events sees. It is
CloudEvents-compatible in the attributes that matter and carries Rheo-specific extensions in
`data`:

| Attribute | Source | Notes |
| --- | --- | --- |
| `specversion` | constant `1.0` | |
| `source` | the connection's `source_namespace` | Server-assigned; never the sender's claim. |
| `id` | the source event identifier | From `event_id_path`, else the `X-Rheo-Event-Id` header, else the SHA-256 of the body. Event identity is `(source, id)`, distinct from subject identity. |
| `type` | `leads.delivery.received` | |
| `time` | source occurrence time from `occurred_at_path`, else receipt time | Both are stored; `time` is the source's. |
| `subject` | the external subject id when the mapping yields one | Subject identity, separate from event identity. |
| `datacontenttype` | `application/json` | |
| `data.transport` | `webhook`, `import`, `manual` | Delivery transport (FR 36). |
| `data.funnel_ref`, `data.campaign_ref` | resolved from the connection, or chosen at manual capture | Acquisition attribution, stored in columns distinct from transport (criterion 46). |
| `data.facts` | list of `{ target, value_kind, value, source_path, transform }` | What the mapping produced. |
| `data.completeness` | count of `value` facts | Used by field derivation. |
| `data.payload_ref` | the receipt id | The bounded source copy is reachable, not embedded. |
| `data.permission_evidence` | list of `{ purpose, disclosure_version, path }` | Contact-permission evidence the mapping was told to look for (FR 46). Evidence, not a permission record. |

Authenticated workspace context is not in the envelope. It is carried by the receipt's connection
and by the delivery record's context, so a payload that claims a tenant, a destination, or a
permission set (criterion 41) is preserved inside `delivery_payload` as evidence and read for
nothing else.

The core fact vocabulary, closed in release one and extended only through `ext.*` (FR 44):
`person.name`, `person.email`, `person.phone`, `organization.name`, `organization.domain`,
`subject`, `message`, `interest`, `source_url`, `locale`, `value.amount`, `value.currency`,
`value.basis`. Extension targets are validated against the pipeline's declared extension fields
([confirmation and safety](confirmation-and-safety.md#pipeline-presets-and-their-limits)); an
unknown target refuses the mapping version at save time, not at delivery time.

### Acceptance: receipt, dedup, conflict, acknowledgement

`leads.intake.accept_delivery(ctx, delivery)` runs in one transaction:

1. **Bound.** `byte_length > intake.max_payload_bytes` (default 262144, operator floor `min`)
   refuses with `payload_too_large` and stores nothing.
2. **Connection.** Must be `active` and belong to `ctx`'s workspace; the receiver built `ctx`
   from the connection's credential, so this is a consistency check, not a lookup by claim.
3. **Insert receipt** with `ON CONFLICT (connection_id, source_event_id) DO NOTHING`.
   - Inserted: continue to step 4.
   - Not inserted, existing digest equals this digest: mark nothing, return `duplicate`. The
     transport acknowledges as it would a fresh accept, because the sender's retry succeeded
     the first time.
   - Not inserted, digest differs, or the existing receipt's observation was deleted: insert
     `delivery_conflict`, increment `connection_health.unresolved_failures`, return `conflict`.
     The transport acknowledges (the delivery was durably recorded) and the conflict is visible
     on the connection (FR 34, criteria 45 and 65). The existing observation is not touched.
4. **Store payload** in `delivery_payload`.
5. **Queue processing**: write outbox event `leads.delivery.received` with the receipt as subject.
6. Commit. Only after commit does the transport acknowledge (webhook `202`, import row counted,
   manual capture confirmed). Criterion 43's failing processing step leaves the receipt because
   processing is a later transaction.

Two concurrent deliveries with the same identifier serialise on the unique index: one inserts, the
other sees the conflict path and finds an equal digest (criterion 44).

### Processing

The worker consumes `leads.delivery.received` (consumer `leads.process_delivery`, not replay-safe)
in one transaction per receipt:

1. **Recheck the connection** (edge case 15, criterion 42). If it is revoked or its signing
   secret was rotated since receipt and the receipt was signed with the old secret (recorded on
   the receipt as `signing_key_generation`), set the receipt `refused` with detail
   `connection_revoked`, count an unresolved failure, and stop. No observation.
2. **Apply the pinned mapping version** from the receipt, never the connection's current one.
   A payload that does not fit its mapping (a required target absent, a transform failing) sets
   the receipt `refused` with the target named (criterion 39) and stops.
3. **Create the observation and its fields.** `value_kind = cleared` when the source path is
   present with a null value and the rule has `clear_on_null`; absent paths produce no row
   (criterion 48).
4. **Resolve the party** through `relationships.party.resolve_or_create` with the evidence the
   connection declares: `external_subject_id` when `subject_authenticated`, `verified_email`
   when `email_verified`, everything else as hints. Automatic linking happens only on the two
   authenticated classes (R4, criteria 50 to 52); hints produce a `relationships.review_candidate`
   and no link. The call is a registered operation, so Leads never touches the relationships
   schema.
5. **Route.** Evaluate the connection's rules in order. `create_opportunity` calls
   `leads.opportunity.create_from_observation`; `attach_to_open_opportunity` attaches to the
   newest open opportunity in the target pipeline that shares the party, else creates one;
   `record_only` stops here with the observation unlinked (FR 39).
6. **Derive fields** (below), set the receipt `processed`, update `connection_health`, and
   write `leads.observation.accepted` plus, when created, `leads.opportunity.created`.

No model is involved anywhere in this path (FR 35, criterion 38).

### Field derivation (FR 37)

`leads.opportunity_field_state` holds the current value of each opportunity field with why it is
the current value:

| Column | Meaning |
| --- | --- |
| `opportunity_id`, `target` | Primary key. |
| `value_kind`, `value_text` | The current value or an explicit clear. |
| `owner` | `source` or `user`. Set to `user` by any hand edit; never set back by intake. |
| `observation_id`, `occurred_at`, `completeness`, `priority` | The evidence that set it. |

A new observation may write a field only when all hold: `owner = source`; the observation's
`occurred_at` is not older than the current one; and, when `occurred_at` is equal, the
observation's `completeness` is not lower and its connection `priority` is not lower. A thinner
or older observation therefore never overwrites (criterion 47); a user-set stage or note is
`owner = user` and survives everything (criterion 49); a `cleared` fact overwrites under the same
rule and is distinguishable from absence (criterion 48). The observation itself is stored
regardless, so nothing is lost, only not applied.

### Transports

**Signed webhook.** `POST /api/v1/intake/webhook/<connection_id>` on the `api` surface. Headers:
`X-Rheo-Timestamp` (Unix seconds), `X-Rheo-Signature` (`v1=<hex HMAC-SHA256 of
"<timestamp>.<body>">`), optional `X-Rheo-Event-Id`. The receiver resolves the connection by path
id, resolves the signing secret through its own secret scope, refuses when the timestamp is
outside `intake.replay_window_seconds` (default 300), verifies the signature in constant time
against `current` and, until `previous_valid_until`, `previous`, and only then builds the
`WorkspaceContext` from the connection and calls `accept_delivery`. A signature failure returns
`401` with no receipt and counts an unresolved failure on the connection (criterion 42). The
connection id in the path is a lookup key, not authorization; the signature is.

**CSV and JSON import.** An owner uploads a file against a connection with `transport = import`.
The importer streams rows, derives each row's `source_event_id` from `event_id_path` (for CSV a
column; absent, the SHA-256 of the row), and calls `accept_delivery` per row inside the batch.
A file whose columns do not match the mapping version's rules is refused whole, naming the first
missing column, before any row is accepted (criterion 39).

**Manual capture.** A form on the Leads surface and the `leads_capture` tool. Each workspace has
one connection with `transport = manual`, created at Leads enable. The capture must name a
funnel from the workspace's funnels; a capture with none is refused before a receipt exists
(criterion 40). The core generates the `source_event_id` (a UUIDv7) and the capture goes through
`accept_delivery` and processing like any delivery, so criterion 39's "identical apart from
transport" holds by construction.

## Part two: events, durable work, operations, audit

### Events and the outbox (FR 15)

All in the `core` schema of each workspace database.

| Table | Columns | Notes |
| --- | --- | --- |
| `outbox_event` | `id uuid`, `position bigserial`, `type text`, `schema_version integer`, `source text`, `subject_ref text`, `subject_revision integer`, `correlation_id uuid`, `causation_id uuid null`, `actor_kind text`, `actor_id uuid null`, `occurred_at`, `data jsonb` | `data` is the declared event model serialised; it is never queried, only delivered, which is the one place the house rule allows a JSON column. `source` is `urn:rheo:module:<module_id>`. |
| `event_delivery` | `event_id`, `consumer_id text`, `state text`, `attempts integer`, `next_attempt_at`, `lease_owner text null`, `lease_until timestamptz null`, `last_error text null`, `completed_at null` | Primary key `(event_id, consumer_id)`. `state` in `pending`, `leased`, `delivered`, `failed`. |
| `consumer_processed` | `consumer_id`, `event_id`, `processed_at` | Primary key `(consumer_id, event_id)`; written inside the consumer's transaction. |

**Envelope.** The `EventEnvelope` in `packages/contracts` is the row above plus the delivery
context, versioned by `schema_version` per event type. Producers may only add optional fields
within a version; a removal or a meaning change is a new version and a consumer declares which
versions it accepts. `correlation_id` is the originating operation's id; `causation_id` is the
event that led to this one when there is one.

**Fan-out at write.** `UnitOfWork.publish(event)` inserts the outbox row and one
`event_delivery` row per consumer that is subscribed to `type` and belongs to a module enabled in
the workspace at that moment. A consumer that is not enabled gets no row and never sees the event.

**Ordering.** Deliveries for the same `(consumer_id, subject_ref)` are delivered in `position`
order, one in flight at a time: the worker will not lease a delivery while another delivery for
the same consumer and subject is `leased`. Across subjects there is no ordering promise.

**Exactly-once effect.** A consumer handler runs inside a `UnitOfWork`; the worker inserts
`consumer_processed` in that same transaction and commits. A redelivery after a crash hits the
primary key, and the worker marks the delivery `delivered` without running the handler
(criterion 11). Consumers are duplicate-safe because the dedup insert is part of the contract,
not left to each handler.

**Retry.** Attempts back off as `5s, 20s, 80s, 320s, 1280s` then cap at 3600s, with jitter, for
`work.max_attempts` (default 8, about two and a half hours end to end). After the last attempt the delivery is `failed`
with its error and appears in `core.work.failures` (criterion 12). An operator or owner may
`retry` a failed delivery, which resets attempts.

**Replay.** `core.work.replay(consumer_id, from_position)` re-creates `pending` deliveries for a
consumer from the outbox. It is permitted only for consumers whose subscription declares
`replay_safe = true` (read-model builders, index maintainers). Consumers that cause external
effects or create domain records declare `replay_safe = false` and the operation refuses to target
them. Replay therefore rebuilds derived state and never resends anything (idea document).

**Cross-module reach.** An event carries references and small facts, never a copy of a record.
A consumer that needs the record resolves the reference under its own context
([identifiers](identifiers.md#resolution-under-permission)).

### Jobs and the worker (FR 16)

| Table | Columns | Notes |
| --- | --- | --- |
| `job` | `id uuid`, `kind text`, `state text`, `input jsonb`, `operation_id uuid null`, `depends_on_ref text null`, `attempts`, `max_attempts`, `next_run_at`, `lease_owner null`, `lease_until null`, `cancel_requested boolean`, `last_error null`, `created_at`, `finished_at null` | `state` in `queued`, `leased`, `succeeded`, `failed`, `cancelled`. `input` is the job kind's declared model serialised and never queried. `depends_on_ref` lets the deletion coordinator cancel dependents. |
| `schedule` | `id`, `module_id`, `name`, `job_kind`, `cron text`, `enabled`, `last_run_at null`, `next_run_at` | Created at module enable from the manifest. |

Worker loop, visiting each active workspace in the registry in turn, with a one-second idle
interval:

1. Lease: `UPDATE ... SET state = 'leased', lease_owner = $worker, lease_until = now() + 60s`
   for one row selected `FOR UPDATE SKIP LOCKED` where `state = 'queued' AND next_run_at <= now()`
   or `state = 'leased' AND lease_until < now()` (an expired lease is a crashed worker; the retry
   counts an attempt).
2. Heartbeat every 20 seconds extends `lease_until`.
3. The handler receives a `CancellationToken` and checks it at its own checkpoints; a `queued`
   job with `cancel_requested` becomes `cancelled` without running; a `leased` job whose token
   fires ends `cancelled`, not succeeded and not retried (criterion 12).
4. Success sets `succeeded`; an exception sets `queued` with backoff or `failed` when the budget
   is spent.
5. Schedules: a due `schedule` enqueues its job kind and advances `next_run_at`; a job already
   queued for the same schedule is not duplicated.

The same loop serves event deliveries, using the delivery table instead of the job table.
Restart recovery is the expired-lease path and nothing else.

### Operations (FR 17)

| Column | Meaning |
| --- | --- |
| `id uuid` | Returned to the caller before completion for long-running operations. |
| `name text`, `safety_class text` | The registered operation. |
| `actor_kind`, `actor_id`, `entry`, `audience_kind`, `audience_id` | From the context. |
| `state text` | `pending`, `running`, `approval_required`, `succeeded`, `failed`, `cancelled`, `unresolved`. |
| `approval_id uuid null` | Set with `approval_required`. |
| `progress_text`, `progress_fraction` | Updated by the job. |
| `result_ref text null`, `error_code text null`, `error_text text null` | Outcome. |
| `terminal_check_kind text null`, `terminal_check_at null` | **Required for `succeeded`**: a database check constraint refuses `succeeded` with these null (criterion 13). The kind names what was checked: `record_exists`, `provider_status`, `sink_recorded`, `handler_returned`. |
| `provider_request_id text null` | For external effects whose provider gives one. |
| `created_at`, `started_at`, `terminal_at` | |

`unresolved` is a terminal state for the operation record and an open item for the person: it is
set when an external effect's outcome is unknown after a timeout and the provider offers neither
idempotency nor status lookup. It is listed by `core.work.failures` and cleared only by
`core.operation.resolve` with an explicit outcome and a note, which is audited.

### Audit (FR 18)

| Column | Meaning |
| --- | --- |
| `id uuid`, `occurred_at` | |
| `actor_kind`, `actor_id`, `entry` | From the context. |
| `operation_name`, `safety_class`, `operation_id null` | What ran. |
| `subject_ref text null` | From the operation's `AuditSpec`. |
| `idempotency_key text null` | For `KEYED` operations. |
| `request_digest bytea` | SHA-256 of the canonical input, so "what exactly was requested" is answerable without storing the input. |
| `outcome text` | `succeeded`, `failed`, `refused`. |

The audit row is written by the service registry's dispatcher inside the operation's transaction
for every operation above the read class. A module never writes it and cannot skip it: an
operation is only callable through the dispatcher, and registration refuses a non-read operation
with no `AuditSpec` (criterion 14). `core.audit.list` (owner only) is the supported read. The
row holds no secret and no reference to one, by the same rule that keeps them out of operation
records ([secrets](storage-and-workspaces.md#a4-the-secret-store-fr-13-guardrail-14)).

### External actions

Introduced here because they are durable work; their approval is in
[confirmation and safety](confirmation-and-safety.md).

| Column | Meaning |
| --- | --- |
| `id uuid`, `operation_id`, `approval_id` | |
| `destination_ref text` | A party reference, a connector destination, or the recording sink. |
| `payload_digest bytea`, `payload_ref` | The approved payload; the digest is rechecked at execution. |
| `state` | `pending`, `executing`, `succeeded`, `failed`, `refused`, `unresolved`, `cancelled`. |
| `provider_request_id null`, `attempts` | |

Execution is a job of kind `core.external_action.execute` with `depends_on_ref = destination_ref`,
so withdrawing a destination party's permission or deleting the party cancels or refuses it
(criteria 61 and 65). Concurrent execution of one action is prevented by the job lease; a retry
after an unknown outcome first reconciles by `provider_request_id` when the provider allows, and
otherwise sets `unresolved`.

## Contact permission records (FR 46)

Leads owns `leads.contact_permission`, separate from any observation:

| Column | Meaning |
| --- | --- |
| `id`, `party_ref`, `purpose text`, `channel text`, `recipient_scope text` | `purpose` from the closed vocabulary `respond`, `follow_up`, `share_with_referral`, `internal_analysis`; `channel` in `email`, `phone`, `message`; `recipient_scope` in `workspace`, `named_referral`. |
| `disclosure_version text`, `evidence_observation_id null`, `granted_at`, `granted_by_kind`, `granted_by_id` | Where the permission came from. An observation's evidence becomes a permission only through `leads.contact_permission.record`, a mutate-class operation a person or a routing rule invokes explicitly; recording an inbound submission creates no permission by itself (criterion 62). |
| `withdrawn_at null`, `withdrawn_reason text null`, `suppressed boolean` | Withdrawal and suppression. |

`leads.contact_permission.check(party_ref, purpose, channel)` is the execution guard external
actions and the memory module's purpose filter call ([confirmation and safety](confirmation-and-safety.md#execution-guards)).
The purpose vocabulary is a contracts enum in release one; the framework-proof phase decides how
modules extend it. The external correction flow for copies held by other systems is out of
release one, as the requirements' disposition of question 19 records.
