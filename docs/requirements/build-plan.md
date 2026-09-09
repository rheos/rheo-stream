# Rheo Stream — phased build plan

**Status:** Proposed plan skeleton, awaiting maintainer ratification. Phases one to three are
planned to implementable depth; later phases are sketches that will be planned when their
predecessor lands. The decisions this plan is built on include five decisions taken on the
maintainer's behalf (R1 to R5 in the companion requirements document). The maintainer's review
of the pull request that carries these documents is the ratification step; until that review,
treat R1 to R5 as proposed rather than accepted.
**Companion:** [Requirements and scope](requirements-and-scope.md), which carries the decisions,
functional requirements (cited as FR *n*), and the release-one scope boundary.
**Decision citations:** D *n* is a settled decision and R *n* is a decision taken on the
maintainer's behalf. Both are defined in the companion requirements document: D *n* under
[Settled decisions](requirements-and-scope.md#settled-decisions), R *n* under
[Questions resolved here](requirements-and-scope.md#questions-resolved-here). No criterion in
this plan rests on a decision recorded anywhere else.
**Source of acceptance criteria:** the architecture acceptance-scenario table in the
[idea document](../ideas/rheo-stream-idea.md#architecture-acceptance-scenarios). Every criterion
below names the scenario it comes from.

Acceptance criteria are numbered continuously across the whole plan and are checkable by
inspection or by a test. None is a judgement about quality. A
[functional-requirement coverage table](#functional-requirement-coverage) at the end of this
document maps every FR from 1 to 53 to the criteria that test it.

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
  into continuous integration. This phase owns the application shell; phase two unifies
  navigation and theme on top of it.
- Workspace and storage foundation: the control plane (accounts, workspace registry), the
  per-workspace database provisioning path, migration tracking per module, and the storage
  adapter seam.
- Identity: the identity-provider boundary with one OAuth code-host provider, plus locally
  issued tokens for command-line and MCP clients, issued from an authenticated web session or by
  an operator-level command on a headless install.
- The operator-level command that adds a second member to a workspace against the control plane.
  R1 makes this the only way a second member exists in release one, and criterion 8 needs a
  `member` session to test the role check against.
- Two test fixtures, both test-only and neither a shipped capability:
  - A second identity-provider implementation that is not an OAuth provider, existing purely as
    a test double so that criterion 8 can substitute it behind the boundary. D6 ships exactly
    one real provider in release one, and this fixture does not become a second one.
  - A deduplicating consumer that records processed event identifiers, so criterion 11 has
    something to deliver to.
- Durable work: the transactional outbox, the worker with leases, bounded retries and
  cancellation, operation records with terminal status, and the audit record.
- The MCP façade with the safety-class registration check and a small set of read-class tools
  sufficient to prove the boundary.
- `ClaudeCliRuntime` behind the runtime adapter contract, with capability discovery.
- Workspace export and restore.
- Routing configuration, through which every link the interface produces is generated.

**Out of scope**

- Any domain module. There are no leads, no work items, and no memories in this phase.
- The second runtime adapter, channels, and voice.
- Module disable, remove, purge, and restore (D5).
- Any interface beyond the shell, a login, and a workspace switcher.

**Acceptance criteria**

1. A clone of the public repository, with no private configuration and no credentials, builds
   and starts the synthetic demo, and the demo completes without reading any file outside the
   checkout and the synthetic fixture set. *(Scenario: Fresh public clone; FR 14.)*
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
6. No code path accepts a database path, connection string, schema name, workspace identifier, or
   actor identity from a request body, query parameter, model argument, or workspace setting. A
   test supplies each of those and asserts the value is ignored and the authenticated context is
   used. *(Scenario: Wrong workspace or channel audience; FR 2, FR 23.)*
7. A request carrying a valid record or operation identifier belonging to another workspace is
   refused by the HTTP API, the MCP façade, and the job dispatcher alike. *(Scenario: Wrong
   workspace or channel audience; FR 1.)*
8. A person signs in through the OAuth code-host provider and the resulting session carries an
   actor, a workspace, and a role. The provider is reached only through the identity-provider
   boundary, verified two ways: the second identity-provider implementation, which is a test
   double and not a shipped provider, is substituted behind the same boundary and leaves the
   domain service suite passing unchanged, and a check asserts no domain module imports the
   provider package. A second member added by the operator-level command receives a `member`
   session, and an operation restricted to `owner` is refused to it. *(Scenario: Hosted workspace
   data; FR 3, FR 5.)*
9. A locally issued command-line or MCP token names exactly one actor, one workspace, and one
   permitted operation set. It is issued either from an already-authenticated web session or by
   the operator-level command against the control plane, and presenting it never requires a
   browser flow. A test presents a malformed token, an expired token, and a valid token whose
   operation set excludes the requested operation, and asserts each is refused with a distinct
   non-success state and leaves no partial effect. *(Scenario: Headless approval or failure;
   FR 4.)*
10. Every workspace row records the installed core version, each installed module's version, and
    each module's schema version, readable through a supported operation rather than by querying
    a migration table directly. *(Scenario: Module reinstalled or upgraded; FR 9.)*
11. A state change and its outgoing event commit in one transaction. A test that kills the
    process between commit and delivery, then restarts, observes the event delivered exactly once
    to the deduplicating test consumer, which records processed identifiers. *(Scenario: Crash
    during handoff; FR 15.)*
12. A worker killed mid-task releases its lease and the task is retried within its bounded retry
    budget; a task exhausting its budget appears in a failure list with its error, and is not
    silently dropped. A queued task that is cancelled never runs, and a running task that is
    cancelled reaches a terminal cancelled status rather than a success or a further retry,
    verified by a test that cancels one of each and asserts the recorded terminal status and the
    absence of any later effect. *(Scenario: Crash during handoff; FR 16.)*
13. Every long-running operation returns an operation identifier before it completes, and that
    operation reports one of a fixed set of terminal statuses, including an explicit unresolved
    status. A test asserts no operation can report success without a recorded terminal check.
    *(Scenario: Crash during handoff; FR 17.)*
14. Every mutating operation writes an audit record naming actor, workspace, operation, and time,
    readable through a supported operation rather than by querying a table directly. A mutating
    operation registered without an audit path fails registration at startup with a named
    operation, so the record cannot be skipped by omission. A test performs one mutation of each
    registered kind and asserts a matching audit record exists for every one. *(Scenario: Crash
    during handoff; FR 18.)*
15. A workflow that declares a requirement the configured runtime cannot satisfy (structured
    output, streaming, or continuation) is rejected before the runtime is invoked, with a named
    unmet capability. *(Scenario: Runtime capability mismatch; FR 19, FR 20.)*
16. A headless run whose executable is missing, whose credential is expired, whose tool is
    denied, or whose output stream truncates returns a distinct non-success state within the
    configured deadline. A test induces each of the four and asserts no hang and no success
    report. *(Scenario: Headless approval or failure; FR 21.)*
17. Every registered MCP tool and every registered service operation declares exactly one safety
    class, and either one registered without a class fails registration at startup, naming the
    tool or the operation. A test registers one tool and one service operation with no declared
    class and asserts startup fails naming each. *(Scenario: Headless approval or failure;
    FR 24.)*
18. Every tool the MCP façade exposes is namespaced and goal-level and reaches storage only by
    calling an application service. A test enumerates the registered tools and asserts that none
    accepts SQL, a table name, or a query fragment as an argument, and a check asserts that no
    file in the MCP façade imports a database driver or a repository directly. *(Scenario: Wrong
    workspace or channel audience; FR 22, guardrail 5.)*
19. A workspace export produces an artifact that a restore reads back into an empty deployment,
    after which the restored workspace's composition, configuration versions, module schema
    versions, and records match the original, verified by comparison rather than by inspection.
    A pending approved action is restored in a state that requires a fresh approval before it can
    execute. *(Scenario: Export and restore; FR 52.)*
20. Every link the web interface produces is generated through routing configuration, with no
    route string hard-coded to one topology. This phase's surface is the application shell, the
    login, the workspace switcher, the post-login redirect, and the OAuth callback URL, and the
    last two are topology-sensitive, so they are in scope here rather than later. The interface
    test suite covering that surface passes in single-host path mode and in subdomain mode with
    no code change between the two runs, and both runs are a continuous-integration gate from
    this phase onward, over whatever interface surface exists when it runs. *(Scenario: Fresh
    public clone; FR 47.)*
21. The web interface builds and runs in the single-server container deployment with no
    hosting-platform-specific feature in its dependency set, enforced by a build that fails on a
    platform-only import or configuration key. That build is a continuous-integration gate from
    this phase onward, over whatever interface surface exists when it runs. *(Scenario: Fresh
    public clone; FR 48, guardrail 15.)*

---

## Phase 2 — The memory module

**Goal.** Recallatron ships as the first real module: installed and enabled through the module
registration contract, storing and retrieving durable memory under workspace and record
permissions, with its retrieval layer rebuilt on Postgres and its data migrated out of the
predecessor. This phase proves module contract v1 on the smallest domain that can carry it (D11).

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
  new retrieval layer, verification, and switchover. The migration runs against the maintainer's
  real memories, so its verification report is written to private workspace storage alongside
  that data and is never committed to this repository (FR 53). The switchover itself is a step
  the maintainer performs deliberately once the report is satisfactory; the migration job never
  switches over on its own.
- Navigation and theme unification on the phase-one application shell: one token set, one theme,
  and one navigation contract that modules contribute to, plus the memory browse, search, and
  entity screens ported from the predecessor.
- The naming and fixture-provenance checks, wired as gates in continuous integration. They bind
  from this phase onward because this phase carries the first ported interface code, which is
  where a legacy name, a hard-coded API path, or real data would enter the public repository. The
  routing-configuration and platform-dependency gates already bind from phase one and take this
  phase's ported surface into their scope.

**Out of scope**

- Module disable, remove, purge, and restore.
- Cross-module memory links to Leads records beyond the reference type, since Leads does not
  exist yet. The link type is defined here and exercised in phase three.
- Automatic memory extraction from conversations. Release one remembers what it is told to
  remember.

**Acceptance criteria**

22. The memory module is installed and enabled entirely through the registration contract: no
    core file changes to add it, verified by a test that enables it in a fresh workspace and
    asserts its records, tools, migrations, and interface contributions all appear.
    *(Scenario: A new specialist module; FR 26.)*
23. The module's manifest declares its owned record types, its storage destination, its
    migrations, its configuration schema, its provided tools with their safety classes, and its
    export format. A manifest missing any of these fails validation at install with a named
    missing field. *(Scenario: A new specialist module; FR 52.)*
24. The module writes only to its own storage. A test asserts that no memory-module code path
    holds a handle to another module's tables, that the core's storage API is the only route to a
    connection, and that a cross-module change is effected only through a public operation or
    event. *(Scenario: A new specialist module; FR 11, guardrail 6.)*
25. A retrieval call by an actor without permission on a source record returns no content
    derived from that record, verified by a test that stores a memory under one permission
    scope and queries it under another. *(Scenario: Wrong workspace or channel audience; FR 27.)*
26. A memory derived from two sources carries the intersection of their audiences, not the
    union. A test combines a broadly readable source with a restricted one and asserts the
    result is restricted. *(Scenario: Wrong workspace or channel audience; FR 27.)*
27. Deleting or superseding a source record invalidates its derived summaries and its
    embeddings in the same operation, verified by querying the retrieval index afterward.
    *(Scenario: Permissions or contact purpose withdrawn; FR 28.)*
28. Every workspace has an explicit memory retention setting, and a workspace created with no
    explicit setting receives a bounded default rather than indefinite retention. *(Scenario:
    Permissions or contact purpose withdrawn; FR 29.)*
29. The retrieval strategy is selected through the adapter, and a test runs the module's full
    behavioural suite against both a dense-only and a lexical-only configuration, both passing.
    *(Scenario: Runtime choice, applied to retrieval rather than to a model runtime; FR 30.)*
30. The migration from the predecessor's memory store is verified before switchover by a
    count-and-sample comparison: every source record has a destination record, and a sampled set
    of retrieval queries returns the same records under the new retrieval layer as under the old
    one, within a documented tolerance. The comparison result is written to private workspace
    storage next to the migrated data, and a check asserts no migration report is tracked in this
    repository. *(Scenario: Export and restore; FR 53, D9.)*
31. Every phase-one path completes correctly in a workspace where the memory module was never
    installed and never enabled, verified by running the phase-one acceptance suite in such a
    workspace. Workspace-level disable is phase-seven work under D5, so release one proves the
    module boundary by absence rather than by disable. *(Scenario: A new specialist module, for
    the half requiring that the core carry no dependency on a module added through the public
    extension points; FR 26.)*
32. No route, package, table, MCP tool, service name, environment variable, configuration key, or
    user-facing string in the repository matches a legacy product name or a generalized
    source-product prefix. The check runs in continuous integration on every branch from this
    phase onward, and its scope includes this phase's ported surface: the navigation, the theme,
    and the memory browse, search, and entity screens. Documentation files recording historical
    migration notes are the single allowed exception, listed explicitly. *(Scenario: Publication
    review; FR 49, guardrail 1.)*
33. Ported interface code contains no personal data, rate, client name, or private deployment
    detail, and every fixture in the repository is synthetic, asserted by a fixture provenance
    check that runs in continuous integration from this phase onward. *(Scenario: Publication
    review; FR 50.)*
34. Criterion 19 is re-asserted at the end of this phase against a workspace that has the memory
    module installed, enabled, and populated. The export carries the module's records through the
    export format its manifest declares (criterion 23), and after a restore into an empty
    deployment the restored workspace's composition, configuration versions, module schema
    versions, and memory records match the original by comparison. *(Scenario: Export and
    restore; FR 52.)*
35. Criteria 20 and 21 still pass with this phase's interface surface included: the unified
    navigation and theme, and the memory browse, search, and entity screens. This criterion adds
    no new check; it asserts that the two gates established in phase one run unchanged in
    continuous integration over the larger surface. *(Scenario: Fresh public clone; FR 47,
    FR 48.)*

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
- Opportunities, one inbound-services pipeline preset with stable stage identifiers and pinned
  configuration versions, qualification records, and terminal dispositions.
- The record-level deletion path for observations, parties, and opportunities (R5).
- The handoff operation, defined with no destination.
- A recording sink: a test-only operation registered in the external-side-effect safety class
  that records what it would have sent and sends nothing. It is the only external-class operation
  in release one, and it exists so that the approval binding and the fail-closed recheck have
  something to execute against. It is a test fixture, not a shipped destination: R2's rule is
  unchanged, the handoff operation still has exactly one release-one destination, none, and the
  sink is not a handoff destination and does not appear in the release-one scope boundary as a
  product capability.
- Contact purpose and permission records, kept separate from observed interest.
- The first web interface: opportunity list and triage, opportunity detail with evidence,
  qualification view, and connection settings, ported per the UI port inventory.
- The first real funnel connected, plus a second unrelated synthetic event-referral funnel as a
  fixture. Both route into the one inbound-services preset through different declarative mappings
  and different routing rules. Pointing the live form at the deployment sends real inquiries from
  real people into the system, so it is a step the maintainer performs deliberately once the
  synthetic funnel passes; nothing connects it automatically.

**Out of scope**

- Any job-search field, source, rubric, or screen.
- Work creation. A handoff has no destination in this phase.
- External CRM connections. The field-ownership contract is written; no connector ships.
- Any external-side-effect operation other than the recording sink, and any financial operation
  at all.
- A second pipeline preset, including a dedicated referral preset.

**Acceptance criteria**

36. A valid signed webhook delivery is authenticated, stored, acknowledged, and processed to a
    created opportunity with no agent runtime process running anywhere in the deployment.
    *(Scenario: Intake without a model session; FR 35, FR 32.)*
37. A CSV import and a JSON import are accepted through the same declarative, versioned field
    mapping as the webhook receiver and produce normalized observations on the same path,
    verified by a test that maps one source record through all three transports and asserts the
    resulting observations are identical apart from their delivery transport. A file whose shape
    does not match its declared mapping version is refused with a named field rather than
    partially applied. *(Scenario: Two different custom funnels; FR 32.)*
38. A manually captured inquiry produces a normalized observation through the same declarative,
    versioned field mapping and the same processing path as a webhook delivery. Its delivery
    transport is recorded as manual capture, and its acquisition attribution, meaning which funnel
    and which campaign, is chosen by the operator at capture from the funnels the workspace has
    configured, so attribution is never empty and never holds a transport value. A test asserts
    the resulting observation is indistinguishable in shape from a delivered one, and that a
    capture submitted with no funnel selected is refused rather than stored with empty
    attribution. *(Scenario: Two different custom funnels; FR 32, FR 36.)*
39. The authenticated ingestion API resolves the workspace from the connection's own credential.
    A test posts a delivery whose payload claims a different tenant, a different destination
    workspace, and an elevated permission set, then asserts all three claims are ignored, the
    observation lands in the credential's workspace, and the claimed values survive only as
    evidence inside the stored payload. *(Scenario: Wrong workspace or channel audience; FR 31.)*
40. The acknowledgement returned to the sender is emitted only after the receipt and its pending
    processing work are durably stored, verified by a test that fails the processing step and
    asserts the receipt survives. *(Scenario: Intake without a model session; FR 33.)*
41. Two concurrent deliveries carrying the same source event identifier produce exactly one
    observation and exactly one processing effect. *(Scenario: Same event retried concurrently;
    FR 34.)*
42. A delivery reusing an accepted source event identifier with different content is recorded as
    a conflict, is visible as one, and does not modify the existing observation. *(Scenario: Same
    event retried concurrently; FR 34.)*
43. Every observation records per-field provenance, the source occurrence time, the server receipt
    time, and a bounded copy of the source payload, with the bound enforced rather than advisory.
    Acquisition attribution, meaning which funnel and which campaign, is stored in fields distinct
    from the delivery transport, verified by a test that delivers the same funnel and campaign
    through two transports and asserts the attribution matches while the recorded transport
    differs. *(Scenario: Late evidence or scoring result; FR 36, guardrail 10.)*
44. An observation arriving with an older source occurrence time than the current field values
    does not overwrite them, and a thinner observation does not overwrite a richer one. A test
    submits both orderings and asserts identical resulting field values. *(Scenario: Late
    evidence or scoring result; FR 37.)*
45. A field absent from a payload and a field explicitly cleared by a payload produce
    distinguishable results. *(Scenario: Late evidence or scoring result; FR 37.)*
46. A user-set stage or note survives any later observation, verified by a test that sets a
    stage by hand and then submits a fuller observation. *(Scenario: Late evidence or scoring
    result; FR 37.)*
47. The same person completing two funnel steps produces two observations, and produces two
    opportunities only when a routing rule says so. The fixture supplies evidence of the grade R4
    requires for an automatic match, a source-verified email address from the same source
    connection on both steps, so exactly one party results; a test asserts one party, two
    observations, and the configured opportunity count. Without that evidence the expected result
    is a second party and a review candidate, which criterion 48 covers. *(Scenario: One person,
    several interactions; FR 39, R4.)*
48. An automatic party match occurs only on an authenticated external subject identifier within
    the connection's namespace or on a source-verified email address. A test presents a matching
    name, a matching company domain, and a matching phone number and asserts each produces a
    review candidate and no link. *(Scenario: One person, several interactions; FR 41, R4.)*
49. Party matching never considers a party in another workspace, verified by a test that creates
    identical parties in two workspaces and asserts no candidate crosses. *(Scenario: Wrong
    workspace or channel audience; FR 41.)*
50. After a merge, both original party identifiers still resolve, and an unmerge restores the
    pre-merge state including every record's party reference. *(Scenario: One person, several
    interactions; FR 41, R4.)*
51. A workspace with the Leads module absent creates parties, contact points, and affiliations
    through the relationships module and reads them back, verified by running the relationships
    behavioural suite in a workspace where Leads is not installed. No relationships record carries
    an opportunity field, and no relationships code path references a Leads table. *(Scenario:
    Client work without Leads; FR 40, R4, guardrail 24.)*
52. Two unrelated funnels, the maintainer's inbound-inquiry form and a synthetic event-referral
    funnel, run through the same intake contract with different declarative mappings and different
    routing rules, and both route into the single inbound-services pipeline preset release one
    ships. Neither requires a new core field, a provider-specific column, a second preset, or a
    product name anywhere in the core. *(Scenario: Two different custom funnels; FR 44.)*
53. A workspace works a pipeline to a terminal disposition with no job board configured, no
    candidate profile present, and no application tool registered. A test asserts the
    job-search-related configuration surface is absent rather than merely hidden. *(Scenario:
    Business-only installation; FR 42, FR 44.)*
54. Editing a pipeline preset does not change the stage meaning or field schema of opportunities
    created under an earlier configuration version, verified by a test that edits a preset with
    opportunities mid-stage and asserts their pinned version and stage semantics are unchanged.
    *(Scenario: Preset edited during active work; FR 43.)*
55. Every opportunity and every qualification record stores the configuration version it was
    created under, readable through a supported operation. *(Scenario: Preset edited during
    active work; FR 42, FR 43.)*
56. An inbound payload whose text instructs the agent to send a message, grant a tool, or change
    a policy results in no tool grant, no policy change, and no external effect. The text is
    retrievable as evidence. *(Scenario: Source text requests a tool action; FR 25.)*
57. An approval binds actor, workspace, operation, recipient or destination, payload digest,
    purpose, and execution window, exercised against the recording sink, which is release one's
    only external-side-effect-class operation. A test approves a payload addressed to the sink,
    alters one byte of it, and asserts execution is refused with an explicit invalid-approval
    state rather than executed against the altered payload; the test repeats with an altered
    recipient and with an elapsed execution window, and asserts in each refused case that the
    sink recorded no attempt. A further case revokes the acting actor's permission for the
    operation between approval and execution and asserts the execution rechecks and fails closed
    with nothing recorded, and a last case asserts that a standing grant does not satisfy the
    external class at all. *(Scenario: Headless approval or failure; FR 24, R3 items 3, 4, and
    5.)*
58. Withdrawing contact permission causes a queued action against that contact to fail closed at
    execution. A test approves and queues a recording-sink action against a contact, withdraws
    the contact permission, runs the queue, and asserts the action is refused at execution and
    the sink recorded nothing. The same test asserts that memory derived from that contact's data
    stops being retrievable for the withdrawn purpose. *(Scenario: Permissions or contact purpose
    withdrawn; FR 46, FR 27, FR 28, R3 item 4.)*
59. Observed interest and permission to contact are separate records. A test asserts that
    recording an inbound submission creates no contact permission by itself. *(Scenario:
    Permissions or contact purpose withdrawn; FR 46.)*
60. Connection health, last successful intake, lag, and unresolved failures are readable per
    connection through a supported operation and are visible in the connection settings screen.
    *(Scenario: Intake without a model session; FR 38.)*
61. A handoff operation records a durable identifier, source opportunity, purpose, destination,
    approved payload snapshot, and result. With no destination configured, requesting one yields
    an explicit unavailable state, not a silent success and not a created opportunity outcome.
    *(Scenario: Crash during handoff; FR 45, guardrail 20.)*
62. Deleting an observation, a party, or an opportunity requires an explicit per-action
    confirmation, removes the record together with its derived summaries, embeddings, and
    exports, cancels any queued action that depends on it, and leaves a deletion record naming
    actor, time, record type, and record identifier. A test deletes one record of each type and
    asserts: the record and every derivative are unreadable through every supported operation;
    the dependent queued action is cancelled rather than left runnable; the deletion record exists
    and carries no field copied from the deleted record; a standing grant does not satisfy the
    confirmation; and deleting a party leaves its observations in place as unlinked evidence.
    *(Scenario: Permissions or contact purpose withdrawn; FR 51, R5.)*
63. The phase-three acceptance suite passes in a workspace where the memory module was never
    installed and never enabled: intake, party resolution, opportunity creation, work through the
    pipeline, and the terminal disposition all complete. *(Scenario: A new specialist module,
    for the half requiring that the core carry no dependency on a module added through the
    public extension points; FR 26.)*
64. Criterion 19 is re-asserted at the end of release one against a workspace with the
    relationships module and the opportunity core populated. The export carries parties, contact
    points, affiliations, observations with their per-field provenance, opportunities with their
    pinned configuration versions, and permission records, and after a restore into an empty
    deployment every one of them matches the original by comparison. A pending approved
    recording-sink action is restored in a state that requires a fresh approval before it can
    execute. *(Scenario: Export and restore; FR 52.)*
65. Criteria 20, 21, 32, and 33 still pass with this phase's interface surface included: the
    opportunity list and triage queue, the opportunity detail view, the qualification view, and
    the connection settings screen. This criterion adds no new check; it asserts that the four
    gates run unchanged in continuous integration over the larger surface and that none of them
    regressed. *(Scenario: Publication review; FR 47, FR 48, FR 49, FR 50.)*

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
The job-search capability is a bundle of presets and namespaced schema extensions turned on and
off by workspace configuration, not a module that gets disabled: module disable in the lifecycle
sense is phase-seven work under D5. With the toggle off, its enrichment and polling workers stop
being scheduled, any run already in flight finishes or fails through the ordinary
operation-status path rather than being killed, its screens are hidden, and its records stay
readable and exportable. The acceptance scenario this phase must satisfy is **Job-search
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
- Billing metadata joins the control plane here. Release one holds none (D1, FR 7).
- Provider licensing and attribution for every job source must be reviewed before that source is
  enabled in a public hosted service.

**Answers on landing.** Idea-doc questions 3, 9, and the hosted half of question 2.

---

## Functional-requirement coverage

Every functional requirement in the companion document, from FR 1 to FR 53, appears below. A
requirement is either mapped to the acceptance criteria that test it, or recorded as deliberately
untested in release one with the phase or milestone that carries it and the reason. A
requirement with neither is a gap in this plan, and none is listed that way. Where a criterion
tests part of a requirement, the row says which part and names what is left untested.

| FR | Tested by | Note |
| --- | --- | --- |
| FR 1 | 7 | Cross-workspace refusal across all three entry surfaces is the boundary test. |
| FR 2 | 6 | Storage routing may not come from any caller-supplied source. |
| FR 3 | 8 | Substituting the second provider implementation behind the boundary is the check that domain code depends on the boundary. |
| FR 4 | 9 | Both issuance paths, the scope, and the three rejection cases. |
| FR 5 | 8 | An `owner`-only operation refused to a `member` session is the role check. |
| FR 6 | none in release one | Deliberate. Release one stores only the owner's material (R1), so no second member's private material exists to separate; the invitation-flow milestone named in the release-one scope boundary tests it. |
| FR 7 | 5 | Distinct database or schema per workspace. |
| FR 8 | none in release one | Deliberate. D2 ships no second backend, so the adapter seam can only be proven by the later local-first edition that supplies one; release one writes the interface-level suite without a second implementation to run it against. |
| FR 9 | 10 | Composition and schema versions as readable product data. |
| FR 10 | 2, 3 | Runtime output outside the tracked tree, and the checkout-local opt-in fully ignored. |
| FR 11 | 24 | The core storage API is the only route to a connection, no module holds another module's tables, and cross-module change goes through public operations and events. |
| FR 12 | none in release one | Deliberate. Criterion 6 asserts that a workspace setting cannot supply storage routing or actor identity, which is FR 2 and FR 23, not FR 12. Neither the three-source precedence rules nor the rule that a workspace override cannot relax an operator security policy is tested in release one; both are architecture-specification deliverables (idea-doc question 24). |
| FR 13 | none in release one | Deliberate. Criterion 4 keeps credentials out of the repository, but it does not test FR 13 itself. That a secret is held by reference, scoped to the narrowest component, and never reaches a prompt, a tool argument, or general service context is fixed by the architecture specification's redaction contract (idea-doc question 12). |
| FR 14 | 1, 2 | Fresh clone, synthetic demo, tracked source unchanged. |
| FR 15 | 11 | Outbox in one transaction, exactly-once delivery after a kill. |
| FR 16 | 12 | Leases, bounded retries, an inspectable failure list, and cancellation of a queued and a running task. |
| FR 17 | 13 | Operation identifier and a terminal status set including unresolved. |
| FR 18 | 14 | Written, readable, and impossible to skip by omission. |
| FR 19 | 15 | Partial. The adapter contract is exercised from the first adapter. That no domain module or channel depends on a specific runtime is fully proven only by the structurally different second adapter in phase six (**Runtime choice**). |
| FR 20 | 15 | Capability mismatch rejected before invocation. |
| FR 21 | 16 | Four induced failure modes, no hang, no false completion. |
| FR 22 | 18 | Namespaced goal-level tools, no raw database or privileged SQL path. |
| FR 23 | 6 | Workspace and actor come from the authenticated session; a model-supplied argument is ignored. |
| FR 24 | 17, 57 | Declared class at registration for every MCP tool and every service operation, and the approval binding that a declared class governs, exercised against the recording sink. |
| FR 25 | 56 | Inbound text stays evidence. |
| FR 26 | 22, 31, 63 | Installable and enableable through the contract; the phase-one and phase-three paths both complete where it was never enabled. |
| FR 27 | 25, 26, 58 | Permission-enforced retrieval, intersection of audiences, withdrawal honoured. |
| FR 28 | 27, 58, 62 | Invalidation of derived summaries and embeddings with the source, on supersession and on deletion. |
| FR 29 | 28 | Explicit retention, bounded default. |
| FR 30 | 29 | The behavioural suite passes on dense-only and lexical-only configurations. |
| FR 31 | 39 | Workspace resolved from the connection credential; claimed values never override it. |
| FR 32 | 36, 37, 38 | All three transports through one declarative versioned mapping. |
| FR 33 | 40 | Acknowledgement only after durable receipt. |
| FR 34 | 41, 42 | Concurrent duplicate, and conflicting content under one identifier. |
| FR 35 | 36 | Intake with no runtime process anywhere in the deployment. |
| FR 36 | 38, 43 | Provenance, both timestamps, the bounded payload copy, and attribution separate from transport including at manual capture. |
| FR 37 | 44, 45, 46 | Older and thinner evidence, absent versus cleared, user-owned state. |
| FR 38 | 60 | Health, last intake, lag, unresolved failures, per connection. |
| FR 39 | 47 | Observations, parties, and opportunities as distinct lifecycles. |
| FR 40 | 51 | Relationships usable with Leads absent. |
| FR 41 | 48, 49, 50 | Two evidence classes only, no cross-workspace candidate, reversible merge. |
| FR 42 | 53, 55 | Terminal disposition reached, and the pinned configuration version stored and readable. |
| FR 43 | 54, 55 | Preset edits do not reinterpret existing records. |
| FR 44 | 52, 53 | Two funnels through one core and one preset; no job-shaped surface present. |
| FR 45 | 61 | The handoff operation exists and has no destination. |
| FR 46 | 58, 59 | Interest and permission are separate records; withdrawal fails closed. |
| FR 47 | 20, 35, 65 | Both topology modes with no code change, held from phase one onward, including the login redirect and the OAuth callback URL. |
| FR 48 | 21, 35, 65 | No hosting-platform-only dependency, held from phase one onward. |
| FR 49 | 32, 65 | No legacy name anywhere outside the listed historical notes, held from phase two onward, when the first ported code arrives. |
| FR 50 | 33, 65 | Ported code carries no real data; every fixture synthetic, held from phase two onward. |
| FR 51 | 62 | Confirmed per action, cascading, cancelling dependents, and leaving a content-free deletion record. |
| FR 52 | 19, 23, 34, 64 | Export and restore on an empty workspace, then re-asserted with a module populated and again with the opportunity core populated; the module export format is declared in the manifest and exercised by the phase-two re-assertion. |
| FR 53 | 30 | Count-and-sample verification before switchover, with the report kept in private workspace storage. |
