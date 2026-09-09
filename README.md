# Rheo Stream

A modular, self-hostable framework for agent-assisted professional workflows.

Rheo Stream brings together reusable infrastructure for identity, permissions,
durable work, integrations, and an agent named **Rheo**. Optional modules develop
opportunities in **Leads**, carry active work in **Current**, and retain useful
context in **Recallatron**. Different professions can compose their own modules,
connectors, and workflow defaults.

**Status: idea and repository scaffold.** There is no runnable application yet.
The implementation stack, storage topology, module contracts, and license are
still being decided. Directory names identify intended boundaries, not implemented
features or independently deployed services.

Start with the [Rheo Stream idea document](docs/ideas/rheo-stream-idea.md). It is
the repository's foundational document and the only file in its first commit.

## Initial structure

```text
apps/                      Application entry points and interface adapters
packages/core/             Shared framework infrastructure
packages/contracts/        Versioned public contracts and module interfaces
modules/
  leads/                   Opportunity development
  current/                 Commitments and active work
  recallatron/             Permission-aware durable memory
  relationships/           Proposed shared people and organization records
connectors/                External source and destination adapters
channels/                  Conversation surfaces such as text and voice
runtimes/                  Replaceable agent/model execution adapters
packs/freelance-software/   First reusable domain-pack direction
docs/ideas/                Product thesis and architectural direction
docs/requirements/         Future scoped requirements
docs/architecture/         Future specifications and decision records
examples/                  Synthetic examples only
tests/                     Future contract, integration, and acceptance tests
scripts/                   Repository checks and development tooling
deploy/                    Future generic deployment templates
```

Modules are logically separate; the preferred starting implementation is a modular
monolith. The first useful configuration supports freelance software work while
keeping job search optional and the core independent of any profession.

## Public code, private workspaces

The repository contains reusable code, definitions, and synthetic examples.
Personal profiles, rates, client data, prompts, credentials, conversations,
databases, documents, and runtime output belong in private workspace storage.
For development, open a parent folder containing the public checkout and private
siblings:

```text
rheo-stream-workspace/      Editor workspace; no Git repository here
  rheo-stream/             Public Git repository; build and publication root
  private/                 Local configuration, documents, agent context, modules
  workspaces/              Private runtime data, separated by application workspace
  backups/                 Private backups
  workspace.paths.json     Local path map; outside the public repository
```

Only `rheo-stream/` is versioned. Private siblings are outside its Git root; ignore
rules inside the checkout cannot cover them. Keep Git, build, and publication
operations rooted in the child repository, and connect private locations through
explicit configuration. The reserved `/.rheo-local/` directory remains an ignored
development fallback for users who deliberately choose checkout-local storage.

See [workspace layout](docs/workspace-layout.md) for setup and connection boundaries.
The path map describes the local arrangement; runtime loading is not implemented.

See the [data boundary](docs/ideas/rheo-stream-idea.md#private-data-placement-in-each-deployment-mode)
and [publication requirements](docs/ideas/rheo-stream-idea.md#public-repository-contents-and-private-workspace-contents).

## Repository checks

With Git and Python 3.9 or newer installed:

```sh
python3 scripts/check_repository.py
```

This checks private-path exclusions, tracked artifacts, and local Markdown link
targets. It is not a secret scanner or a replacement for reviewing public content.
The same check runs in GitHub Actions. No application dependencies are required.

## Contributing and license

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) before changing
the architecture or importing code. The project license has not been selected;
there is no LICENSE file yet. License and contribution terms must be settled before
substantial implementation or outside code contributions.

Project home: [rheo.stream](https://rheo.stream).
