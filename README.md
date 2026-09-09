# Rheo Stream

An open, self-hostable framework for composing agent-assisted working environments.

> Leads enter the stream. Current carries the work. Recallatron remembers.

Rheo Stream is for independent professionals whose working life is spread across
too many tools. You assemble a workspace from modules: **Leads** develops
opportunities from whatever sources feed you work, **Current** carries active
commitments and projects, and **Recallatron** keeps the context that would
otherwise be lost between sessions. An agent named **Rheo** operates all of it
in conversation, over Claude, Telegram, or voice. Conversation is the interface,
not the database: the modules stay explicit systems of record that you can
inspect, export, and own.

The first reference configuration serves a freelance web developer and software
entrepreneur. The same contracts are meant to carry other professions: an HR
consultant, a regulatory consultant, a sales representative, or a business
routing inquiries from its own websites and forms. Job search is one optional
workflow; a workspace can feed Leads from its own funnels and referral partners
and never touch a job board.

**Status: idea, proposed requirements, and repository scaffold.** There is no
runnable application yet. Proposed requirements for the first release name the
implementation stack (a Python core with a Next.js web interface), the storage
topology (Postgres, one database or schema per workspace), and how much of the
module contract that release implements; they await the maintainer's
ratification. The full module manifest and the license are still open. Directory
names mark intended boundaries, not implemented features.

Start with the [idea document](docs/ideas/rheo-stream-idea.md). It sets out the
product thesis, the architecture direction, and a decision ledger that keeps
settled choices separate from open questions. The
[requirements and scope](docs/requirements/requirements-and-scope.md) and the
[build plan](docs/requirements/build-plan.md) propose what the first release
does and in what order.

## Why this exists

The project grows out of tools already in daily use by one working freelancer:
an opportunity triage system, a ticket desk, a memory service, and a collection
of agent routines. Each is useful; together they are a pile of dashboards with
history trapped in each one. Rheo Stream reconstructs the useful parts as one
system with clear domain boundaries, portable data, and a single agent interface,
built so that other people can run it too.

## How it is put together

A small framework core provides workspaces, permissions, module lifecycle, and
durable background work. Modules own their own records and cooperate through
versioned contracts and events; none writes another's tables. Rheo reaches the
system through one MCP facade with goal-level tools, and every call is checked
against the caller's workspace and permissions. Actions that affect the outside
world (sending, submitting, paying) require explicit policy and leave an audit
trail.

Agent execution is a replaceable adapter. Claude Code in print mode and the
OpenRouter API are the planned runtimes, with Codex CLI as a further target; no
module may assume a particular model or vendor.

```text
apps/                      Application entry points and interface adapters
packages/core/             Shared framework infrastructure
packages/contracts/        Versioned public contracts and module interfaces
modules/
  leads/                   Opportunity development
  current/                 Commitments and active work
  recallatron/             Permission-aware durable memory
  relationships/           Shared people and organization records (proposed)
connectors/                External source and destination adapters
channels/                  Conversation surfaces such as text and voice
runtimes/                  Replaceable agent execution adapters
packs/                     Reusable domain packs; freelance software work first
docs/                      Idea, future requirements and architecture records
examples/                  Synthetic examples only
tests/                     Future contract, integration, and acceptance tests
scripts/                   Repository checks and development tooling
deploy/                    Future generic deployment templates
```

The preferred starting implementation is a modular monolith: logical boundaries
without premature microservices.

## Public code, private data

The repository contains reusable code, definitions, and synthetic examples.
Profiles, rates, client records, prompts, credentials, conversations, and
databases belong in private workspace storage that Git never sees. For
development, the public checkout sits inside an unversioned parent folder next
to its private siblings:

```text
rheo-stream-workspace/     Editor workspace; no Git repository here
  rheo-stream/             Public Git repository; build and publication root
  private/                 Local configuration, documents, agent context
  workspaces/              Private runtime data
  backups/                 Private backups
```

Only `rheo-stream/` is versioned. The [workspace layout guide](docs/workspace-layout.md)
describes the arrangement and its boundaries, and the idea document records the
[data placement rules](docs/ideas/rheo-stream-idea.md#private-data-placement-in-each-deployment-mode)
and [publication requirements](docs/ideas/rheo-stream-idea.md#public-repository-contents-and-private-workspace-contents).
The same rules will apply to a hosted edition: local ownership and hosted
convenience are both intended deployment modes.

## Repository checks

With Git and Python 3.9 or newer installed:

```sh
python3 scripts/check_repository.py
```

This verifies private-path exclusions, tracked artifacts, and local Markdown
link targets. It also runs in GitHub Actions. It is not a secret scanner and
does not replace review of public content.

## Contributing and license

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing the architecture or
importing code. Local `AGENTS.md` and `CLAUDE.md` files are ignored on purpose;
internal build guidance stays in private agent context, as described in the
[workspace guide](docs/workspace-layout.md#private-instructions-and-new-sessions).

The license has not been selected yet and there is no LICENSE file. That
decision comes before substantial implementation or outside contributions, so
treat the code as all-rights-reserved for now.

Project home: [rheo.stream](https://rheo.stream).
