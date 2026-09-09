# Contributor and agent instructions

Read [the idea document](docs/ideas/rheo-stream-idea.md) before making architecture
decisions. Its decision ledger distinguishes settled direction from proposals and
open questions. This repository currently contains a scaffold, not a working app.

- Use issue → dedicated branch → linked draft PR → relevant checks/review → GitHub
  merge for feature and bug delivery. The initial idea-only root commit bootstraps
  the repository; later work follows the PR workflow.
- Keep code and examples public-safe. Personal profiles, private instructions,
  credentials, workspace data, logs, and exports belong outside the checkout or
  in the explicitly ignored local state directory.
- When the editor opens a parent workspace, this child checkout remains the Git,
  build-context, and publication root. Follow [the workspace layout](docs/workspace-layout.md).
  Do not initialize Git at the parent, copy its private siblings into source, or
  add symlinks that expose them through the public tree. Access private inputs only
  when the task requires them; their visibility in an editor is not permission to
  publish them or send them to an external service.
- Use only synthetic fixtures. Do not access real workspaces or production data
  while running tests or creating examples.
- Public module defaults must not contain a particular user's configuration.
- Keep profession-specific rules in modules and presets. Modules use service/event
  contracts and cannot write another module's tables.
- Treat module installation, dependencies, disablement, data retention, and removal
  as part of the design. Do not make optional modules hidden requirements.
- Keep framework/runtime/storage choices explicit. These README placeholders do
  not authorize silently settling the pending stack or license decisions.
- Do not copy legacy repository history, private documentation, or whole source
  trees. Review each selected contribution for privacy, provenance, and licensing.
- Run `python3 scripts/check_repository.py` for repository/documentation changes
  and relevant behavior tests when implementations exist. Review what is staged
  before pushing; ignore rules do not protect already tracked data.

Do not add personal machine paths, private orchestration instructions, or local
framework installations to this file. Contributors may keep those outside Git.
