# Rheo Stream — phased build plan

**Status:** Accepted plan skeleton. Phases one to three are planned to implementable depth;
later phases are sketches that will be planned when their predecessor lands.
**Companion:** [Requirements and scope](requirements-and-scope.md), which carries the decisions,
functional requirements (cited as FR *n*), and the release-one scope boundary.
**Source of acceptance criteria:** the architecture acceptance-scenario table in the
[idea document](../ideas/rheo-stream-idea.md#architecture-acceptance-scenarios). Every criterion
below names the scenario it comes from.

Acceptance criteria are numbered continuously across the whole plan and are checkable by
inspection or by a test. None is a judgement about quality.

Release one is phases one to three. Phases four onward follow it.

---

## Phase 1 — Walking skeleton

**Goal.** A running application with nothing in it: a workspace exists, its storage is
provisioned and versioned, background work survives a crash, an agent can reach the system
through MCP, a person can log in, and a fresh clone runs a synthetic demo. No domain module
ships in this phase.

**In scope**

- Repository bootstrap: the Python core service, the Next.js application shell, the container
  stack with a Postgres container, the development harness, and the publication checks wired
  into continuous integration.
- Workspace and storage foundation: the control plane (accounts, workspace registry), the
  per-workspace database provisioning path, migration tracking per module, and the storage
  adapter seam.
- Identity: the identity-provider boundary with one OAuth code-host provider, plus locally
  issued tokens for command-line and MCP clients.
- Durable work: the transactional outbox, the worker with leases and bounded retries,
  operation records with terminal status, and the audit record.
- The MCP façade with the safety-class registration check and a small set of read-class tools
  sufficient to prove the boundary.
- `ClaudeCliRuntime` behind the runtime adapter contract, with capability discovery.
- Workspace export and restore.

**Out of scope**

- Any domain module. There are no leads, no work items, and no memories in this phase.
- The second runtime adapter, channels, and voice.
- Module disable, remove, purge, and restore (D5).
- Any interface beyond the shell, a login, and a workspace switcher.

**Acceptance criteria**

1. A clone of the public repository, with no private configuration and no credentials, builds
   and starts the synthetic demo, and the demo completes without reading any file outside the
   checkout and the synthetic fixture set. *(Scenario: Fresh public clone.)*
2. Running the demo and normal startup writes no file inside the tracked source tree; `git
   status` is clean after a full run. *(Scenario: Local private workspace; FR 10, FR 14.)*
3. With the checkout-local fallback directory explicitly selected, every configuration file,
   upload, database, database sidecar, export, and log it produces is matched by the repository
   ignore rules, verified by a test that creates one of each and asserts it is ignored.
   *(Scenario: Checkout-local fallback; FR 10.)*
4. `python3 scripts/check_repository.py` exits zero in continuous integration on every branch,
   and the container build context excludes the private sibling directories by construction.
   *(Scenario: Publication review.)*
5. Each workspace's records are in a distinct Postgres database or schema, verified by a test
   that creates two workspaces, writes to one, and asserts the other's storage is unchanged.
   *(Scenario: Hosted workspace data; FR 7.)*
6. No code path accepts a database path, connection string, schema name, or workspace
   identifier from a request body, query parameter, model argument, or workspace setting. A test
   supplies each of those and asserts the value is ignored and the authenticated context is used.
   *(Scenario: Wrong workspace or channel audience; FR 2.)*
7. A request carrying a valid record or operation identifier belonging to another workspace is
   refused by the HTTP API, the MCP façade, and the job dispatcher alike. *(Scenario: Wrong
   workspace or channel audience; FR 1.)*
8. Every workspace row records the installed core version, each installed module's version, and
   each module's schema version, readable through a supported operation rather than by querying
   a migration table directly. *(Scenario: Module reinstalled or upgraded; FR 9.)*
9. A state change and its outgoing event commit in one transaction. A test that kills the
   process between commit and delivery, then restarts, observes the event delivered exactly once
   to a consumer that records processed identifiers. *(Scenario: Crash during handoff; FR 15.)*
10. A worker killed mid-task releases its lease and the task is retried within its bounded retry
    budget; a task exhausting its budget appears in a failure list with its error, and is not
    silently dropped. *(Scenario: Crash during handoff; FR 16.)*
11. Every long-running operation returns an operation identifier before it completes, and that
    operation reports one of a fixed set of terminal statuses, including an explicit unresolved
    status. A test asserts no operation can report success without a recorded terminal check.
    *(Scenario: Crash during handoff; FR 17.)*
12. A workflow that declares a requirement the configured runtime cannot satisfy (structured
    output, streaming, or continuation) is rejected before the runtime is invoked, with a named
    unmet capability. *(Scenario: Runtime capability mismatch; FR 20.)*
13. A headless run whose executable is missing, whose credential is expired, whose tool is
    denied, or whose output stream truncates returns a distinct non-success state within the
    configured deadline. A test induces each of the four and asserts no hang and no success
    report. *(Scenario: Headless approval or failure; FR 21.)*
14. Every registered MCP tool declares exactly one safety class, and a tool registered without
    one fails registration at startup with a named tool. *(Scenario: Headless approval or
    failure; FR 24.)*
15. A workspace export produces an artifact that a restore reads back into an empty deployment,
    after which the restored workspace's composition, configuration versions, and records match
    the original, verified by comparison rather than by inspection. *(Scenario: Export and
    restore.)*

---

## Phase 2 — The memory module

**Goal.** Recallatron ships as the first real module: installed and enabled through the module
registration contract, storing and retrieving durable memory under workspace and record
permissions, with its retrieval layer rebuilt on Postgres and its data migrated out of the
predecessor. This phase proves module contract v1 on the smallest domain that can carry it.

**In scope**

- The module manifest and the install and enable path, implementing the subset of the lifecycle
  contract that D5 places in release one.
- Memory records with provenance, entities and relationships, decisions, time, confidence,
  correction, and supersession.
- The retrieval adapter, with the release-one implementation on pgvector for dense retrieval and
  `tsvector` or `pg_trgm` for lexical retrieval, or a hybrid of the two (D9).
- Permission-enforced retrieval, including inheritance of source access and purpose restrictions
  by derived memories.
- Retention policy per workspace.
- Migration and cutover from the predecessor's memory store: extraction, re-embedding under the
  new retrieval layer, verification, and switchover.
- The application shell, navigation, and theme unification, plus the memory browse, search, and
  entity screens ported from the predecessor.

**Out of scope**

- Module disable, remove, purge, and restore.
- Cross-module memory links to Leads records beyond the reference type, since Leads does not
  exist yet. The link type is defined here and exercised in phase three.
- Automatic memory extraction from conversations. Release one remembers what it is told to
  remember.

**Acceptance criteria**

16. The memory module is installed and enabled entirely through the registration contract: no
    core file changes to add it, verified by a test that enables it in a fresh workspace and
    asserts its records, tools, migrations, and interface contributions all appear.
    *(Scenario: A new specialist module; FR 26.)*
17. The module's manifest declares its owned record types, its storage destination, its
    migrations, its configuration schema, its provided tools with their safety classes, and its
    export format. A manifest missing any of these fails validation at install with a named
    missing field. *(Scenario: A new specialist module.)*
18. The module writes only to its own storage. A test asserts that no memory-module code path
    holds a handle to another module's tables, and that the core's storage API is the only route
    to a connection. *(Scenario: A new specialist module; guardrail 6; FR 11.)*
19. A retrieval call by an actor without permission on a source record returns no content
    derived from that record, verified by a test that stores a memory under one permission
    scope and queries it under another. *(Scenario: Wrong workspace or channel audience; FR 27.)*
20. A memory derived from two sources carries the intersection of their audiences, not the
    union. A test combines a broadly readable source with a restricted one and asserts the
    result is restricted. *(Scenario: Wrong workspace or channel audience; FR 27.)*
21. Deleting or superseding a source record invalidates its derived summaries and its
    embeddings in the same operation, verified by querying the retrieval index afterward.
    *(Scenario: Permissions or contact purpose withdrawn; FR 28.)*
22. Every workspace has an explicit memory retention setting, and a workspace created with no
    explicit setting receives a bounded default rather than indefinite retention. *(Scenario:
    Permissions or contact purpose withdrawn; FR 29.)*
23. The retrieval strategy is selected through the adapter, and a test runs the module's full
    behavioural suite against both a dense-only and a lexical-only configuration, both passing.
    *(Scenario: Runtime choice, applied to retrieval rather than to a model runtime; FR 30.)*
24. The migration from the predecessor's memory store is verified by a count-and-sample
    comparison: every source record has a destination record, and a sampled set of retrieval
    queries returns the same records under the new retrieval layer as under the old one, within
    a documented tolerance recorded in the migration report. *(Scenario: Export and restore;
    D9.)*
25. Every other release-one path completes correctly with the memory module disabled at the
    workspace level, verified by running the phase-one acceptance suite with it off.
    *(Scenario: Client work without Leads; FR 26.)*

---

## Phase 3 — The opportunity core

**Goal.** The first real funnel works end to end. An inbound inquiry from a site the maintainer
already operates arrives, becomes an observation with provenance, resolves a party, creates an
opportunity in a configured pipeline, and is worked to a terminal disposition in the web
interface and through Rheo. This phase completes release one.

**In scope**

- The relationships module at the R4 contract: party identity, contact points, affiliations,
  automatic matching restricted to authenticated evidence, and merges reversible by
  construction.
- Generic intake: the authenticated ingestion API, a signed webhook receiver, CSV/JSON import,
  manual capture, declarative versioned field mapping, durable receipts, and connection health.
- Observations with per-field provenance, occurrence and receipt time, bounded source payload,
  and acquisition attribution separate from delivery transport.
- Opportunities, pipelines with stable stage identifiers and pinned configuration versions,
  qualification records, and terminal dispositions.
- The handoff operation, defined with no destination.
- Contact purpose and permission records, kept separate from observed interest.
- The first web interface: opportunity list and triage, opportunity detail with evidence,
  qualification view, and connection settings, ported per the UI port inventory.
- The first real funnel connected, plus a second unrelated synthetic funnel as a fixture.

**Out of scope**

- Any job-search field, source, rubric, or screen.
- Work creation. A handoff has no destination in this phase.
- External CRM connections. The field-ownership contract is written; no connector ships.

**Acceptance criteria**

26. A valid signed webhook delivery is authenticated, stored, acknowledged, and processed to a
    created opportunity with no agent runtime process running anywhere in the deployment.
    *(Scenario: Intake without a model session; FR 35.)*
27. The acknowledgement returned to the sender is emitted only after the receipt and its pending
    processing work are durably stored, verified by a test that fails the processing step and
    asserts the receipt survives. *(Scenario: Intake without a model session; FR 33.)*
28. Two concurrent deliveries carrying the same source event identifier produce exactly one
    observation and exactly one processing effect. *(Scenario: Same event retried concurrently;
    FR 34.)*
29. A delivery reusing an accepted source event identifier with different content is recorded as
    a conflict, is visible as one, and does not modify the existing observation. *(Scenario: Same
    event retried concurrently; FR 34.)*
30. An observation arriving with an older source occurrence time than the current field values
    does not overwrite them, and a thinner observation does not overwrite a richer one. A test
    submits both orderings and asserts identical resulting field values. *(Scenario: Late
    evidence or scoring result; FR 37.)*
31. A field absent from a payload and a field explicitly cleared by a payload produce
    distinguishable results. *(Scenario: Late evidence or scoring result; FR 37.)*
32. A user-set stage or note survives any later observation, verified by a test that sets a
    stage by hand and then submits a fuller observation. *(Scenario: Late evidence or scoring
    result; FR 37.)*
33. The same person completing two funnel steps produces two observations, and produces two
    opportunities only when a routing rule says so. A test asserts one party, two observations,
    and the configured opportunity count. *(Scenario: One person, several interactions; FR 39.)*
34. An automatic party match occurs only on an authenticated external subject identifier within
    the connection's namespace or on a source-verified email address. A test presents a matching
    name, a matching company domain, and a matching phone number and asserts each produces a
    review candidate and no link. *(Scenario: One person, several interactions; FR 41, R4.)*
35. Party matching never considers a party in another workspace, verified by a test that creates
    identical parties in two workspaces and asserts no candidate crosses. *(Scenario: Wrong
    workspace or channel audience; FR 41.)*
36. After a merge, both original party identifiers still resolve, and an unmerge restores the
    pre-merge state including every record's party reference. *(Scenario: One person, several
    interactions; FR 41, R4.)*
37. Two unrelated funnels, the maintainer's inbound-inquiry form and a synthetic event-referral
    funnel, run through the same intake contract with different declarative mappings, and neither
    requires a new core field, a provider-specific column, or a product name anywhere in the core.
    *(Scenario: Two different custom funnels; FR 44.)*
38. A workspace works a pipeline to a terminal disposition with no job board configured, no
    candidate profile present, and no application tool registered. A test asserts the
    job-search-related configuration surface is absent rather than merely hidden. *(Scenario:
    Business-only installation.)*
39. Editing a pipeline preset does not change the stage meaning or field schema of opportunities
    created under an earlier configuration version, verified by a test that edits a preset with
    opportunities mid-stage and asserts their pinned version and stage semantics are unchanged.
    *(Scenario: Preset edited during active work; FR 43.)*
40. Every opportunity and every qualification record stores the configuration version it was
    created under, readable through a supported operation. *(Scenario: Preset edited during
    active work; FR 42, FR 43.)*
41. An inbound payload whose text instructs the agent to send a message, grant a tool, or change
    a policy results in no tool grant, no policy change, and no external effect. The text is
    retrievable as evidence. *(Scenario: Source text requests a tool action; FR 25.)*
42. Withdrawing contact permission causes a queued action against that contact to fail closed at
    execution, and any memory derived from that contact's data stops being retrievable for the
    withdrawn purpose. *(Scenario: Permissions or contact purpose withdrawn; FR 46, FR 27.)*
43. Observed interest and permission to contact are separate records. A test asserts that
    recording an inbound submission creates no contact permission by itself. *(Scenario:
    Permissions or contact purpose withdrawn; FR 46.)*
44. Connection health, last successful intake, lag, and unresolved failures are readable per
    connection through a supported operation and are visible in the connection settings screen.
    *(Scenario: Intake without a model session; FR 38.)*
45. A handoff operation records a durable identifier, source opportunity, purpose, destination,
    approved payload snapshot, and result. With no destination configured, requesting one yields
    an explicit unavailable state, not a silent success and not a created opportunity outcome.
    *(Scenario: Crash during handoff; FR 45, guardrail 20.)*
46. No route, package, table, MCP tool, service name, environment variable, configuration key, or
    user-facing string in the repository matches a legacy product name or a generalized
    source-product prefix, enforced by a check that runs in continuous integration. Documentation
    files recording historical migration notes are the single allowed exception, listed
    explicitly. *(Scenario: Publication review; FR 49, guardrail 1.)*
47. Every link in the web interface is produced through routing configuration. The application
    passes its full interface test suite in single-host path mode and in subdomain mode, with no
    code change between the two runs. *(Scenario: Fresh public clone; FR 47.)*
48. The web interface builds and runs in the single-server container deployment with no
    hosting-platform-specific feature in its dependency set, enforced by a build that fails on a
    platform-only import or configuration key. *(Scenario: Fresh public clone; FR 48,
    guardrail 15.)*
49. Ported interface code contains no personal data, rate, client name, or private deployment
    detail. Every fixture in the repository is synthetic, asserted by a fixture provenance check.
    *(Scenario: Publication review; FR 50.)*

---

## Phase 4 — The optional job-search workflow

**Goal.** Restore the enrichment and application-preparation depth of the opportunity-discovery
predecessor, entirely as an optional workflow that a business user never sees.

**Shape.** A job-search capability supplying pipeline presets, namespaced schema extensions for
candidate-fit and application questions, the job-source connectors, the multi-observation
enrichment behaviour where an email alert, a copied search result, and a full posting converge on
one opportunity, and the proposal drafting and answer library screens deferred from the UI port
inventory. The email transport becomes a deterministic client-side poller with a durable cursor,
not an agent routine.

**Key boundaries.** Nothing in this phase adds a field, a column, or a concept to the Leads core.
Disabling the capability stops its workers and hides its screens while retaining its records for
inspection and export. The acceptance scenario this phase must satisfy is **Job-search
regression**: email, search result, and full posting enrich one opportunity while preserving
proposals and user decisions. It must also re-satisfy **Business-only installation** with the
capability enabled but unconfigured.

**Answers on landing.** Idea-doc question 5 (which proposal-generation capabilities belong in the
initial job-search release).

---

## Phase 5 — The work-in-motion module

**Goal.** Current ships: commitments, projects, tasks, status, priority, due dates, and
dependencies, with work created from an opportunity or independently.

**Shape.** The module ported from the work-in-motion predecessor, including its queue, board, and
work-item screens, moved from `better-sqlite3` to the per-workspace Postgres database. The
handoff operation from phase three gains its first destination, with the destination
deduplicating retries so that a lost response after successful creation does not create a second
project. Leads displays a linked work item's state rather than keeping a second editable copy.

**Key boundaries.** Current does not become an invoicing or accounting product. Completing a task
never asserts a domain outcome that another module owns. The acceptance scenario this phase must
satisfy is **Crash during handoff**: a retry recovers the same created work, and an uncertain
external outcome stays visible until reconciled.

---

## Phase 6 — Channels and the second runtime

**Goal.** Prove that the authorization model is one model, by adding a second conversational
surface and a structurally different runtime adapter.

**Shape.** The OpenRouter adapter, which supplies its own agent loop and dispatches tools through
the authorized boundary, with an explicit model and provider allowlist, required-parameter
enforcement, and a fallback policy that cannot widen who receives private context. Telegram as a
second channel, entering the same session and authorization model, with per-audience visibility
so that a private conversation and a group conversation are distinct. Voice waits until this
phase's text interaction and permission model are stable.

**Key boundaries.** No channel becomes a privileged back door. Native session identifiers stay
private adapter handles bound to runtime, credential scope, actor, workspace, and audience, and no
adapter ever resumes a global latest session. The acceptance scenarios this phase must satisfy
are **Runtime choice**, **Runtime switch or retry**, and **Wrong workspace or channel audience**.

**Answers on landing.** Idea-doc question 15 (minimum useful voice experience and its timing) and
the hosted-default half of question 10.

---

## Phase 7 — Framework proof and a v0.1 release

**Goal.** Demonstrate that the extension contracts are real, then publish.

**Shape.** The remainder of the module lifecycle from D5: disable, remove, purge, and restore,
with dependency checks, in-flight effect reconciliation, retained exports, and detached-record
handling. A small synthetic specialist module, registering records, tools, interface
contributions, jobs, migrations, and exports through the public extension points with no change
to the core. Domain packs and their composition rules. The licence decision, which is
deliberately deferred to this point because it must be made before accepting substantial outside
contributions and after the contracts it governs are real.

**Key boundaries.** The synthetic module is an example, not a product for another profession. The
acceptance scenarios this phase must satisfy are **A new specialist module**, **Module disabled
during execution**, **Module removal with dependencies**, **Removal from one workspace**,
**Module reinstalled or upgraded**, **Combined domain packs**, and **Public pack export**.

**Answers on landing.** Idea-doc questions 14, 21, 22, and 23.

---

## Phase 8 — The hosted edition

**Goal.** Offer a managed workspace to a customer who does not want to operate infrastructure.

**Not planned in detail.** This phase is named so that release-one decisions do not foreclose it,
not because its shape is decided. What is already recorded and carried forward:

- Module subdomains compete with per-tenant subdomains for the same namespace level, and a
  wildcard certificate covers one level only. The hosted edition must choose its scheme
  deliberately rather than inheriting the reference deployment's.
- A hosted service uses service-owned model credentials through an API or agent SDK. It must not
  depend on customers sharing consumer CLI subscription logins.
- Per-workspace encryption and key management need a threat model and a recovery procedure, not
  one library option, and their design is a prerequisite for this phase rather than an addition to
  an earlier one.
- Provider licensing and attribution for every job source must be reviewed before that source is
  enabled in a public hosted service.

**Answers on landing.** Idea-doc questions 3, 9, and the hosted half of question 2.
