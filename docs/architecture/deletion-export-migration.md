# Deletion, export and restore, and migration verification

**Part of:** the [architecture specification](README.md). Designs against R5, FR 28, FR 46,
FR 51 to FR 53, and criteria 21, 29, 32, 36, 65, 67. Also answers the disaster-recovery half of
idea-document question 13 for release one.
**Decision:** A14 (deletion coordinator with synchronous participants). See the
[decision list](README.md#architecture-decisions).

## Record-level deletion (R5, FR 51)

### The operation

`core.record.delete(ref)`, destructive class, per-action confirmation, no standing grant. Any
module can call it for a record type whose manifest marks `deletable = true`; release one has
three: `leads.observation`, `relationships.party`, `leads.opportunity`. The memory module's
`recallatron_forget` is the same coordinator invoked for `recallatron.memory`.

### The cascade

The coordinator runs the whole cascade in **one transaction** against the workspace database,
which the one-database-per-workspace layout makes possible without a distributed step. Order:

1. **Guards.** The approval is rechecked (window, actor); the record must still exist at the
   approved revision.
2. **Owning module.** The owner's registered `delete(ref)` removes the record and every row it
   owns for that record (an observation's fields and payload; an opportunity's field state,
   qualifications, and handoff rows; a party's contact points and affiliations).
3. **Deletion participants.** Every module enabled in the workspace that declared a
   `DeletionParticipant` for the type runs its handler in the same transaction:
   - `recallatron.on_record_deleted`: invalidate memories derived from the reference, remove
     their embeddings and lexical index entries, mark summaries superseded (FR 28, criterion 29).
   - `leads.on_party_deleted`: null `observation.party_ref` for every observation that referenced
     the party, so they remain as unlinked evidence (R5); mark opportunities' party links
     removed.
   - `leads.on_observation_deleted`: keep the `delivery_receipt` row; delete only its
     `delivery_payload`; set the receipt's `state_detail = observation_deleted`.
4. **Core participants.** Queued jobs and pending external actions with
   `depends_on_ref = ref` (or whose destination is the deleted party) are set `cancelled`
   (criterion 65). Approvals bound to the reference go `invalidated`.
5. **Held exports.** Every `export_record` whose `export_record_ref` rows include the reference is
   marked `state = removed_by_deletion` with `removed_at` and the deletion record id.
6. **Deletion record.** `core.deletion_record` is written.
7. **Commit.** After commit, the coordinator deletes the marked export artifacts from the data
   root; a failure to remove a file leaves the export record marked and enqueues
   `core.exports.sweep`, which retries until the path is gone. The record says why the artifact
   is gone before the artifact is gone, never the reverse.

A participant that raises aborts the whole deletion; the record survives untouched and the
operation reports the participant's error. Deletion never cascades to another workspace, to
shared credentials, or to unrelated records (idea document).

### The deletion record

| `core.deletion_record` column | Meaning |
| --- | --- |
| `id uuid`, `deleted_at` | |
| `record_type text`, `record_id uuid` | What, by identifier only. |
| `actor_kind`, `actor_id`, `approval_id` | Who, and the confirmation. |
| `participants text[]` | Which participants ran. |
| `cancelled_job_count integer`, `cancelled_action_count integer`, `removed_export_count integer`, `invalidated_memory_count integer` | Counts only. |

No column can hold content from the deleted record; the model has no field for it, and the test
in criterion 65 asserts no field value from the deleted record appears anywhere in the row. The
record resolver returns `state = deleted` for the reference from this table.

### Deletion is not withdrawal

`leads.contact_permission.withdraw(party_ref, purpose, channel)` sets `withdrawn_at` on the
permission and leaves every record in place; queued actions fail closed at their guard and derived
memory stops being retrievable for the purpose (criterion 61). `core.record.delete` removes the
record and leaves permissions untouched. The interface offers them as two actions on a party with
two confirmations, and neither operation calls the other (FR 46, R5).

### Receipts and re-delivery

The receipt outlives the observation with `source_event_id`, `content_digest`, `received_at`,
`source_occurred_at`, and no payload. A later delivery with the same identifier hits the unique
index; the intake path finds the receipt's `state_detail = observation_deleted` and records a
`delivery_conflict` whatever the digest, so the observation is never recreated and the conflict is
visible on the connection (criterion 65). Only an operator command that deletes the *receipt* would
allow the event to be accepted again, and release one ships no such command.

## Export and restore (FR 52)

### The artifact

A directory under `<data_root>/workspaces/<id>/exports/<export_id>/`, packed to one `.tar.zst`
when complete:

```text
manifest.json          core version, contract version, workspace id and slug, created_at,
                       modules: [{ module_id, package_version, schema_version, export_format_version }],
                       settings_digest, record_counts per type, approval_count
settings.jsonl         workspace and member settings, one row each; secret references, never values
core/
  approvals.jsonl      every non-terminal approval, written with state = requires_reapproval
  operations.jsonl     non-terminal operations, written as unresolved
  audit.jsonl          the audit log
  deletions.jsonl      deletion records
<module_id>/
  <record_type>.jsonl  one line per record, in the module's declared export format,
                       validated against its JSON Schema (schema_path) before the export completes
  files/               copies of workspace files the module's records reference
```

Every record type marked `exportable` is written by the module's `exporter` through a core writer
that enforces the schema. The core writes its own tables. Secret values are absent by
construction: no exporter can resolve one.

### Export records

| Table | Columns |
| --- | --- |
| `core.export_record` | `id uuid`, `artifact_path`, `created_at`, `created_by_id`, `state` (`in_progress`, `complete`, `failed`, `removed_by_deletion`), `removed_at null`, `deletion_record_id null`, `byte_length` |
| `core.export_record_ref` | `export_id`, `record_ref` for every record of a deletable type in the artifact |

The reference index exists for one reason: criterion 65's "the export artifact is gone from the
data root and its export record says why" needs the coordinator to find which artifacts carry a
record without opening them. It is bounded by the number of deletable records times the number
of held exports, and the sweep removes rows with their artifacts.

### Restore

`rheo workspace restore <artifact>` on the operator command, or `core.workspace.restore` for an
owner into a workspace the control plane does not yet know:

1. Read and validate `manifest.json`; refuse if the contract version is unsupported or any listed
   module is not host-loadable at a version satisfying the recorded one, naming it.
2. Create the workspace row with the recorded id and slug (identifiers are globally safe, so the
   id is kept and comparison in criteria 21, 36, 67 is by id), provision the database, apply the
   core chain.
3. Install each module at the recorded schema version by running its chain to that version, then
   upgrade to the host's version if newer (a second migration, recorded).
4. Import settings, then each module's records through its `importer` in dependency order, then
   core tables.
5. Every approval lands `requires_reapproval`; every pending external action lands `pending` with
   `approval_id` pointing at an approval that is not `approved`, so it cannot execute until a
   person approves again (criterion 21). Every connection lands `needs_credential`; every member
   credential `needs_value`.
6. Set the workspace `active`; write an `export_record`-style `restore_record` with the source
   artifact's digest.

The comparison the criteria require is a supported operation, `core.workspace.digest`, that
returns per-type record counts and a per-type content digest computed from the export
serialisation, so "match by comparison" is one call on each side.

## Migration verification (FR 53)

The predecessor memory store's migration in phase two, and any later predecessor migration, is
verified before switchover and the result kept where the data lives:

| `core.migration_verification` column | Meaning |
| --- | --- |
| `id`, `source_name text`, `module_id`, `run_at`, `run_by_id` | `source_name` is a label chosen by the operator; the public repository never carries a real source's name. |
| `source_count integer`, `destination_count integer`, `missing_count integer` | Every source record must have a destination record. |
| `sample_size integer`, `sample_matched integer`, `tolerance_fraction numeric`, `passed boolean` | A sampled set of retrieval queries compared under the old and new retrieval layers; `passed` when `sample_matched / sample_size >= 1 - tolerance_fraction`. Default tolerance 0.05, recorded on the row. |
| `report_file_ref null` | An optional fuller report under the workspace's private files. |

The migration job writes the row and stops. Switchover (pointing the workspace's memory module at
the migrated records as its live set) is `recallatron.migration.switch_over`, a separate mutate
operation a person invokes after reading the verification (criterion 32). A CI check asserts no
file matching a migration-report pattern is tracked in the repository.

## Disaster recovery for release one

Answers the remainder of idea-document question 13 at release-one scale.

- **What is backed up.** The control-plane database and every workspace database by `pg_dump`,
  plus the data root (secrets directory, workspace files, exports). Postgres backups are the
  operator's, on the operator's schedule; `deploy/` ships a generic example.
- **What restore means.** Two paths, both exercised: a database-level restore of a cluster
  backup, which is Postgres's own procedure; and the application-level export and restore above,
  which is the path the acceptance criteria drill at the end of each phase.
- **How it is tested.** Criteria 21, 36, and 67 are the drill: export, restore into an empty
  deployment, compare by digest. Running them in CI at every phase end is the release-one
  disaster-recovery test plan; a cluster-backup restore drill is an operator runbook in `deploy/`
  and is not automated in release one.
- **What is not covered.** Point-in-time recovery, replica failover, and per-workspace encryption
  keys are the hosted edition's ([later phases](later-phases.md#phase-8-the-hosted-edition)).
