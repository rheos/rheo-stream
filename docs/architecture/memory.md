# Memory: records, provenance, audience, and invalidation

**Part of:** the [architecture specification](README.md). Designs against D9, D11, FR 26 to
FR 30, FR 28's cascade, and criteria 24 to 33, 36, and the memory clause of 61. The retrieval
adapter's storage is in [storage](storage-and-workspaces.md#retrieval-adapter-d9-fr-30); this
document owns the records it indexes.
**Decision:** A17 (explicit audience and purposes with intersection on derivation; one
invalidation rule). See the [decision list](README.md#architecture-decisions).

## What a memory is, and is not

A memory is something the workspace was told to remember, or derived from records or other
memories on request: a note, a fact, a decision with its reasons, or a summary. It carries who
may read it, for which purposes it may reach a model, where it came from, and when it stops being
retained. It is never the authoritative record: a summary of an opportunity is not the
opportunity, and every link back is a reference resolved under the caller's permission
(idea document). Release one remembers what it is told to remember; nothing is extracted from
conversations automatically.

## Entities

All in the `recallatron` schema. Every table has `id uuid` (UUIDv7) unless noted.

| Table | Columns | Notes |
| --- | --- | --- |
| `memory` | `kind text`, `title text`, `body text`, `search_tsv tsvector`, `audience_kind text`, `audience_id uuid null`, `purposes text[]`, `confidence numeric null`, `occurred_at timestamptz null`, `recorded_at`, `recorded_by_kind`, `recorded_by_id`, `origin text`, `revision integer`, `corrected_at null`, `superseded_by_id uuid null`, `invalidated_at null`, `invalidation_reason text null`, `retention_until timestamptz` | `kind` in `note`, `fact`, `decision`, `summary`. `search_tsv` is generated from `title` and `body` with a GIN index (the lexical index). `audience_kind` in `workspace`, `member`; `audience_id` is the account when `member` and null otherwise (check constraint). `purposes` is a non-empty subset of the closed purpose vocabulary. `origin` in `told`, `derived`, `migrated`. `invalidation_reason` in `source_deleted`, `source_corrected`, `source_superseded`. `superseded_by_id` names the memory that replaced this one. |
| `memory_entity` | `kind text`, `name text`, `normalized_name text`, `ref text null`, `created_at` | `kind` in `person`, `organization`, `project`, `topic`, `place`, `thing`. `ref` is a record reference when the entity is a domain record (a `relationships.party`), resolved under permission on read. Unique on `(kind, normalized_name)`. |
| `memory_mention` | `memory_id`, `entity_id`, `role text null` | Primary key `(memory_id, entity_id)`. Which entities a memory is about. |
| `memory_link` | `memory_id`, `ref text`, `relation text`, `created_at` | Primary key `(memory_id, ref, relation)`. `relation` in `derived_from` (a source this memory was made from: another memory, or a record) and `about` (a record this memory concerns, including every party a source involves, written at derivation time). Provenance and the permission check both read this table. |
| `memory_embedding` | `memory_id`, `model_id text`, `dimensions integer`, `vector vector`, `embedded_at` | Primary key `(memory_id, model_id)`; HNSW index, cosine. The dense index. Rows exist only for live, non-invalidated memories. |
| `retention_policy` | `kind text pk`, `retain_days integer`, `updated_by_id uuid null`, `updated_at` | One row per memory kind, written at enable from package defaults (`note` 365, `fact` 365, `decision` 730, `summary` 180), each clamped to the workspace's `recallatron.retention.days`. |

The two indexes (`search_tsv` and `memory_embedding`) are the retrieval index criterion 29
queries. A memory holds no secret and no contact point value; a party's contact points live in
the relationships module and are `restricted` in the redaction tiers.

## Audience and purposes (FR 27, criteria 27 and 28)

Every memory carries an explicit audience and an explicit purpose set from the day it is
written. There is no implicit "everyone".

**Audience** is a two-level lattice in release one: `workspace` (every member of the workspace)
above `member:<account>` (that account only). A memory recorded with `audience = member` is the
recording account's own; nobody can record a memory private to someone else. Phase six's channel
audiences are a later value of the same column, not a new mechanism.

**Purposes** are the closed vocabulary shared with contact permission (`respond`, `follow_up`,
`share_with_referral`, `internal_analysis`). A `remember` call names them; the default is
`recallatron.default_purposes` (package default `respond, follow_up, internal_analysis`,
workspace scope, floor `subset`). A run with purpose `p` can be given a memory only when `p` is
in its purposes ([context builder](runtime-and-mcp.md#the-context-builder)).

**Derivation intersects, never unions.** `recallatron.memory.derive(sources, kind, title, body)`
writes a memory whose `audience` is the meet of its sources' audiences (`workspace` and
`member:A` give `member:A`; `member:A` and `member:B` give nothing) and whose `purposes` is the
intersection of its sources' purposes. An empty audience refuses with `audience_empty`; an empty
purpose set refuses with `purposes_empty`; a memory nobody may read for no purpose is not
written. A record source (an opportunity, an observation, a party) contributes `workspace` and the
full vocabulary, because records carry neither column in release one; the person behind a record
constrains use through contact permission at retrieval instead (below). So a memory derived from a
broadly readable memory and a member-private one is member-private (criterion 28), and a memory
stored under one member's audience is invisible to another member's query (criterion 27).

## Provenance and links

`memory_link` rows are written by the operation that creates the memory and are never edited:

- `derived_from`: each source of a `derive`, each record a `remember` cites, and the predecessor
  record of a migrated memory.
- `about`: each record the memory concerns, plus every `relationships.party` a source involves at
  the time of writing (an opportunity's linked parties through `leads.opportunity.get`; an
  observation's `party_ref`), expanded once at write time so retrieval has a bounded set to check.

A link is a reference string, never a foreign key into another schema (FR 11). A memory may link
to Leads records only when Leads is enabled in the workspace; the memory module declares Leads
and relationships as optional dependencies and reaches them through registered operations by
name, which is what lets criterion 66's no-memory run and a memory-without-Leads workspace both
exist.

## Retrieval (FR 27, FR 30, criteria 27 and 31)

`recallatron.memory.recall(query, purpose, k, kinds, since)`, read class, roles `owner`,
`member`, `service`. Two stages, both inside the module's `RetrievalStrategy.search`:

1. **Candidate set in SQL, before ranking.** Live memories only: `audience_kind = workspace`, or
   `audience_kind = member` with `audience_id` equal to the caller's account (an `account` actor's
   id; a `token` actor resolves to its account; a `system` or `connection` actor has no account
   and sees `workspace` memories only), `purposes` contains `purpose`, `invalidated_at is null`,
   `superseded_by_id is null`, `retention_until > now()`, plus the caller's kind and time
   filters. Nothing outside this set is scored.
2. **Ranking, then the per-link permission check.** The strategy ranks the candidate set
   (lexical, dense, or hybrid, [storage](storage-and-workspaces.md#retrieval-adapter-d9-fr-30))
   and takes the top `k * recallatron.retrieval.overfetch` (default 5). For each hit, every
   `memory_link.ref` is resolved under `ctx`: a reference that is unreadable or `deleted` drops
   the hit. When Leads is enabled, every `about` link to a party runs
   `leads.contact_permission.check(party_ref, purpose)`; a result of `withdrawn` or `suppressed`
   drops the hit (criterion 61); `absent` does not, because no permission record is the normal
   state of every party (criterion 62) and a memory is the workspace's own note about its work,
   while a withdrawal or suppression is a person's expressed refusal and must bite. The first
   `k` survivors are returned; if fewer survive, one further slice is fetched, then the call
   returns what it has.

The result carries `ref`, `kind`, `title`, `body`, `score`, `strategy`, `occurred_at`, and the
resolved heads of its links. Criterion 31 runs this and the write path under `lexical` and
`dense` in turn; the candidate SQL and the link check are strategy-independent.

## Correction and supersession (FR 28, criterion 29)

Two operations, one rule underneath.

- `recallatron.memory.correct(ref, title, body, confidence)`, mutate, roles `owner`, `member`:
  the memory was wrong and is fixed in place. `revision` increments, `corrected_at` is set, the
  memory is re-indexed (its embedding rows deleted and re-created, `search_tsv` regenerates), and
  the rule below runs for `recallatron.memory:<id>` with reason `source_corrected`.
- `recallatron.memory.supersede(ref, replacement)`, mutate, roles `owner`, `member`: a new memory
  replaces the old one, which stays readable as history. The replacement is written like a
  `remember` with a `derived_from` link to the old memory; the old memory's `superseded_by_id` is
  set, its embedding rows are deleted, and the rule runs for it with `source_superseded`.

**The one invalidation rule.** `invalidate_derived(ref, reason)`: find every memory with a
`memory_link` to `ref` in either relation, and, transitively, every memory with a `derived_from`
link to a memory so found. For each:

- delete its `memory_embedding` rows, so the dense index no longer holds it;
- with reason `source_deleted`: delete the memory row with its links and mentions, so the lexical
  index no longer holds it either; a derivative of erased data has no reason to exist, and R5
  wants derivatives gone, not marked;
- with any other reason: set `invalidated_at` and `invalidation_reason` and keep the row; the
  candidate SQL excludes it, `recall(include_invalidated = true)` shows it to a person deciding
  whether to re-derive, and nothing re-derives on its own.

The same function runs from `correct`, from `supersede`, and from the deletion participant
below. It is one function so that criterion 29's "in the same operation" is a property of the
transaction the caller already holds, not of three implementations agreeing.

## Deletion (FR 28, R5, criterion 65)

`recallatron.memory` is a deletable record type. `recallatron_forget` is `core.record.delete` for
it: the owning delete removes the memory row, its embedding rows, links, and mentions; then the
participant `recallatron.on_record_deleted` runs `invalidate_derived(ref, source_deleted)` for
memories derived from it. The same participant is registered for `leads.observation`,
`leads.opportunity`, and `relationships.party`, so deleting any of those removes every memory
linked to it and every memory derived from those, inside the coordinator's transaction
([deletion](deletion-export-migration.md#the-cascade)). The deletion record's
`invalidated_memory_count` is the number of memory rows removed.

## Retention (FR 29, criterion 30)

`recallatron.retention.days` (package default 365, `explicit_per_workspace`, floor `min`) is
written as a row at enable ([module contract](module-contract.md#install-and-enable-release-one-in-code)),
so every workspace has an explicit bounded setting and none inherits indefinite retention. It is
the ceiling. Under it, `retention_policy` holds one `retain_days` per kind, written at enable
from the package defaults and editable by an owner through `recallatron.retention_policy.set`
(mutate, roles `owner`), which refuses a value above the ceiling; the read path clamps too, so
tightening the ceiling takes effect at once. A single number would satisfy FR 29; the per-kind
rows exist because a decision and a scratch note have different useful lives, and one number long
enough for decisions would retain notes far longer than needed.

`memory.retention_until` is set at write from `recorded_at` plus the kind's `retain_days`, and
recomputed for existing rows when a policy row changes. The scheduled job
`recallatron.retention_sweep` (daily, `system` actor) removes memories past `retention_until`
through the same owning delete and `invalidate_derived(source_deleted)`, and writes a
`core.deletion_record` with `actor_kind = system` and no approval, which is R5's one permitted
scheduled expiry.

## Migration from the predecessor (FR 53, criterion 32)

`recallatron.migration.import(source_label, extract_file_ref)`, mutate, roles `owner`,
long-running: creates a `recallatron.migration_batch(id, source_label text, state text,
verification_id uuid null, created_at)` row (`state` in `importing`, `verified`, `live`,
`failed`; a declared record type whose resolver returns a label and nothing else), writes each
predecessor record as a memory with `origin = migrated`,
`audience = workspace`, the default purposes, and a `derived_from` link to the batch, then
re-embeds under the configured strategy and writes the `core.migration_verification` row
([migration verification](deletion-export-migration.md#migration-verification-fr-53)).
Memories of a batch in state `verified` are excluded from the candidate SQL until
`recallatron.migration.switch_over(batch_ref)` (mutate, roles `owner`) sets the batch `live`.
The extract file and the report are workspace files under the data root, never in the
repository.

## Web contribution

Memory browse, search, and entity screens (the phase-two port) plus the unified navigation and
theme. The screens call `recall`, `remember`, `correct`, `supersede`, the entity reads, and the
retention policy read and set, through the internal API like every other screen.

## Export

`memory`, `memory_entity`, `memory_mention`, `memory_link`, and `retention_policy` are
`exportable`; `memory_embedding` is not (it is rebuilt from `body` on restore by a job, since the
embedding model may differ). Criterion 36's comparison is over the exportable set.

## Operations and roles

| Operation | Class | Roles | Tool |
| --- | --- | --- | --- |
| `recallatron.memory.recall` | read | owner, member, service | `recallatron_recall` |
| `recallatron.memory.remember` | mutate | owner, member, service | `recallatron_remember` |
| `recallatron.memory.derive` | mutate | owner, member, service | `recallatron_derive` |
| `recallatron.memory.correct` | mutate | owner, member | `recallatron_correct` |
| `recallatron.memory.supersede` | mutate | owner, member | `recallatron_supersede` |
| `core.record.delete` for `recallatron.memory` | destructive | owner, member (a member only for a memory its audience lets it read) | `recallatron_forget` |
| `recallatron.entity.list`, `.get` | read | owner, member, service | none in release one |
| `recallatron.retention_policy.get`, `.set` | read, mutate | owner (set); owner, member (get) | none |
| `recallatron.migration.import`, `.switch_over` | mutate | owner | none (operator and web only) |

`service` on `remember` and `derive` is what lets a job or a model run write a memory on the
actor's behalf; the audience of anything a `service` actor writes is the audience of the
operation that started it, never wider.

## A17. Explicit audience and purposes, intersection, one invalidation rule

**Decision.** Audience and purposes are columns on every memory, required at write; derivation
takes the meet and the intersection and refuses when either is empty; one function invalidates
derivatives for deletion, correction, and supersession, with deletion removing rows and the other
two marking them.

**Why columns and not a policy lookup.** FR 27 and criterion 28 ask what a memory *carries*,
because a derived memory outlives the conditions under which its sources were readable. A lookup
at read time against the sources would widen the moment a source was loosened; a stored
intersection cannot.

**Why one rule with two dispositions.** Criterion 29 and R5 ask for the same traversal from
three entry points; three implementations would agree until one was changed. The disposition
differs because the reasons differ: erased personal data must not survive in a derivative, while
a corrected fact leaves a derivative wrong but not forbidden.
