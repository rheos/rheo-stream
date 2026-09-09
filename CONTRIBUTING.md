# Contributing

Rheo Stream is at the idea and architecture stage. Start with the
[idea document](docs/ideas/rheo-stream-idea.md) and its open decisions. Discuss scope
in an issue before adding implementations or introducing dependencies.

Create a dedicated branch and linked draft pull request before implementation.
Describe the resulting behavior, run relevant checks, and complete review before
merging through GitHub. Keep proposals distinguishable from accepted decisions.

For repository changes, run:

```sh
python3 scripts/check_repository.py
```

Review staged content for private information as well as credentials. Use invented
people, organizations, and source payloads in examples. Never attach real client
data, production exports, or secrets to public issues, PRs, test results, or logs.
The path checks are deliberately limited and do not establish that arbitrary file
contents are safe to publish.

Use the [parent workspace layout](docs/workspace-layout.md) to keep the public
checkout alongside private configuration and runtime data. Open the parent in an
editor, but run Git, builds, and publication from the child checkout. Do not create
a Git repository at the parent or link private sibling content into the public
tree. The optional `/.rheo-local/` directory is ignored; it must not become the
source of committed fixtures. Public packs contain generic defaults, while
personal overrides remain private.

License and contribution terms remain undecided. Discuss architectural proposals
through issues; defer substantial outside code contributions until those terms
are established. Reused material needs source provenance and license review.
